"""
OCI Functions API Emulator
Applications + Functions CRUD, Docker-backed invocation.

API version: 20181201

Covered:
  Applications — create, get, list, update, delete
  Functions    — create, get, list, update, delete
  Invocations  — invoke (Docker, pay-per-call)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import docker
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    DEFAULT_OCI_COMPARTMENT, DEFAULT_OCI_REGION,
    etag_random, find_by_id, flag_resources_modified, get_resources,
    new_uuid, oci_error, oci_headers, ocid, paginate, remove_by_id, utcnow_iso,
)

router = APIRouter()
logger = logging.getLogger(__name__)

try:
    docker_client = docker.from_env()
except Exception:
    docker_client = None
    logger.warning("Docker not available — OCI Functions invoke will return mock responses")

_FN_PREFIX = "/20181201/functions"

# Runtime → Docker image mapping (reuse Lambda public images)
_RUNTIME_IMAGES = {
    "PYTHON_3_11": "public.ecr.aws/lambda/python:3.11",
    "PYTHON_3_9":  "public.ecr.aws/lambda/python:3.9",
    "NODE_18":     "public.ecr.aws/lambda/nodejs:18",
    "NODE_16":     "public.ecr.aws/lambda/nodejs:16",
    "JAVA_17":     "public.ecr.aws/lambda/java:17",
    "JAVA_11":     "public.ecr.aws/lambda/java:11",
    "GO_1_21":     "public.ecr.aws/lambda/go:1",
    "RUBY_3_2":    "public.ecr.aws/lambda/ruby:3.2",
}


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


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

@router.post(_FN_PREFIX + "/applications")
async def create_application(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_fn_applications", [])

    app_id = ocid("fnapp")
    app = {
        "id": app_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName"),
        "subnetIds": body.get("subnetIds", []),
        "config": body.get("config", {}),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "timeUpdated": utcnow_iso(),
    }
    resources["oci_fn_applications"].append(app)
    flag_resources_modified(db, env)
    return _ok(app, 200)


@router.get(_FN_PREFIX + "/applications")
async def list_applications(
    compartmentId: Optional[str] = None,
    displayName: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    apps = resources.get("oci_fn_applications", [])
    if displayName:
        apps = [a for a in apps if a.get("displayName") == displayName]
    items, next_page = paginate(apps, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_FN_PREFIX + "/applications/{application_id}")
async def get_application(application_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    app = find_by_id(resources.get("oci_fn_applications", []), "id", application_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return _ok(app)


@router.put(_FN_PREFIX + "/applications/{application_id}")
async def update_application(application_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    app = find_by_id(resources.get("oci_fn_applications", []), "id", application_id)
    if not app:
        raise HTTPException(404, "Application not found")
    for k in ("config", "subnetIds", "freeformTags", "definedTags"):
        if k in body:
            app[k] = body[k]
    app["timeUpdated"] = utcnow_iso()
    flag_resources_modified(db, env)
    return _ok(app)


@router.delete(_FN_PREFIX + "/applications/{application_id}")
async def delete_application(application_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    apps = resources.get("oci_fn_applications", [])
    if not remove_by_id(apps, "id", application_id):
        raise HTTPException(404, "Application not found")
    # Also remove associated functions
    resources["oci_fn_functions"] = [
        f for f in resources.get("oci_fn_functions", [])
        if f.get("applicationId") != application_id
    ]
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

@router.post(_FN_PREFIX + "/functions")
async def create_function(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_fn_functions", [])

    application_id = body.get("applicationId")
    app = find_by_id(resources.get("oci_fn_applications", []), "id", application_id)
    if not app:
        raise HTTPException(404, "Application not found")

    fn_id = ocid("fnfunc")
    image = body.get("image", "")
    # Store code zip if provided (base64)
    code_zip = body.get("codeBase64")

    fn = {
        "id": fn_id,
        "applicationId": application_id,
        "compartmentId": app.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName"),
        "image": image,
        "imageDigest": body.get("imageDigest", f"sha256:{uuid.uuid4().hex}"),
        "memoryInMBs": body.get("memoryInMBs", 256),
        "timeoutInSeconds": body.get("timeoutInSeconds", 30),
        "config": body.get("config", {}),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "timeUpdated": utcnow_iso(),
        "invokeEndpoint": (
            f"https://{fn_id}.{DEFAULT_OCI_REGION}.functions.oci.oraclecloud.com"
        ),
        # Internal: runtime detection + code storage
        "_runtime": body.get("runtime", "PYTHON_3_11"),
        "_codeBase64": code_zip,
    }
    resources["oci_fn_functions"].append(fn)
    flag_resources_modified(db, env)

    # Strip internal fields before returning
    public_fn = {k: v for k, v in fn.items() if not k.startswith("_")}
    return _ok(public_fn, 200)


@router.get(_FN_PREFIX + "/functions")
async def list_functions(
    applicationId: str,
    displayName: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    fns = [f for f in resources.get("oci_fn_functions", []) if f.get("applicationId") == applicationId]
    if displayName:
        fns = [f for f in fns if f.get("displayName") == displayName]
    # Strip internal fields
    fns = [{k: v for k, v in f.items() if not k.startswith("_")} for f in fns]
    items, next_page = paginate(fns, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_FN_PREFIX + "/functions/{function_id}")
async def get_function(function_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    fn = find_by_id(resources.get("oci_fn_functions", []), "id", function_id)
    if not fn:
        raise HTTPException(404, "Function not found")
    return _ok({k: v for k, v in fn.items() if not k.startswith("_")})


@router.put(_FN_PREFIX + "/functions/{function_id}")
async def update_function(function_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    fn = find_by_id(resources.get("oci_fn_functions", []), "id", function_id)
    if not fn:
        raise HTTPException(404, "Function not found")
    for k in ("image", "memoryInMBs", "timeoutInSeconds", "config", "freeformTags", "definedTags"):
        if k in body:
            fn[k] = body[k]
    if "runtime" in body:
        fn["_runtime"] = body["runtime"]
    if "codeBase64" in body:
        fn["_codeBase64"] = body["codeBase64"]
    fn["timeUpdated"] = utcnow_iso()
    flag_resources_modified(db, env)
    return _ok({k: v for k, v in fn.items() if not k.startswith("_")})


@router.delete(_FN_PREFIX + "/functions/{function_id}")
async def delete_function(function_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    fns = resources.get("oci_fn_functions", [])
    if not remove_by_id(fns, "id", function_id):
        raise HTTPException(404, "Function not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ---------------------------------------------------------------------------
# Invocations — Docker-backed
# ---------------------------------------------------------------------------

@router.post(_FN_PREFIX + "/functions/{function_id}/actions/invoke")
async def invoke_function(function_id: str, request: Request, db: Session = Depends(get_db)):
    """Invoke an OCI Function — runs in Docker, billed per invocation."""
    env = _env(request, db)
    resources = get_resources(env)
    fn = find_by_id(resources.get("oci_fn_functions", []), "id", function_id)
    if not fn:
        raise HTTPException(404, "Function not found")

    payload = await request.body()
    timeout = fn.get("timeoutInSeconds", 30)
    runtime = fn.get("_runtime", "PYTHON_3_11")
    code_b64 = fn.get("_codeBase64")
    env_vars = fn.get("config", {}).copy()
    start_ts = time.time()

    result_body = b""
    status_code = 200

    if docker_client and code_b64:
        try:
            code_bytes = base64.b64decode(code_b64)
            image = _RUNTIME_IMAGES.get(runtime, "public.ecr.aws/lambda/python:3.11")

            # Write code to temp volume via env var (small functions only)
            container = docker_client.containers.run(
                image=image,
                command=["python3", "-c", code_bytes.decode("utf-8", errors="replace")],
                environment={**env_vars, "OCI_FUNCTION_PAYLOAD": payload.decode("utf-8", errors="replace")},
                mem_limit=f"{fn.get('memoryInMBs', 256)}m",
                network_disabled=True,
                read_only=True,
                remove=True,
                detach=False,
                stdout=True,
                stderr=True,
                timeout=timeout,
            )
            result_body = container if isinstance(container, bytes) else b""
        except Exception as exc:
            logger.warning("OCI Function Docker invoke failed: %s", exc)
            status_code = 200
            result_body = json.dumps({"result": "mock", "function": fn.get("displayName"), "error": str(exc)}).encode()
    else:
        # No Docker or no code — return a realistic mock response
        result_body = json.dumps({
            "result": "mock",
            "function": fn.get("displayName"),
            "payload": payload.decode("utf-8", errors="replace"),
        }).encode()

    duration_ms = int((time.time() - start_ts) * 1000)

    return Response(
        content=result_body,
        status_code=status_code,
        headers={
            **oci_headers(),
            "fn-call-id": new_uuid(),
            "fn-execution-duration-in-ms": str(duration_ms),
        },
        media_type="application/json",
    )
