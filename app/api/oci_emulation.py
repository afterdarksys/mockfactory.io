"""
OCI (Oracle Cloud Infrastructure) API Emulation
Exposes realistic OCI REST APIs backed by local Docker / MinIO infrastructure.

Covered services:
  - Object Storage  — namespace, buckets, objects, pre-authenticated requests
  - Compute         — instances, shapes, images, lifecycle actions
  - Networking (VCN) — VCNs, subnets, internet gateways, route tables, security lists
  - Identity (IAM)  — compartments, users, groups, policies, API keys
  - Block Volume    — volumes, volume attachments, backups
  - Container Registry (OCIR) — repositories, images, tags
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    DEFAULT_OCI_COMPARTMENT, DEFAULT_OCI_NAMESPACE, DEFAULT_OCI_REGION,
    DEFAULT_OCI_TENANCY,
    etag_from_content, etag_random, find_by_id, flag_resources_modified,
    get_resources, new_uuid, oci_error, oci_headers, oci_request_id,
    ocid, paginate, remove_by_id, utcnow_iso, utcnow_rfc1123, random_private_ip,
    random_public_ip,
)


router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _s3() -> boto3.client:
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("MINIO_ROOT_USER", "mockfactory"),
        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "mockfactory123"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


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


def _ok(body: dict, status: int = 200, etag: Optional[str] = None,
        extra_headers: Optional[dict] = None) -> Response:
    h = oci_headers(etag=etag)
    if extra_headers:
        h.update(extra_headers)
    return Response(
        content=json.dumps(body),
        status_code=status,
        headers=h,
        media_type="application/json",
    )


def _oci_instance_shape_config(shape: str) -> dict:
    configs = {
        "VM.Standard.E4.Flex":  {"ocpus": 1, "memoryInGBs": 16},
        "VM.Standard3.Flex":    {"ocpus": 1, "memoryInGBs": 16},
        "VM.Standard.E3.Flex":  {"ocpus": 1, "memoryInGBs": 16},
        "VM.Standard2.1":       {"ocpus": 1, "memoryInGBs": 15},
        "BM.Standard3.64":      {"ocpus": 64, "memoryInGBs": 1024},
        "BM.HPC2.36":           {"ocpus": 36, "memoryInGBs": 384},
    }
    return configs.get(shape, {"ocpus": 1, "memoryInGBs": 16})


# ============================================================================
# OCI Object Storage — namespace + buckets + objects + pre-auth requests
# ============================================================================

@router.get("/n")
async def get_namespace(request: Request, db: Session = Depends(get_db)):
    """GET /n — return the object storage namespace for this environment."""
    env = _env(request, db)
    return _ok({"value": f"mf-{env.id}"})


@router.get("/n/{namespace}/b")
async def list_buckets(
    namespace: str,
    compartmentId: Optional[str] = None,
    limit: int = 100,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET /n/{namespace}/b — list OCI buckets for this environment."""
    env = _env(request, db)
    resources = get_resources(env)
    buckets = resources.get("oci_buckets", [])
    page_items, next_page = paginate(buckets, page, limit)

    headers = oci_headers()
    if next_page:
        headers["opc-next-page"] = next_page

    return Response(
        content=json.dumps(page_items),
        status_code=200,
        headers=headers,
        media_type="application/json",
    )


