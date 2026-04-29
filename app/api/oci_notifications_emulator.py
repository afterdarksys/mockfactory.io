"""
OCI Notifications Service (ONS) Emulator
Topics + Subscriptions CRUD, publish messages via Redis pub/sub.

API versions:
  20181201 — Topics, Subscriptions, Publish

Covered:
  Topics        — create, get, list, delete
  Subscriptions — create, get, list, delete, get-unsubscribe-url
  Publish       — publish message to topic (fanout to subscribers)
"""
from __future__ import annotations

import json
import logging
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

_ONS_PREFIX = "/20181201"

try:
    import redis as _redis
    _redis_client = _redis.Redis(host="localhost", port=6379, db=3, decode_responses=True)
    _redis_client.ping()
    _HAS_REDIS = True
except Exception:
    _redis_client = None
    _HAS_REDIS = False
    logger.warning("Redis not available — ONS publish will be logged only")


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


def _topic_arn(compartment_id: str, topic_name: str, region: str = DEFAULT_OCI_REGION) -> str:
    return f"ocid1.onstopic.oc1.{region}.{topic_name.lower().replace(' ', '-')}"


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

@router.post(_ONS_PREFIX + "/topics")
async def create_topic(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_ons_topics", [])

    name = body.get("name")
    if any(t["name"] == name for t in resources["oci_ons_topics"]):
        raise HTTPException(409, f"Topic '{name}' already exists")

    topic_id = ocid("onstopic")
    topic = {
        "topicId": topic_id,
        "name": name,
        "description": body.get("description", ""),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "etag": new_uuid(),
        "apiEndpoint": (
            f"https://cell-1.notification.{DEFAULT_OCI_REGION}.oci.oraclecloud.com/"
            f"20181201/topics/{topic_id}/messages"
        ),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
    }
    resources["oci_ons_topics"].append(topic)
    flag_resources_modified(db, env)
    logger.info("Created ONS topic: %s", name)
    return _ok(topic, 200)


@router.get(_ONS_PREFIX + "/topics")
async def list_topics(
    compartmentId: Optional[str] = None,
    name: Optional[str] = None,
    lifecycleState: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    topics = resources.get("oci_ons_topics", [])
    if name:
        topics = [t for t in topics if t.get("name") == name]
    if lifecycleState:
        topics = [t for t in topics if t.get("lifecycleState") == lifecycleState]
    items, next_page = paginate(topics, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_ONS_PREFIX + "/topics/{topic_id}")
async def get_topic(topic_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    topic = find_by_id(resources.get("oci_ons_topics", []), "topicId", topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    return _ok(topic)


@router.put(_ONS_PREFIX + "/topics/{topic_id}")
async def update_topic(topic_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    topic = find_by_id(resources.get("oci_ons_topics", []), "topicId", topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    for k in ("description", "freeformTags", "definedTags"):
        if k in body:
            topic[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(topic)


@router.delete(_ONS_PREFIX + "/topics/{topic_id}")
async def delete_topic(topic_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    topics = resources.get("oci_ons_topics", [])
    if not remove_by_id(topics, "topicId", topic_id):
        raise HTTPException(404, "Topic not found")
    # Remove associated subscriptions
    resources["oci_ons_subscriptions"] = [
        s for s in resources.get("oci_ons_subscriptions", [])
        if s.get("topicId") != topic_id
    ]
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@router.post(_ONS_PREFIX + "/topics/{topic_id}/messages")
async def publish_message(topic_id: str, request: Request, db: Session = Depends(get_db)):
    """Publish a message to an ONS topic — fan-out to all subscribers."""
    env = _env(request, db)
    resources = get_resources(env)
    topic = find_by_id(resources.get("oci_ons_topics", []), "topicId", topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")

    body = await request.json()
    title = body.get("title", "")
    body_text = body.get("body", "")
    message_type = body.get("messageType", "RAW_TEXT")  # RAW_TEXT | JSON

    message_id = new_uuid()

    # Fan-out: publish to Redis channel for each subscriber
    subscriptions = [
        s for s in resources.get("oci_ons_subscriptions", [])
        if s.get("topicId") == topic_id and s.get("lifecycleState") == "ACTIVE"
    ]

    delivered = 0
    for sub in subscriptions:
        protocol = sub.get("protocol", "")
        endpoint = sub.get("endpoint", "")
        channel = f"ons:{env.id}:{topic_id}:{sub['id']}"

        payload = json.dumps({
            "messageId": message_id,
            "title": title,
            "body": body_text,
            "type": message_type,
            "topicId": topic_id,
            "subscriptionId": sub["id"],
            "protocol": protocol,
            "endpoint": endpoint,
            "timestamp": utcnow_iso(),
        })

        if _HAS_REDIS and _redis_client:
            _redis_client.publish(channel, payload)
            # Also push to a list for polling-style consumers
            _redis_client.rpush(f"ons:inbox:{env.id}:{sub['id']}", payload)
        delivered += 1

    logger.info(
        "ONS published to topic %s — %d subscribers, messageId=%s",
        topic.get("name"), delivered, message_id,
    )

    return _ok({
        "messageId": message_id,
        "timeStamp": utcnow_iso(),
    }, 202)


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

@router.post(_ONS_PREFIX + "/subscriptions")
async def create_subscription(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_ons_subscriptions", [])

    topic_id = body.get("topicId")
    if not find_by_id(resources.get("oci_ons_topics", []), "topicId", topic_id):
        raise HTTPException(404, "Topic not found")

    sub_id = ocid("onssubscription")
    sub = {
        "id": sub_id,
        "topicId": topic_id,
        "protocol": body.get("protocol", "EMAIL"),   # EMAIL | HTTPS | SLACK | PAGERDUTY | ORACLE_FUNCTIONS | SMS
        "endpoint": body.get("endpoint", ""),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "createdTime": utcnow_iso(),
        "etag": new_uuid(),
        "lifecycleState": "ACTIVE",
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "deliveryPolicy": body.get("deliveryPolicy", {}),
    }
    resources["oci_ons_subscriptions"].append(sub)
    flag_resources_modified(db, env)
    return _ok(sub, 200)


@router.get(_ONS_PREFIX + "/subscriptions")
async def list_subscriptions(
    compartmentId: Optional[str] = None,
    topicId: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    subs = resources.get("oci_ons_subscriptions", [])
    if topicId:
        subs = [s for s in subs if s.get("topicId") == topicId]
    items, next_page = paginate(subs, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_ONS_PREFIX + "/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    sub = find_by_id(resources.get("oci_ons_subscriptions", []), "id", subscription_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    return _ok(sub)


@router.delete(_ONS_PREFIX + "/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    subs = resources.get("oci_ons_subscriptions", [])
    if not remove_by_id(subs, "id", subscription_id):
        raise HTTPException(404, "Subscription not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get(_ONS_PREFIX + "/subscriptions/{subscription_id}/unsubscribeUrl")
async def get_unsubscribe_url(subscription_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    sub = find_by_id(resources.get("oci_ons_subscriptions", []), "id", subscription_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    return _ok({
        "url": (
            f"https://cell-1.notification.{DEFAULT_OCI_REGION}.oci.oraclecloud.com/"
            f"20181201/subscriptions/{subscription_id}/unsubscription"
            f"?token=mock-unsubscribe-token-{subscription_id}"
        )
    })


# ---------------------------------------------------------------------------
# Inbox poll (non-standard — lets test code pull published messages)
# ---------------------------------------------------------------------------

@router.get(_ONS_PREFIX + "/subscriptions/{subscription_id}/inbox")
async def poll_inbox(
    subscription_id: str,
    limit: int = 10,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Non-standard helper: poll messages delivered to a subscription inbox (Redis list)."""
    env = _env(request, db)
    resources = get_resources(env)
    if not find_by_id(resources.get("oci_ons_subscriptions", []), "id", subscription_id):
        raise HTTPException(404, "Subscription not found")

    inbox_key = f"ons:inbox:{env.id}:{subscription_id}"
    messages = []

    if _HAS_REDIS and _redis_client:
        for _ in range(min(limit, 100)):
            raw = _redis_client.lpop(inbox_key)
            if raw is None:
                break
            messages.append(json.loads(raw))

    return _ok({"messages": messages})
