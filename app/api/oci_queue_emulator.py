"""
OCI Queue API Emulator
Backed by Redis lists — same pattern as the AWS SQS emulator.

API version: 20210201

Covered:
  Queues   — create, get, list, delete, purge
  Messages — put, get, delete, delete-all
"""
from __future__ import annotations

import json
import logging
import time
import uuid
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

_Q_PREFIX = "/20210201/queues"

try:
    import redis as _redis
    _redis_client = _redis.Redis(host="localhost", port=6379, db=1, decode_responses=True)
    _redis_client.ping()
except Exception:
    _redis_client = None
    logger.warning("Redis not available — OCI Queue will use in-memory fallback")

# In-memory fallback: {redis_key: [msg, ...]}
_mem_queues: dict[str, list] = {}


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


def _redis_push(key: str, data: str) -> None:
    if _redis_client:
        _redis_client.rpush(key, data)
    else:
        _mem_queues.setdefault(key, []).append(data)


def _redis_pop(key: str, count: int) -> list[str]:
    msgs = []
    if _redis_client:
        for _ in range(count):
            val = _redis_client.lpop(key)
            if val is None:
                break
            msgs.append(val)
    else:
        q = _mem_queues.get(key, [])
        while q and len(msgs) < count:
            msgs.append(q.pop(0))
    return msgs


def _redis_delete(key: str) -> None:
    if _redis_client:
        _redis_client.delete(key)
    else:
        _mem_queues.pop(key, None)


def _redis_len(key: str) -> int:
    if _redis_client:
        return _redis_client.llen(key)
    return len(_mem_queues.get(key, []))


# ---------------------------------------------------------------------------
# Queues — CRUD
# ---------------------------------------------------------------------------

@router.post(_Q_PREFIX)
async def create_queue(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_queues", [])

    display_name = body.get("displayName")
    if any(q["displayName"] == display_name for q in resources["oci_queues"]):
        raise HTTPException(409, f"Queue '{display_name}' already exists")

    queue_id = ocid("queue")
    redis_key = f"ociqueue:{env.id}:{queue_id}"

    queue = {
        "id": queue_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": display_name,
        "visibilityInSeconds": body.get("visibilityInSeconds", 30),
        "timeoutInSeconds": body.get("timeoutInSeconds", 30),
        "deadLetterQueueDeliveryCount": body.get("deadLetterQueueDeliveryCount", 5),
        "retentionInSeconds": body.get("retentionInSeconds", 86400),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "timeUpdated": utcnow_iso(),
        "messagesEndpoint": (
            f"https://cell-1.queue.messaging.{DEFAULT_OCI_REGION}.oci.oraclecloud.com"
        ),
        "_redisKey": redis_key,
    }
    resources["oci_queues"].append(queue)
    flag_resources_modified(db, env)
    return _ok({k: v for k, v in queue.items() if not k.startswith("_")}, 200)


@router.get(_Q_PREFIX)
async def list_queues(
    compartmentId: Optional[str] = None,
    displayName: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    queues = resources.get("oci_queues", [])
    if displayName:
        queues = [q for q in queues if q.get("displayName") == displayName]
    public = [{k: v for k, v in q.items() if not k.startswith("_")} for q in queues]
    items, next_page = paginate(public, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_Q_PREFIX + "/{queue_id}")
async def get_queue(queue_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    queue = find_by_id(resources.get("oci_queues", []), "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")
    return _ok({k: v for k, v in queue.items() if not k.startswith("_")})


@router.delete(_Q_PREFIX + "/{queue_id}")
async def delete_queue(queue_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    queues = resources.get("oci_queues", [])
    queue = find_by_id(queues, "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")
    _redis_delete(queue["_redisKey"])
    remove_by_id(queues, "id", queue_id)
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.post(_Q_PREFIX + "/{queue_id}/messages")
async def put_messages(queue_id: str, request: Request, db: Session = Depends(get_db)):
    """PUT messages into a queue — consumes Redis."""
    env = _env(request, db)
    resources = get_resources(env)
    queue = find_by_id(resources.get("oci_queues", []), "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")

    body = await request.json()
    messages = body.get("messages", [])
    entries = []

    for msg in messages:
        message_id = new_uuid()
        content = msg.get("content", "")
        stored = {
            "id": message_id,
            "content": content,
            "createdAt": utcnow_iso(),
            "visibleAfter": utcnow_iso(),
            "deliveryCount": 0,
        }
        _redis_push(queue["_redisKey"], json.dumps(stored))
        entries.append({
            "id": message_id,
            "md5OfContent": __import__("hashlib").md5(content.encode()).hexdigest(),
        })

    logger.info("OCI Queue put %d messages: %s", len(entries), queue.get("displayName"))
    return _ok({"messages": entries}, 200)


@router.get(_Q_PREFIX + "/{queue_id}/messages")
async def get_messages(
    queue_id: str,
    limit: int = 1,
    visibilityInSeconds: Optional[int] = None,
    timeoutInSeconds: Optional[int] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET messages from a queue — pops from Redis."""
    env = _env(request, db)
    resources = get_resources(env)
    queue = find_by_id(resources.get("oci_queues", []), "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")

    raw_msgs = _redis_pop(queue["_redisKey"], min(limit, 20))
    messages = []
    for raw in raw_msgs:
        stored = json.loads(raw)
        receipt = new_uuid()
        messages.append({
            "id": stored["id"],
            "content": stored.get("content", ""),
            "receipt": receipt,
            "deliveryCount": stored.get("deliveryCount", 0) + 1,
            "visibleAfter": utcnow_iso(),
            "createdAt": stored.get("createdAt", utcnow_iso()),
        })

    logger.info("OCI Queue got %d messages: %s", len(messages), queue.get("displayName"))
    return _ok({"messages": messages}, 200)


@router.delete(_Q_PREFIX + "/{queue_id}/messages/{receipt}")
async def delete_message(queue_id: str, receipt: str, request: Request, db: Session = Depends(get_db)):
    """Delete (acknowledge) a message by receipt handle."""
    env = _env(request, db)
    resources = get_resources(env)
    if not find_by_id(resources.get("oci_queues", []), "id", queue_id):
        raise HTTPException(404, "Queue not found")
    # Receipt-based deletion: message already popped from Redis on get
    return Response(status_code=204, headers=oci_headers())


@router.post(_Q_PREFIX + "/{queue_id}/messages/actions/deleteAllMessages")
async def purge_queue(queue_id: str, request: Request, db: Session = Depends(get_db)):
    """Delete all messages from a queue."""
    env = _env(request, db)
    resources = get_resources(env)
    queue = find_by_id(resources.get("oci_queues", []), "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")
    _redis_delete(queue["_redisKey"])
    logger.info("OCI Queue purged: %s", queue.get("displayName"))
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Queue stats
# ---------------------------------------------------------------------------

@router.get(_Q_PREFIX + "/{queue_id}/stats")
async def get_queue_stats(queue_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    queue = find_by_id(resources.get("oci_queues", []), "id", queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")
    count = _redis_len(queue["_redisKey"])
    return _ok({
        "queue": {
            "id": queue_id,
            "approximateMessagesVisible": count,
            "approximateMessagesVisibleExpired": 0,
            "approximateMessagesInFlight": 0,
            "timeOfOldestMessage": None,
        }
    })