@router.post("/n/{namespace}/b")
async def create_bucket(
    namespace: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """POST /n/{namespace}/b — create an OCI object storage bucket."""
    env = _env(request, db)
    body = await request.json()
    name = body.get("name")
    if not name:
        raise HTTPException(400, "name required")

    resources = get_resources(env)
    if "oci_buckets" not in resources:
        resources["oci_buckets"] = []

    if any(b["name"] == name for b in resources["oci_buckets"]):
        raise HTTPException(409, f"Bucket '{name}' already exists")

    minio_bucket = f"env-{env.id}-oci-{name.lower().replace(' ', '-')[:40]}"
    s3 = _s3()
    try:
        s3.create_bucket(Bucket=minio_bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise HTTPException(500, f"Storage backend error: {e}")

    et = etag_random()
    bucket_record = {
        "name": name,
        "namespace": namespace,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "createdBy": DEFAULT_OCI_TENANCY,
        "timeCreated": utcnow_iso(),
        "etag": et,
        "storageTier": body.get("storageTier", "Standard"),
        "objectLifecyclePolicyEtag": None,
        "metadata": body.get("metadata", {}),
        "isReadPublic": body.get("publicAccessType", "NoPublicAccess") != "NoPublicAccess",
        "approximateCount": 0,
        "approximateSize": 0,
        "_minio_bucket": minio_bucket,
    }
    resources["oci_buckets"].append(bucket_record)
    flag_resources_modified(db, env)

    return _ok(bucket_record, status=200, etag=et)


@router.get("/n/{namespace}/b/{bucket_name}")
async def get_bucket(
    namespace: str, bucket_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """HEAD/GET /n/{namespace}/b/{bucket} — bucket details."""
    env = _env(request, db)
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")
    return _ok(bucket, etag=bucket.get("etag"))


@router.delete("/n/{namespace}/b/{bucket_name}")
async def delete_bucket(
    namespace: str, bucket_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """DELETE /n/{namespace}/b/{bucket} — delete an OCI bucket."""
    env = _env(request, db)
    resources = get_resources(env)
    buckets = resources.get("oci_buckets", [])
    bucket = find_by_id(buckets, "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    s3 = _s3()
    minio_bucket = bucket.get("_minio_bucket", "")
    if minio_bucket:
        try:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=minio_bucket):
                objs = page.get("Contents", [])
                if objs:
                    s3.delete_objects(
                        Bucket=minio_bucket,
                        Delete={"Objects": [{"Key": o["Key"]} for o in objs]},
                    )
            s3.delete_bucket(Bucket=minio_bucket)
        except ClientError:
            pass

    remove_by_id(buckets, "name", bucket_name)
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# --- Objects ---

@router.get("/n/{namespace}/b/{bucket_name}/o")
async def list_objects(
    namespace: str, bucket_name: str,
    prefix: Optional[str] = None,
    delimiter: Optional[str] = None,
    limit: int = 1000,
    page: Optional[str] = None,
    fields: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET /n/{namespace}/b/{bucket}/o — list objects."""
    env = _env(request, db)
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    s3 = _s3()
    minio_bucket = bucket["_minio_bucket"]

    kwargs: dict = {"Bucket": minio_bucket, "MaxKeys": limit}
    if prefix:
        kwargs["Prefix"] = prefix
    if delimiter:
        kwargs["Delimiter"] = delimiter
    if page:
        kwargs["ContinuationToken"] = page

    try:
        resp = s3.list_objects_v2(**kwargs)
    except ClientError as e:
        raise HTTPException(500, str(e))

    objects = [
        {
            "name": o["Key"],
            "size": o["Size"],
            "md5": o.get("ETag", "").strip('"'),
            "timeCreated": o["LastModified"].isoformat(),
            "timeModified": o["LastModified"].isoformat(),
            "storageTier": "Standard",
            "etag": o.get("ETag", "").strip('"'),
        }
        for o in resp.get("Contents", [])
    ]

    result: dict = {"objects": objects}
    if resp.get("NextContinuationToken"):
        result["nextStartWith"] = resp["NextContinuationToken"]
    if resp.get("CommonPrefixes"):
        result["prefixes"] = [p["Prefix"] for p in resp["CommonPrefixes"]]

    return _ok(result)


@router.put("/n/{namespace}/b/{bucket_name}/o/{object_name:path}")
async def put_object(
    namespace: str, bucket_name: str, object_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """PUT /n/{namespace}/b/{bucket}/o/{object} — upload an object."""
    env = _env(request, db)
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    content = await request.body()
    ct = request.headers.get("content-type", "application/octet-stream")
    et = etag_from_content(content)

    s3 = _s3()
    try:
        s3.put_object(
            Bucket=bucket["_minio_bucket"],
            Key=object_name,
            Body=content,
            ContentType=ct,
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    bucket["approximateCount"] = bucket.get("approximateCount", 0) + 1
    bucket["approximateSize"] = bucket.get("approximateSize", 0) + len(content)
    flag_resources_modified(db, env)

    return Response(
        status_code=200,
        headers=oci_headers(etag=et, extra={
            "Content-MD5": et,
            "Last-Modified": utcnow_rfc1123(),
        }),
    )


@router.get("/n/{namespace}/b/{bucket_name}/o/{object_name:path}")
async def get_object(
    namespace: str, bucket_name: str, object_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """GET /n/{namespace}/b/{bucket}/o/{object} — download an object."""
    env = _env(request, db)
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    s3 = _s3()
    try:
        resp = s3.get_object(Bucket=bucket["_minio_bucket"], Key=object_name)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(404, f"Object '{object_name}' not found")
        raise HTTPException(500, str(e))

    return StreamingResponse(
        resp["Body"],
        media_type=resp.get("ContentType", "application/octet-stream"),
        headers={"ETag": resp.get("ETag", ""), "Last-Modified": utcnow_rfc1123()},
    )


@router.delete("/n/{namespace}/b/{bucket_name}/o/{object_name:path}")
async def delete_object(
    namespace: str, bucket_name: str, object_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """DELETE /n/{namespace}/b/{bucket}/o/{object} — delete an object."""
    env = _env(request, db)
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    s3 = _s3()
    try:
        s3.delete_object(Bucket=bucket["_minio_bucket"], Key=object_name)
    except ClientError as e:
        raise HTTPException(500, str(e))

    return Response(status_code=204, headers=oci_headers())


# --- Pre-authenticated requests ---

@router.post("/n/{namespace}/b/{bucket_name}/p")
async def create_preauthenticated_request(
    namespace: str, bucket_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """POST /n/{namespace}/b/{bucket}/p — create a pre-authenticated request."""
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    bucket = find_by_id(resources.get("oci_buckets", []), "name", bucket_name)
    if not bucket:
        raise HTTPException(404, f"Bucket '{bucket_name}' not found")

    par_id = ocid("preauthrequest")
    access_uri = f"/p/{new_uuid()}/n/{namespace}/b/{bucket_name}/o/"
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    par = {
        "id": par_id,
        "name": body.get("name", f"par-{par_id[-8:]}"),
        "accessType": body.get("accessType", "ObjectRead"),
        "objectName": body.get("objectName"),
        "bucketListingAction": body.get("bucketListingAction"),
        "accessUri": access_uri,
        "fullPath": f"https://objectstorage.{DEFAULT_OCI_REGION}.oraclecloud.com{access_uri}",
        "timeCreated": utcnow_iso(),
        "timeExpires": body.get("timeExpires", expires),
    }

    if "oci_pars" not in resources:
        resources["oci_pars"] = {}
    if bucket_name not in resources["oci_pars"]:
        resources["oci_pars"][bucket_name] = []
    resources["oci_pars"][bucket_name].append(par)
    flag_resources_modified(db, env)

    return _ok(par, status=200)


@router.get("/n/{namespace}/b/{bucket_name}/p")
async def list_preauthenticated_requests(
    namespace: str, bucket_name: str,
    request: Request, db: Session = Depends(get_db),
):
    """GET /n/{namespace}/b/{bucket}/p — list pre-authenticated requests."""
    env = _env(request, db)
    resources = get_resources(env)
    pars = resources.get("oci_pars", {}).get(bucket_name, [])
    return _ok(pars)


# ============================================================================
# OCI Compute — instances, shapes, images, lifecycle
# ============================================================================

SHAPES_CATALOG = [
    {"shape": "VM.Standard.E4.Flex", "ocpus": 1, "memoryInGBs": 16, "processorDescription": "AMD EPYC"},
    {"shape": "VM.Standard3.Flex", "ocpus": 1, "memoryInGBs": 16, "processorDescription": "Intel Xeon"},
    {"shape": "VM.Standard.E3.Flex", "ocpus": 1, "memoryInGBs": 16, "processorDescription": "AMD EPYC Rome"},
    {"shape": "VM.Standard2.1", "ocpus": 1, "memoryInGBs": 15, "processorDescription": "Intel Xeon"},
    {"shape": "VM.Standard2.2", "ocpus": 2, "memoryInGBs": 30, "processorDescription": "Intel Xeon"},
    {"shape": "VM.Standard2.4", "ocpus": 4, "memoryInGBs": 60, "processorDescription": "Intel Xeon"},
    {"shape": "BM.Standard3.64", "ocpus": 64, "memoryInGBs": 1024, "processorDescription": "Intel Xeon"},
    {"shape": "BM.HPC2.36", "ocpus": 36, "memoryInGBs": 384, "processorDescription": "Intel Xeon Gold"},
]

IMAGES_CATALOG = [
    {"id": ocid("image"), "displayName": "Oracle Linux 8", "operatingSystem": "Oracle Linux", "operatingSystemVersion": "8", "lifecycleState": "AVAILABLE"},
    {"id": ocid("image"), "displayName": "Oracle Linux 9", "operatingSystem": "Oracle Linux", "operatingSystemVersion": "9", "lifecycleState": "AVAILABLE"},
    {"id": ocid("image"), "displayName": "Ubuntu 22.04", "operatingSystem": "Canonical Ubuntu", "operatingSystemVersion": "22.04", "lifecycleState": "AVAILABLE"},
    {"id": ocid("image"), "displayName": "Ubuntu 20.04", "operatingSystem": "Canonical Ubuntu", "operatingSystemVersion": "20.04", "lifecycleState": "AVAILABLE"},
    {"id": ocid("image"), "displayName": "CentOS Stream 9", "operatingSystem": "CentOS", "operatingSystemVersion": "Stream 9", "lifecycleState": "AVAILABLE"},
    {"id": ocid("image"), "displayName": "Windows Server 2022 Standard", "operatingSystem": "Windows", "operatingSystemVersion": "Server 2022 Standard", "lifecycleState": "AVAILABLE"},
]


@router.get("/20160918/shapes")
async def list_shapes(
    compartmentId: Optional[str] = None,
    imageId: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET /20160918/shapes — list available compute shapes."""
    env = _env(request, db)
    return _ok({"items": SHAPES_CATALOG})


@router.get("/20160918/images")
async def list_images(
    compartmentId: Optional[str] = None,
    operatingSystem: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET /20160918/images — list available OS images."""
    env = _env(request, db)
    images = IMAGES_CATALOG
    if operatingSystem:
        images = [i for i in images if operatingSystem.lower() in i["operatingSystem"].lower()]
    return _ok({"items": images})


@router.post("/20160918/instances")
async def launch_instance(
    request: Request, db: Session = Depends(get_db),
):
    """POST /20160918/instances — launch a compute instance."""
    env = _env(request, db)
    body = await request.json()

    shape = body.get("shape", "VM.Standard.E4.Flex")
    shape_cfg = _oci_instance_shape_config(shape)
    if body.get("shapeConfig"):
        shape_cfg.update(body["shapeConfig"])

    instance_id = ocid("instance")
    resources = get_resources(env)
    if "oci_instances" not in resources:
        resources["oci_instances"] = []

    private_ip = random_private_ip(len(resources["oci_instances"]))
    public_ip = random_public_ip()

    instance = {
        "id": instance_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "availabilityDomain": body.get("availabilityDomain", "US-ASHBURN-AD-1"),
        "displayName": body.get("displayName", f"instance-{instance_id[-8:]}"),
        "shape": shape,
        "shapeConfig": shape_cfg,
        "imageId": body.get("sourceDetails", {}).get("imageId", IMAGES_CATALOG[0]["id"]),
        "lifecycleState": "PROVISIONING",
        "timeCreated": utcnow_iso(),
        "region": DEFAULT_OCI_REGION,
        "faultDomain": "FAULT-DOMAIN-1",
        "metadata": body.get("metadata", {}),
        "extendedMetadata": body.get("extendedMetadata", {}),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "primaryPrivateIp": private_ip,
        "primaryPublicIp": public_ip,
        "hostname": body.get("displayName", f"instance-{instance_id[-8:]}").lower(),
    }
    resources["oci_instances"].append(instance)
    flag_resources_modified(db, env)

    # Simulate PROVISIONING → RUNNING transition in response
    instance["lifecycleState"] = "RUNNING"
    return _ok(instance, status=200, etag=etag_random())


@router.get("/20160918/instances")
async def list_instances(
    compartmentId: Optional[str] = None,
    lifecycleState: Optional[str] = None,
    limit: int = 100,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """GET /20160918/instances — list compute instances."""
    env = _env(request, db)
    resources = get_resources(env)
    instances = resources.get("oci_instances", [])
    if lifecycleState:
        instances = [i for i in instances if i["lifecycleState"] == lifecycleState]
    page_items, next_page = paginate(instances, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": page_items}), headers=h, media_type="application/json")


@router.get("/20160918/instances/{instance_id}")
async def get_instance(
    instance_id: str, request: Request, db: Session = Depends(get_db),
):
    """GET /20160918/instances/{id} — get instance details."""
    env = _env(request, db)
    resources = get_resources(env)
    inst = find_by_id(resources.get("oci_instances", []), "id", instance_id)
    if not inst:
        raise HTTPException(404, f"Instance '{instance_id}' not found")
    return _ok(inst, etag=etag_random())


@router.post("/20160918/instances/{instance_id}/actions/stop")
async def stop_instance(
    instance_id: str, request: Request, db: Session = Depends(get_db),
):
    """POST /20160918/instances/{id}/actions/stop"""
    env = _env(request, db)
    resources = get_resources(env)
    inst = find_by_id(resources.get("oci_instances", []), "id", instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    inst["lifecycleState"] = "STOPPED"
    flag_resources_modified(db, env)
    return _ok(inst)


@router.post("/20160918/instances/{instance_id}/actions/start")
async def start_instance(
    instance_id: str, request: Request, db: Session = Depends(get_db),
):
    """POST /20160918/instances/{id}/actions/start"""
    env = _env(request, db)
    resources = get_resources(env)
    inst = find_by_id(resources.get("oci_instances", []), "id", instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    inst["lifecycleState"] = "RUNNING"
    flag_resources_modified(db, env)
    return _ok(inst)


@router.post("/20160918/instances/{instance_id}/actions/reset")
async def reset_instance(
    instance_id: str, request: Request, db: Session = Depends(get_db),
):
    """POST /20160918/instances/{id}/actions/reset — hard reboot."""
    env = _env(request, db)
    resources = get_resources(env)
    inst = find_by_id(resources.get("oci_instances", []), "id", instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    inst["lifecycleState"] = "RUNNING"
    flag_resources_modified(db, env)
    return _ok(inst)


@router.delete("/20160918/instances/{instance_id}")
async def terminate_instance(
    instance_id: str,
    preserveBootVolume: bool = False,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """DELETE /20160918/instances/{id} — terminate an instance."""
    env = _env(request, db)
    resources = get_resources(env)
    instances = resources.get("oci_instances", [])
    inst = find_by_id(instances, "id", instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    inst["lifecycleState"] = "TERMINATING"
    remove_by_id(instances, "id", instance_id)
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ============================================================================
# OCI Networking (VCN) — VCNs, subnets, internet gateways, route tables
# ============================================================================

@router.post("/20160918/vcns")
async def create_vcn(request: Request, db: Session = Depends(get_db)):
    """POST /20160918/vcns — create a Virtual Cloud Network."""
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_vcns" not in resources:
        resources["oci_vcns"] = []

    vcn_id = ocid("vcn")
    vcn = {
        "id": vcn_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"vcn-{vcn_id[-8:]}"),
        "cidrBlock": body.get("cidrBlock", "10.0.0.0/16"),
        "cidrBlocks": body.get("cidrBlocks", [body.get("cidrBlock", "10.0.0.0/16")]),
        "dnsLabel": body.get("dnsLabel", f"vcn{vcn_id[-4:]}"),
        "vcnDomainName": f"{body.get('dnsLabel', 'vcn')}.oraclevcn.com",
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
        "freeformTags": body.get("freeformTags", {}),
        "defaultRouteTableId": ocid("routetable"),
        "defaultSecurityListId": ocid("securitylist"),
        "defaultDhcpOptionsId": ocid("dhcpoptions"),
    }
    resources["oci_vcns"].append(vcn)
    flag_resources_modified(db, env)
    return _ok(vcn, status=200, etag=etag_random())


@router.get("/20160918/vcns")
async def list_vcns(
    compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    vcns = resources.get("oci_vcns", [])
    items, next_page = paginate(vcns, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/vcns/{vcn_id}")
async def get_vcn(vcn_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    vcn = find_by_id(resources.get("oci_vcns", []), "id", vcn_id)
    if not vcn:
        raise HTTPException(404, "VCN not found")
    return _ok(vcn, etag=etag_random())


@router.delete("/20160918/vcns/{vcn_id}")
async def delete_vcn(vcn_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    vcns = resources.get("oci_vcns", [])
    if not remove_by_id(vcns, "id", vcn_id):
        raise HTTPException(404, "VCN not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.post("/20160918/subnets")
async def create_subnet(request: Request, db: Session = Depends(get_db)):
    """POST /20160918/subnets — create a subnet inside a VCN."""
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_subnets" not in resources:
        resources["oci_subnets"] = []

    idx = len(resources["oci_subnets"])
    subnet_id = ocid("subnet")
    subnet = {
        "id": subnet_id,
        "vcnId": body.get("vcnId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"subnet-{subnet_id[-8:]}"),
        "cidrBlock": body.get("cidrBlock", f"10.0.{idx}.0/24"),
        "availabilityDomain": body.get("availabilityDomain", "US-ASHBURN-AD-1"),
        "dnsLabel": body.get("dnsLabel", f"sub{idx}"),
        "subnetDomainName": f"sub{idx}.vcn.oraclevcn.com",
        "lifecycleState": "AVAILABLE",
        "prohibitInternetIngress": body.get("prohibitInternetIngress", False),
        "prohibitPublicIpOnVnic": body.get("prohibitPublicIpOnVnic", False),
        "timeCreated": utcnow_iso(),
        "routeTableId": body.get("routeTableId", ocid("routetable")),
        "securityListIds": body.get("securityListIds", [ocid("securitylist")]),
        "virtualRouterIp": f"10.0.{idx}.1",
        "virtualRouterMac": "00:00:00:00:00:01",
    }
    resources["oci_subnets"].append(subnet)
    flag_resources_modified(db, env)
    return _ok(subnet, status=200, etag=etag_random())


@router.get("/20160918/subnets")
async def list_subnets(
    vcnId: Optional[str] = None, compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    subnets = resources.get("oci_subnets", [])
    if vcnId:
        subnets = [s for s in subnets if s.get("vcnId") == vcnId]
    items, next_page = paginate(subnets, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.post("/20160918/internetGateways")
async def create_internet_gateway(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_igws" not in resources:
        resources["oci_igws"] = []

    igw_id = ocid("internetgateway")
    igw = {
        "id": igw_id,
        "vcnId": body.get("vcnId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"igw-{igw_id[-8:]}"),
        "isEnabled": body.get("isEnabled", True),
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
    }
    resources["oci_igws"].append(igw)
    flag_resources_modified(db, env)
    return _ok(igw, status=200)


@router.post("/20160918/routeTables")
async def create_route_table(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_route_tables" not in resources:
        resources["oci_route_tables"] = []

    rt_id = ocid("routetable")
    rt = {
        "id": rt_id,
        "vcnId": body.get("vcnId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"rt-{rt_id[-8:]}"),
        "routeRules": body.get("routeRules", []),
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
    }
    resources["oci_route_tables"].append(rt)
    flag_resources_modified(db, env)
    return _ok(rt, status=200)


@router.post("/20160918/securityLists")
async def create_security_list(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_security_lists" not in resources:
        resources["oci_security_lists"] = []

    sl_id = ocid("securitylist")
    sl = {
        "id": sl_id,
        "vcnId": body.get("vcnId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"sl-{sl_id[-8:]}"),
        "egressSecurityRules": body.get("egressSecurityRules", [
            {"destination": "0.0.0.0/0", "protocol": "all", "isStateless": False}
        ]),
        "ingressSecurityRules": body.get("ingressSecurityRules", [
            {"source": "0.0.0.0/0", "protocol": "6", "isStateless": False,
             "tcpOptions": {"destinationPortRange": {"min": 22, "max": 22}}}
        ]),
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
    }
    resources["oci_security_lists"].append(sl)
    flag_resources_modified(db, env)
    return _ok(sl, status=200)


# ============================================================================
# OCI Identity (IAM) — compartments, users, groups, policies, API keys
# ============================================================================

@router.get("/20160918/tenancy")
async def get_tenancy(request: Request, db: Session = Depends(get_db)):
    """GET /20160918/tenancy — get tenancy details."""
    env = _env(request, db)
    return _ok({
        "id": DEFAULT_OCI_TENANCY,
        "name": f"mockfactory-{env.id}",
        "description": "MockFactory emulated tenancy",
        "homeRegionKey": "IAD",
        "upiIdcsCompatibilityLayerEndpoint": None,
        "freeformTags": {},
        "definedTags": {},
    })


@router.post("/20160918/compartments")
async def create_compartment(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_compartments" not in resources:
        resources["oci_compartments"] = []

    cmp_id = ocid("compartment")
    cmp = {
        "id": cmp_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "name": body.get("name"),
        "description": body.get("description", ""),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "isAccessible": True,
    }
    resources["oci_compartments"].append(cmp)
    flag_resources_modified(db, env)
    return _ok(cmp, status=200)


@router.get("/20160918/compartments")
async def list_compartments(
    compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    cmps = resources.get("oci_compartments", [])
    items, next_page = paginate(cmps, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.post("/20160918/users")
async def create_user(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_users" not in resources:
        resources["oci_users"] = []

    user_id = ocid("user")
    user = {
        "id": user_id,
        "compartmentId": DEFAULT_OCI_TENANCY,
        "name": body.get("name"),
        "description": body.get("description", ""),
        "email": body.get("email"),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "isMfaActivated": False,
        "freeformTags": body.get("freeformTags", {}),
    }
    resources["oci_users"].append(user)
    flag_resources_modified(db, env)
    return _ok(user, status=200)


@router.get("/20160918/users")
async def list_users(
    compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    users = resources.get("oci_users", [])
    items, next_page = paginate(users, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.post("/20160918/groups")
async def create_group(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_groups" not in resources:
        resources["oci_groups"] = []

    group_id = ocid("group")
    group = {
        "id": group_id,
        "compartmentId": DEFAULT_OCI_TENANCY,
        "name": body.get("name"),
        "description": body.get("description", ""),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "freeformTags": body.get("freeformTags", {}),
    }
    resources["oci_groups"].append(group)
    flag_resources_modified(db, env)
    return _ok(group, status=200)


@router.post("/20160918/policies")
async def create_policy(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_policies" not in resources:
        resources["oci_policies"] = []

    policy_id = ocid("policy")
    policy = {
        "id": policy_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "name": body.get("name"),
        "description": body.get("description", ""),
        "statements": body.get("statements", []),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "freeformTags": body.get("freeformTags", {}),
    }
    resources["oci_policies"].append(policy)
    flag_resources_modified(db, env)
    return _ok(policy, status=200)


@router.post("/20160918/users/{user_id}/apiKeys")
async def upload_api_key(
    user_id: str, request: Request, db: Session = Depends(get_db),
):
    """POST /20160918/users/{id}/apiKeys — upload a public API key."""
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)

    fingerprint = ":".join([
        f"{ocid('x')[-2:]}" for _ in range(16)
    ])[:47]

    key = {
        "userId": user_id,
        "keyId": f"{DEFAULT_OCI_TENANCY}/{user_id}/{fingerprint}",
        "fingerprint": fingerprint,
        "publicKey": body.get("key", ""),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
    }

    if "oci_api_keys" not in resources:
        resources["oci_api_keys"] = {}
    if user_id not in resources["oci_api_keys"]:
        resources["oci_api_keys"][user_id] = []
    resources["oci_api_keys"][user_id].append(key)
    flag_resources_modified(db, env)
    return _ok(key, status=200)


# ============================================================================
# OCI Block Volume — volumes, attachments, backups
# ============================================================================

@router.post("/20160918/volumes")
async def create_volume(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_volumes" not in resources:
        resources["oci_volumes"] = []

    vol_id = ocid("volume")
    volume = {
        "id": vol_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "availabilityDomain": body.get("availabilityDomain", "US-ASHBURN-AD-1"),
        "displayName": body.get("displayName", f"vol-{vol_id[-8:]}"),
        "sizeInGBs": body.get("sizeInGBs", 50),
        "sizeInMBs": body.get("sizeInGBs", 50) * 1024,
        "vpusPerGB": body.get("vpusPerGB", 10),
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
        "isHydrated": True,
        "kmsKeyId": body.get("kmsKeyId"),
        "sourceDetails": body.get("sourceDetails", {}),
        "freeformTags": body.get("freeformTags", {}),
    }
    resources["oci_volumes"].append(volume)
    flag_resources_modified(db, env)
    return _ok(volume, status=200)


@router.get("/20160918/volumes")
async def list_volumes(
    compartmentId: Optional[str] = None,
    availabilityDomain: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    volumes = resources.get("oci_volumes", [])
    items, next_page = paginate(volumes, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/volumes/{volume_id}")
async def get_volume(volume_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    vol = find_by_id(resources.get("oci_volumes", []), "id", volume_id)
    if not vol:
        raise HTTPException(404, "Volume not found")
    return _ok(vol)


@router.delete("/20160918/volumes/{volume_id}")
async def delete_volume(volume_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    volumes = resources.get("oci_volumes", [])
    if not remove_by_id(volumes, "id", volume_id):
        raise HTTPException(404, "Volume not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.post("/20160918/volumeAttachments")
async def attach_volume(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_volume_attachments" not in resources:
        resources["oci_volume_attachments"] = []

    att_id = ocid("volumeattachment")
    attachment = {
        "id": att_id,
        "instanceId": body.get("instanceId"),
        "volumeId": body.get("volumeId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "availabilityDomain": "US-ASHBURN-AD-1",
        "attachmentType": body.get("type", "paravirtualized"),
        "device": body.get("device", "/dev/oracleoci/oraclevdb"),
        "displayName": body.get("displayName", f"att-{att_id[-8:]}"),
        "isReadOnly": body.get("isReadOnly", False),
        "isShareable": body.get("isShareable", False),
        "lifecycleState": "ATTACHED",
        "timeCreated": utcnow_iso(),
    }
    resources["oci_volume_attachments"].append(attachment)
    flag_resources_modified(db, env)
    return _ok(attachment, status=200)


@router.delete("/20160918/volumeAttachments/{attachment_id}")
async def detach_volume(attachment_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    atts = resources.get("oci_volume_attachments", [])
    if not remove_by_id(atts, "id", attachment_id):
        raise HTTPException(404, "Attachment not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ============================================================================
# OCI Container Registry (OCIR) — repositories, images, tags
# ============================================================================

@router.get("/20180917/repositories")
async def list_oci_repositories(
    compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    repos = resources.get("oci_repositories", [])
    items, next_page = paginate(repos, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.post("/20180917/repositories")
async def create_oci_repository(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    if "oci_repositories" not in resources:
        resources["oci_repositories"] = []

    repo_id = ocid("repository", "iad")
    registry_host = os.getenv("REGISTRY_HOST", "registry:5000")
    repo = {
        "id": repo_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName"),
        "namespace": DEFAULT_OCI_NAMESPACE,
        "isPublic": body.get("isPublic", False),
        "lifecycleState": "AVAILABLE",
        "timeCreated": utcnow_iso(),
        "imageCount": 0,
        "layerCount": 0,
        "layersSizeInBytes": 0,
        "_registry_path": f"{registry_host}/{env.id}/{body.get('displayName', repo_id[-8:])}",
    }
    resources["oci_repositories"].append(repo)
    flag_resources_modified(db, env)
    return _ok(repo, status=200)


@router.get("/20180917/repositories/{repository_id}")
async def get_oci_repository(
    repository_id: str, request: Request, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    repo = find_by_id(resources.get("oci_repositories", []), "id", repository_id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    return _ok(repo)


@router.delete("/20180917/repositories/{repository_id}")
async def delete_oci_repository(
    repository_id: str, request: Request, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    repos = resources.get("oci_repositories", [])
    if not remove_by_id(repos, "id", repository_id):
        raise HTTPException(404, "Repository not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20180917/repositories/{repository_id}/images")
async def list_oci_images(
    repository_id: str,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    images = resources.get("oci_images", {}).get(repository_id, [])
    items, next_page = paginate(images, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


# ============================================================================
# Networking — missing GET-by-ID and DELETE endpoints
# ============================================================================

@router.get("/20160918/subnets/{subnet_id}")
async def get_subnet(subnet_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    subnet = find_by_id(resources.get("oci_subnets", []), "id", subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    return _ok(subnet, etag=etag_random())


@router.delete("/20160918/subnets/{subnet_id}")
async def delete_subnet(subnet_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_subnets", []), "id", subnet_id):
        raise HTTPException(404, "Subnet not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/internetGateways")
async def list_internet_gateways(
    vcnId: Optional[str] = None, compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    igws = resources.get("oci_igws", [])
    if vcnId:
        igws = [i for i in igws if i.get("vcnId") == vcnId]
    items, next_page = paginate(igws, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/internetGateways/{igw_id}")
async def get_internet_gateway(igw_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    igw = find_by_id(resources.get("oci_igws", []), "id", igw_id)
    if not igw:
        raise HTTPException(404, "Internet Gateway not found")
    return _ok(igw)


@router.put("/20160918/internetGateways/{igw_id}")
async def update_internet_gateway(igw_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    igw = find_by_id(resources.get("oci_igws", []), "id", igw_id)
    if not igw:
        raise HTTPException(404, "Internet Gateway not found")
    if "isEnabled" in body:
        igw["isEnabled"] = body["isEnabled"]
    if "displayName" in body:
        igw["displayName"] = body["displayName"]
    flag_resources_modified(db, env)
    return _ok(igw)


@router.delete("/20160918/internetGateways/{igw_id}")
async def delete_internet_gateway(igw_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_igws", []), "id", igw_id):
        raise HTTPException(404, "Internet Gateway not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/routeTables")
async def list_route_tables(
    vcnId: Optional[str] = None, compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    rts = resources.get("oci_route_tables", [])
    if vcnId:
        rts = [r for r in rts if r.get("vcnId") == vcnId]
    items, next_page = paginate(rts, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/routeTables/{rt_id}")
async def get_route_table(rt_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    rt = find_by_id(resources.get("oci_route_tables", []), "id", rt_id)
    if not rt:
        raise HTTPException(404, "Route Table not found")
    return _ok(rt)


@router.put("/20160918/routeTables/{rt_id}")
async def update_route_table(rt_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    rt = find_by_id(resources.get("oci_route_tables", []), "id", rt_id)
    if not rt:
        raise HTTPException(404, "Route Table not found")
    if "routeRules" in body:
        rt["routeRules"] = body["routeRules"]
    if "displayName" in body:
        rt["displayName"] = body["displayName"]
    flag_resources_modified(db, env)
    return _ok(rt)


@router.delete("/20160918/routeTables/{rt_id}")
async def delete_route_table(rt_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_route_tables", []), "id", rt_id):
        raise HTTPException(404, "Route Table not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/securityLists")
async def list_security_lists(
    vcnId: Optional[str] = None, compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    sls = resources.get("oci_security_lists", [])
    if vcnId:
        sls = [s for s in sls if s.get("vcnId") == vcnId]
    items, next_page = paginate(sls, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/securityLists/{sl_id}")
async def get_security_list(sl_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    sl = find_by_id(resources.get("oci_security_lists", []), "id", sl_id)
    if not sl:
        raise HTTPException(404, "Security List not found")
    return _ok(sl)


@router.put("/20160918/securityLists/{sl_id}")
async def update_security_list(sl_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    sl = find_by_id(resources.get("oci_security_lists", []), "id", sl_id)
    if not sl:
        raise HTTPException(404, "Security List not found")
    for k in ("egressSecurityRules", "ingressSecurityRules", "displayName"):
        if k in body:
            sl[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(sl)


@router.delete("/20160918/securityLists/{sl_id}")
async def delete_security_list(sl_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_security_lists", []), "id", sl_id):
        raise HTTPException(404, "Security List not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ============================================================================
# IAM — missing GET-by-ID, UPDATE, DELETE endpoints
# ============================================================================

@router.get("/20160918/users/{user_id}")
async def get_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    user = find_by_id(resources.get("oci_users", []), "id", user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return _ok(user)


@router.put("/20160918/users/{user_id}")
async def update_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    user = find_by_id(resources.get("oci_users", []), "id", user_id)
    if not user:
        raise HTTPException(404, "User not found")
    for k in ("description", "email", "freeformTags"):
        if k in body:
            user[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(user)


@router.delete("/20160918/users/{user_id}")
async def delete_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_users", []), "id", user_id):
        raise HTTPException(404, "User not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/groups")
async def list_groups(
    compartmentId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    groups = resources.get("oci_groups", [])
    items, next_page = paginate(groups, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/groups/{group_id}")
async def get_group(group_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    group = find_by_id(resources.get("oci_groups", []), "id", group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    return _ok(group)


@router.put("/20160918/groups/{group_id}")
async def update_group(group_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    group = find_by_id(resources.get("oci_groups", []), "id", group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    for k in ("description", "freeformTags"):
        if k in body:
            group[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(group)


@router.delete("/20160918/groups/{group_id}")
async def delete_group(group_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_groups", []), "id", group_id):
        raise HTTPException(404, "Group not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.post("/20160918/userGroupMemberships")
async def add_user_to_group(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    membership_id = ocid("userGroupMembership")
    membership = {
        "id": membership_id,
        "userId": body.get("userId"),
        "groupId": body.get("groupId"),
        "compartmentId": DEFAULT_OCI_COMPARTMENT,
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
    }
    resources.setdefault("oci_group_memberships", []).append(membership)
    flag_resources_modified(db, env)
    return _ok(membership, status=200)


@router.get("/20160918/userGroupMemberships")
async def list_user_group_memberships(
    compartmentId: Optional[str] = None,
    userId: Optional[str] = None,
    groupId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    memberships = resources.get("oci_group_memberships", [])
    if userId:
        memberships = [m for m in memberships if m.get("userId") == userId]
    if groupId:
        memberships = [m for m in memberships if m.get("groupId") == groupId]
    items, next_page = paginate(memberships, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.delete("/20160918/userGroupMemberships/{membership_id}")
async def remove_user_from_group(membership_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_group_memberships", []), "id", membership_id):
        raise HTTPException(404, "Membership not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/compartments/{compartment_id}")
async def get_compartment(compartment_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    cmp = find_by_id(resources.get("oci_compartments", []), "id", compartment_id)
    if not cmp:
        raise HTTPException(404, "Compartment not found")
    return _ok(cmp)


@router.put("/20160918/compartments/{compartment_id}")
async def update_compartment(compartment_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    cmp = find_by_id(resources.get("oci_compartments", []), "id", compartment_id)
    if not cmp:
        raise HTTPException(404, "Compartment not found")
    for k in ("name", "description", "freeformTags", "definedTags"):
        if k in body:
            cmp[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(cmp)


@router.delete("/20160918/compartments/{compartment_id}")
async def delete_compartment(compartment_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_compartments", []), "id", compartment_id):
        raise HTTPException(404, "Compartment not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/policies/{policy_id}")
async def get_policy(policy_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    policy = find_by_id(resources.get("oci_policies", []), "id", policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return _ok(policy)


@router.put("/20160918/policies/{policy_id}")
async def update_policy(policy_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    policy = find_by_id(resources.get("oci_policies", []), "id", policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    for k in ("description", "statements", "freeformTags", "definedTags"):
        if k in body:
            policy[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(policy)


@router.delete("/20160918/policies/{policy_id}")
async def delete_policy(policy_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_policies", []), "id", policy_id):
        raise HTTPException(404, "Policy not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.get("/20160918/users/{user_id}/apiKeys")
async def list_api_keys(user_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    keys = resources.get("oci_api_keys", {}).get(user_id, [])
    return _ok({"items": keys})


@router.delete("/20160918/users/{user_id}/apiKeys/{fingerprint}")
async def delete_api_key(user_id: str, fingerprint: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    keys = resources.get("oci_api_keys", {}).get(user_id, [])
    original_len = len(keys)
    resources["oci_api_keys"][user_id] = [k for k in keys if k.get("fingerprint") != fingerprint]
    if len(resources["oci_api_keys"][user_id]) == original_len:
        raise HTTPException(404, "API key not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


# ============================================================================
# Block Volume — missing GET list and backups
# ============================================================================

@router.get("/20160918/volumeAttachments")
async def list_volume_attachments(
    compartmentId: Optional[str] = None,
    instanceId: Optional[str] = None,
    volumeId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    atts = resources.get("oci_volume_attachments", [])
    if instanceId:
        atts = [a for a in atts if a.get("instanceId") == instanceId]
    if volumeId:
        atts = [a for a in atts if a.get("volumeId") == volumeId]
    items, next_page = paginate(atts, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/volumeAttachments/{attachment_id}")
async def get_volume_attachment(attachment_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    att = find_by_id(resources.get("oci_volume_attachments", []), "id", attachment_id)
    if not att:
        raise HTTPException(404, "Volume attachment not found")
    return _ok(att)


@router.post("/20160918/volumeBackups")
async def create_volume_backup(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_volume_backups", [])

    backup_id = ocid("volumebackup")
    backup = {
        "id": backup_id,
        "volumeId": body.get("volumeId"),
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": body.get("displayName", f"backup-{backup_id[-8:]}"),
        "type": body.get("type", "INCREMENTAL"),
        "lifecycleState": "AVAILABLE",
        "sizeInGBs": body.get("sizeInGBs", 50),
        "uniqueSizeInGBs": body.get("sizeInGBs", 50),
        "timeCreated": utcnow_iso(),
        "timeRequestReceived": utcnow_iso(),
        "expirationTime": None,
        "freeformTags": body.get("freeformTags", {}),
    }
    resources["oci_volume_backups"].append(backup)
    flag_resources_modified(db, env)
    return _ok(backup, status=200)


@router.get("/20160918/volumeBackups")
async def list_volume_backups(
    compartmentId: Optional[str] = None,
    volumeId: Optional[str] = None,
    limit: int = 100, page: Optional[str] = None,
    request: Request = None, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    backups = resources.get("oci_volume_backups", [])
    if volumeId:
        backups = [b for b in backups if b.get("volumeId") == volumeId]
    items, next_page = paginate(backups, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get("/20160918/volumeBackups/{backup_id}")
async def get_volume_backup(backup_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    backup = find_by_id(resources.get("oci_volume_backups", []), "id", backup_id)
    if not backup:
        raise HTTPException(404, "Volume backup not found")
    return _ok(backup)


@router.delete("/20160918/volumeBackups/{backup_id}")
async def delete_volume_backup(backup_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    if not remove_by_id(resources.get("oci_volume_backups", []), "id", backup_id):
        raise HTTPException(404, "Volume backup not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())
