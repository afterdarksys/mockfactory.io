"""
OCI Streaming API Emulator
Kafka-compatible streaming backed by Redis Streams (XADD / XREAD).

API version: 20180418

Covered:
  Streams   — create, get, list, delete
  Messages  — put, get (with cursor)
  Cursors   — create (AT_OFFSET, LATEST, TRIM_HORIZON, AFTER_ID)
  Groups    — create, list (stream consumer groups)
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    DEFAULT_OCI_COMPARTMENT, DEFAULT_OCI_REGION,
    find_by_id, flag_resources_modified, get_resources,
    new_uuid, oci_headers, ocid, paginate, remove_by_id, utcnow_iso,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_ST_PREFIX = "/20180418"

try:
    import redis as _redis
    _redis_client = _redis.Redis(host="localhost", port=6379, db=2, decode_responses=True)
    _redis_client.ping()
    _HAS_REDIS = True
except Exception:
    _redis_client = None
    _HAS_REDIS = False
    logger.warning("Redis not available — OCI Streaming will use in-memory fallback")

# In-memory stream fallback: {redis_key: [(id, {k:v}), ...]}
_mem_streams: dict[str, list] = {}
_mem_counter: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(request: Request, db: Session) -> Environment:
    host = request.headers.get("host", "")
    env_id = next((p for p in host.split(".") if p.startswith("env-")), None)
    if not env_id:
        raise HTTPException(400, "Environment ID not found in host")
    env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING,
    ).first()
    if not env:
        raise HTTPException(404, "Environment not found or not running")
    return env


def _ok(body, status: int = 200) -> Response:
    return Response(
        content=json.dumps(body),
        status_code=status,
        headers=oci_headers(),
        media_type="application/json",
    )


def _stream_key(env_id: str, stream_id: str) -> str:
    return f"ocistream:{env_id}:{stream_id}"


def _xadd(key: str, fields: dict) -> str:
    """Append a message to the stream; return the generated message ID."""
    if _HAS_REDIS and _redis_client:
        flat = {}
        for k, v in fields.items():
            flat[k] = v if isinstance(v, str) else json.dumps(v)
        msg_id = _redis_client.xadd(key, flat)
        return msg_id if isinstance(msg_id, str) else msg_id.decode()
    else:
        _mem_counter[key] = _mem_counter.get(key, 0) + 1
        msg_id = f"{int(time.time() * 1000)}-{_mem_counter[key]}"
        _mem_streams.setdefault(key, []).append((msg_id, fields))
        return msg_id


def _xread(key: str, cursor: str, count: int) -> list[tuple[str, dict]]:
    """Read up to `count` messages after `cursor`."""
    if _HAS_REDIS and _redis_client:
        result = _redis_client.xread({key: cursor}, count=count, block=0)
        if not result:
            return []
        # result: [(stream_key, [(id, {fields}), ...])]
        entries = result[0][1]
        out = []
        for entry_id, fields in entries:
            out.append((
                entry_id if isinstance(entry_id, str) else entry_id.decode(),
                {k if isinstance(k, str) else k.decode(): v if isinstance(v, str) else v.decode()
                 for k, v in fields.items()},
            ))
        return out
    else:
        msgs = _mem_streams.get(key, [])
        # Simple offset: cursor "0" means start, else find position after cursor id
        out = []
        past = (cursor == "0")
        for msg_id, fields in msgs:
            if past:
                out.append((msg_id, fields))
                if len(out) >= count:
                    break
            elif msg_id == cursor:
                past = True
        return out


def _xlen(key: str) -> int:
    if _HAS_REDIS and _redis_client:
        return _redis_client.xlen(key)
    return len(_mem_streams.get(key, []))


def _xdel_all(key: str) -> None:
    if _HAS_REDIS and _redis_client:
        _redis_client.delete(key)
    else:
        _mem_streams.pop(key, None)
        _mem_counter.pop(key, None)


# ---------------------------------------------------------------------------
# Streams — CRUD
# ---------------------------------------------------------------------------

@router.post(_ST_PREFIX + "/streams")
async def create_stream(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_streams", [])

    name = body.get("name")
    if any(s["name"] == name for s in resources["oci_streams"]):
        raise HTTPException(409, f"Stream '{name}' already exists")

    stream_id = ocid("stream")
    redis_key = _stream_key(env.id, stream_id)

    stream = {
        "id": stream_id,
        "name": name,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "partitions": body.get("partitions", 1),
        "retentionInHours": body.get("retentionInHours", 24),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "messagesEndpoint": (
            f"https://streaming.{DEFAULT_OCI_REGION}.oci.oraclecloud.com"
        ),
        "_redisKey": redis_key,
    }
    resources["oci_streams"].append(stream)
    flag_resources_modified(db, env)
    return _ok({k: v for k, v in stream.items() if not k.startswith("_")}, 200)


@router.get(_ST_PREFIX + "/streams")
async def list_streams(
    compartmentId: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    streams = resources.get("oci_streams", [])
    if name:
        streams = [s for s in streams if s.get("name") == name]
    public = [{k: v for k, v in s.items() if not k.startswith("_")} for s in streams]
    items, next_page = paginate(public, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_ST_PREFIX + "/streams/{stream_id}")
async def get_stream(stream_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    stream = find_by_id(resources.get("oci_streams", []), "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    return _ok({k: v for k, v in stream.items() if not k.startswith("_")})


@router.delete(_ST_PREFIX + "/streams/{stream_id}")
async def delete_stream(stream_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    streams = resources.get("oci_streams", [])
    stream = find_by_id(streams, "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    _xdel_all(stream["_redisKey"])
    remove_by_id(streams, "id", stream_id)
    # Remove associated groups
    resources["oci_stream_groups"] = [
        g for g in resources.get("oci_stream_groups", [])
        if g.get("streamId") != stream_id
    ]
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Messages — put + get
# ---------------------------------------------------------------------------

@router.post(_ST_PREFIX + "/streams/{stream_id}/messages")
async def put_messages(stream_id: str, request: Request, db: Session = Depends(get_db)):
    """PUT messages into a stream partition (XADD)."""
    env = _env(request, db)
    resources = get_resources(env)
    stream = find_by_id(resources.get("oci_streams", []), "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    body = await request.json()
    messages = body.get("messages", [])
    entries = []

    for msg in messages:
        key_b64 = msg.get("key", "")
        value_b64 = msg.get("value", "")
        try:
            key_str = base64.b64decode(key_b64).decode("utf-8", errors="replace")
        except Exception:
            key_str = key_b64
        try:
            value_str = base64.b64decode(value_b64).decode("utf-8", errors="replace")
        except Exception:
            value_str = value_b64

        msg_id = _xadd(stream["_redisKey"], {"key": key_str, "value": value_str})
        entries.append({"offset": msg_id, "partition": 0, "timestamp": utcnow_iso()})

    logger.info("OCI Streaming put %d messages: %s", len(entries), stream.get("name"))
    return _ok({"entries": entries}, 200)


@router.get(_ST_PREFIX + "/streams/{stream_id}/messages")
async def get_messages(
    stream_id: str,
    cursor: Optional[str] = None,
    limit: int = 10,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET messages from a stream cursor position (XREAD)."""
    env = _env(request, db)
    resources = get_resources(env)
    stream = find_by_id(resources.get("oci_streams", []), "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    # Decode cursor (base64-encoded offset)
    redis_cursor = "0"
    if cursor:
        try:
            redis_cursor = base64.b64decode(cursor).decode()
        except Exception:
            redis_cursor = cursor

    entries = _xread(stream["_redisKey"], redis_cursor, min(limit, 10000))

    messages = []
    last_offset = redis_cursor
    for entry_id, fields in entries:
        key_bytes = base64.b64encode(fields.get("key", "").encode()).decode()
        val_bytes = base64.b64encode(fields.get("value", "").encode()).decode()
        messages.append({
            "stream": stream_id,
            "partition": 0,
            "offset": entry_id,
            "timestamp": utcnow_iso(),
            "key": key_bytes,
            "value": val_bytes,
        })
        last_offset = entry_id

    # Next cursor is base64(last_offset)
    next_cursor = base64.b64encode(last_offset.encode()).decode() if messages else cursor

    return _ok({"messages": messages, "nextCursor": next_cursor}, 200)


# ---------------------------------------------------------------------------
# Cursors
# ---------------------------------------------------------------------------

@router.post(_ST_PREFIX + "/streams/{stream_id}/cursors")
async def create_cursor(stream_id: str, request: Request, db: Session = Depends(get_db)):
    """Create a cursor for consuming messages."""
    env = _env(request, db)
    resources = get_resources(env)
    stream = find_by_id(resources.get("oci_streams", []), "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    body = await request.json()
    cursor_type = body.get("type", "TRIM_HORIZON")  # TRIM_HORIZON | LATEST | AT_OFFSET | AFTER_OFFSET

    if cursor_type in ("TRIM_HORIZON",):
        offset = "0"
    elif cursor_type == "LATEST":
        # Point to the end of the stream
        if _HAS_REDIS and _redis_client:
            info = _redis_client.xinfo_stream(stream["_redisKey"]) if _xlen(stream["_redisKey"]) > 0 else {}
            offset = str(info.get("last-generated-id", f"{int(time.time()*1000)}-0"))
        else:
            msgs = _mem_streams.get(stream["_redisKey"], [])
            offset = msgs[-1][0] if msgs else f"{int(time.time()*1000)}-0"
    else:
        raw_offset = body.get("offset", "0")
        offset = str(raw_offset)

    cursor_value = base64.b64encode(offset.encode()).decode()
    return _ok({"value": cursor_value}, 200)


# ---------------------------------------------------------------------------
# Stream groups (consumer groups)
# ---------------------------------------------------------------------------

@router.post(_ST_PREFIX + "/streams/{stream_id}/groups")
async def create_group(stream_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    stream = find_by_id(resources.get("oci_streams", []), "id", stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    resources.setdefault("oci_stream_groups", [])
    group_id = new_uuid()
    group = {
        "id": group_id,
        "streamId": stream_id,
        "name": body.get("name"),
        "compartmentId": stream.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
    }
    resources["oci_stream_groups"].append(group)
    flag_resources_modified(db, env)
    return _ok(group, 200)


@router.get(_ST_PREFIX + "/streams/{stream_id}/groups")
async def list_groups(
    stream_id: str,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    groups = [g for g in resources.get("oci_stream_groups", []) if g.get("streamId") == stream_id]
    items, next_page = paginate(groups, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")
