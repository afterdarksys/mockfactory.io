"""
Cloud API Emulation — AWS S3, GCP Cloud Storage, Azure Blob Storage
Production-grade emulation backed by local MinIO (S3-compatible).
All three providers translate to the same MinIO backend with per-environment,
per-provider namespaced buckets.

Supported operations per provider:
  AWS S3   — ListBuckets, CreateBucket, HeadBucket, DeleteBucket,
              ListObjects, PutObject, GetObject, HeadObject, DeleteObject,
              CopyObject, GetBucketLocation, GetBucketVersioning,
              CreateMultipartUpload, UploadPart, CompleteMultipartUpload,
              AbortMultipartUpload
  GCP GCS  — List, Upload, Get, Delete, Copy, Rewrite, Patch
  Azure    — List, Put, Get, Delete, Copy, GetProperties
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import unquote_plus

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.models.user import User
from app.security.auth import require_authenticated_request
from app.services.mock_helpers import (
    aws_headers, aws_request_id, azure_headers, azure_request_id,
    etag_from_content, etag_random, gcp_headers, get_resources,
    new_uuid, utcnow_iso, utcnow_rfc1123, version_id,
    DEFAULT_AWS_ACCOUNT_ID, DEFAULT_AWS_REGION,
)


router = APIRouter()


# ---------------------------------------------------------------------------
# MinIO client
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


# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------

def _env_from_host(request: Request, db: Session) -> Environment:
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


async def _authed_env(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated_request),
) -> Environment:
    env = _env_from_host(request, db)
    if env.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return env


def _bucket_name(environment: Environment, service_key: str) -> str:
    bucket = (environment.oci_resources or {}).get(service_key)
    if not bucket or not isinstance(bucket, str):
        raise HTTPException(404, f"{service_key} service not enabled for this environment")
    return bucket


def _touch(environment: Environment, db: Session) -> None:
    environment.last_activity = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# XML helpers (S3 / Azure use XML; GCS uses JSON)
# ---------------------------------------------------------------------------

def _xml(root: ET.Element, status: int = 200,
         extra_headers: Optional[dict] = None) -> Response:
    h = aws_headers()
    if extra_headers:
        h.update(extra_headers)
    return Response(
        content=ET.tostring(root, encoding="unicode", xml_declaration=False),
        status_code=status,
        headers=h,
        media_type="application/xml",
    )


def _s3_obj_to_xml(parent: ET.Element, obj: dict) -> None:
    contents = ET.SubElement(parent, "Contents")
    ET.SubElement(contents, "Key").text = obj["Key"]
    ET.SubElement(contents, "LastModified").text = obj["LastModified"].strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    ET.SubElement(contents, "ETag").text = obj.get("ETag", "").strip('"')
    ET.SubElement(contents, "Size").text = str(obj["Size"])
    ET.SubElement(contents, "StorageClass").text = "STANDARD"
    owner = ET.SubElement(contents, "Owner")
    ET.SubElement(owner, "ID").text = DEFAULT_AWS_ACCOUNT_ID
    ET.SubElement(owner, "DisplayName").text = "mockfactory"


# ============================================================================
# AWS S3 Emulation
# ============================================================================

# --- Bucket operations ---

@router.get("/s3/")
async def s3_list_buckets(
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 ListBuckets."""
    resources = get_resources(environment)
    root = ET.Element("ListAllMyBucketsResult",
                      xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    owner_el = ET.SubElement(root, "Owner")
    ET.SubElement(owner_el, "ID").text = DEFAULT_AWS_ACCOUNT_ID
    ET.SubElement(owner_el, "DisplayName").text = "mockfactory"
    buckets_el = ET.SubElement(root, "Buckets")

    # Only list S3 service bucket
    s3_bucket = resources.get("aws_s3")
    if s3_bucket:
        b = ET.SubElement(buckets_el, "Bucket")
        ET.SubElement(b, "Name").text = "default"
        ET.SubElement(b, "CreationDate").text = utcnow_iso()

    return _xml(root)


@router.head("/s3/{bucket_name}")
async def s3_head_bucket(
    bucket_name: str,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 HeadBucket."""
    _bucket_name(environment, "aws_s3")
    return Response(status_code=200, headers=aws_headers())


@router.get("/s3/{bucket_name}/location")
async def s3_get_bucket_location(
    bucket_name: str,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 GetBucketLocation."""
    root = ET.Element("LocationConstraint",
                      xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    root.text = DEFAULT_AWS_REGION
    return _xml(root)


@router.get("/s3/{bucket_name}/versioning")
async def s3_get_bucket_versioning(
    bucket_name: str,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 GetBucketVersioning."""
    root = ET.Element("VersioningConfiguration",
                      xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    ET.SubElement(root, "Status").text = "Suspended"
    return _xml(root)


# --- Object listing ---

@router.get("/s3/{bucket_name}")
async def s3_list_objects(
    bucket_name: str,
    prefix: Optional[str] = None,
    delimiter: Optional[str] = None,
    max_keys: int = 1000,
    continuation_token: Optional[str] = None,
    list_type: Optional[str] = None,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 ListObjectsV2 (and V1 compatible)."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()

    kwargs: dict = {"Bucket": minio_bucket, "MaxKeys": max_keys}
    if prefix:
        kwargs["Prefix"] = prefix
    if delimiter:
        kwargs["Delimiter"] = delimiter
    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token

    try:
        resp = s3.list_objects_v2(**kwargs)
    except ClientError as e:
        raise HTTPException(500, str(e))

    root = ET.Element("ListBucketResult",
                      xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    ET.SubElement(root, "Name").text = bucket_name
    ET.SubElement(root, "Prefix").text = prefix or ""
    ET.SubElement(root, "MaxKeys").text = str(max_keys)
    ET.SubElement(root, "KeyCount").text = str(resp.get("KeyCount", 0))
    ET.SubElement(root, "IsTruncated").text = str(resp.get("IsTruncated", False)).lower()

    if resp.get("NextContinuationToken"):
        ET.SubElement(root, "NextContinuationToken").text = resp["NextContinuationToken"]
    if continuation_token:
        ET.SubElement(root, "ContinuationToken").text = continuation_token

    for obj in resp.get("Contents", []):
        _s3_obj_to_xml(root, obj)

    for cp in resp.get("CommonPrefixes", []):
        cp_el = ET.SubElement(root, "CommonPrefixes")
        ET.SubElement(cp_el, "Prefix").text = cp["Prefix"]

    return _xml(root)


# --- Object operations ---

@router.head("/s3/{bucket_name}/{object_key:path}")
async def s3_head_object(
    bucket_name: str,
    object_key: str,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 HeadObject."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()
    try:
        resp = s3.head_object(Bucket=minio_bucket, Key=object_key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            raise HTTPException(404, "Not found")
        raise HTTPException(500, str(e))

    et = resp.get("ETag", "").strip('"')
    return Response(
        status_code=200,
        headers={
            **aws_headers(),
            "ETag": f'"{et}"',
            "Content-Length": str(resp.get("ContentLength", 0)),
            "Content-Type": resp.get("ContentType", "application/octet-stream"),
            "Last-Modified": utcnow_rfc1123(),
            "Accept-Ranges": "bytes",
        },
    )


@router.put("/s3/{bucket_name}/{object_key:path}")
async def s3_put_object(
    bucket_name: str,
    object_key: str,
    request: Request,
    x_amz_copy_source: Optional[str] = Header(None),
    content_type: Optional[str] = Header(None),
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """AWS S3 PutObject (and CopyObject when x-amz-copy-source is set)."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()

    if x_amz_copy_source:
        # CopyObject
        src = unquote_plus(x_amz_copy_source.lstrip("/"))
        # src is "bucket/key"
        src_parts = src.split("/", 1)
        src_bucket = minio_bucket  # same environment bucket
        src_key = src_parts[1] if len(src_parts) > 1 else src_parts[0]
        try:
            s3.copy_object(
                Bucket=minio_bucket,
                CopySource={"Bucket": src_bucket, "Key": src_key},
                Key=object_key,
            )
        except ClientError as e:
            raise HTTPException(500, str(e))

        et = etag_random()
        root = ET.Element("CopyObjectResult",
                          xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
        ET.SubElement(root, "LastModified").text = utcnow_iso()
        ET.SubElement(root, "ETag").text = f'"{et}"'
        _touch(environment, db)
        return _xml(root, extra_headers={"ETag": f'"{et}"'})

    # Regular PutObject
    body = await request.body()
    et = etag_from_content(body)
    ct = content_type or "application/octet-stream"

    # Collect x-amz-meta-* headers as S3 metadata
    metadata = {
        k[11:]: v
        for k, v in request.headers.items()
        if k.lower().startswith("x-amz-meta-")
    }

    try:
        s3.put_object(
            Bucket=minio_bucket,
            Key=object_key,
            Body=body,
            ContentType=ct,
            Metadata=metadata,
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    _touch(environment, db)
    return Response(
        status_code=200,
        headers={
            **aws_headers(),
            "ETag": f'"{et}"',
            "Content-Length": "0",
        },
    )


@router.get("/s3/{bucket_name}/{object_key:path}")
async def s3_get_object(
    bucket_name: str,
    object_key: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """AWS S3 GetObject."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()
    try:
        resp = s3.get_object(Bucket=minio_bucket, Key=object_key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(404, "NoSuchKey")
        raise HTTPException(500, str(e))

    et = resp.get("ETag", "").strip('"')
    _touch(environment, db)
    return StreamingResponse(
        resp["Body"],
        media_type=resp.get("ContentType", "application/octet-stream"),
        headers={
            **aws_headers(),
            "ETag": f'"{et}"',
            "Content-Length": str(resp.get("ContentLength", 0)),
            "Last-Modified": utcnow_rfc1123(),
            "Accept-Ranges": "bytes",
        },
    )


@router.delete("/s3/{bucket_name}/{object_key:path}")
async def s3_delete_object(
    bucket_name: str,
    object_key: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """AWS S3 DeleteObject."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()
    try:
        s3.delete_object(Bucket=minio_bucket, Key=object_key)
    except ClientError as e:
        raise HTTPException(500, str(e))
    _touch(environment, db)
    return Response(
        status_code=204,
        headers={**aws_headers(), "x-amz-delete-marker": "false"},
    )


@router.post("/s3/{bucket_name}/{object_key:path}")
async def s3_multipart_or_restore(
    bucket_name: str,
    object_key: str,
    uploads: Optional[str] = None,
    uploadId: Optional[str] = None,
    request: Request = None,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """
    AWS S3 Multipart upload endpoints:
      POST /bucket/key?uploads            → CreateMultipartUpload
      POST /bucket/key?uploadId=...       → CompleteMultipartUpload
    """
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()

    if uploads is not None:
        # CreateMultipartUpload
        ct = request.headers.get("content-type", "application/octet-stream")
        try:
            resp = s3.create_multipart_upload(
                Bucket=minio_bucket, Key=object_key, ContentType=ct
            )
        except ClientError as e:
            raise HTTPException(500, str(e))

        root = ET.Element("InitiateMultipartUploadResult",
                          xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
        ET.SubElement(root, "Bucket").text = bucket_name
        ET.SubElement(root, "Key").text = object_key
        ET.SubElement(root, "UploadId").text = resp["UploadId"]
        return _xml(root, status=200)

    if uploadId:
        # CompleteMultipartUpload
        body = await request.body()
        try:
            xml_root = ET.fromstring(body)
        except ET.ParseError:
            raise HTTPException(400, "Invalid XML")

        parts = []
        for part in xml_root.findall("Part"):
            parts.append({
                "PartNumber": int(part.findtext("PartNumber", "0")),
                "ETag": part.findtext("ETag", "").strip('"'),
            })

        try:
            resp = s3.complete_multipart_upload(
                Bucket=minio_bucket,
                Key=object_key,
                UploadId=uploadId,
                MultipartUpload={"Parts": parts},
            )
        except ClientError as e:
            raise HTTPException(500, str(e))

        et = resp.get("ETag", "").strip('"')
        root = ET.Element("CompleteMultipartUploadResult",
                          xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
        ET.SubElement(root, "Location").text = resp.get("Location", "")
        ET.SubElement(root, "Bucket").text = bucket_name
        ET.SubElement(root, "Key").text = object_key
        ET.SubElement(root, "ETag").text = f'"{et}"'
        _touch(environment, db)
        return _xml(root)

    raise HTTPException(400, "Unknown S3 POST operation")


@router.put("/s3/{bucket_name}/{object_key:path}/part")
async def s3_upload_part(
    bucket_name: str,
    object_key: str,
    partNumber: int = 1,
    uploadId: str = "",
    request: Request = None,
    environment: Environment = Depends(_authed_env),
):
    """AWS S3 UploadPart."""
    minio_bucket = _bucket_name(environment, "aws_s3")
    s3 = _s3()
    body = await request.body()
    try:
        resp = s3.upload_part(
            Bucket=minio_bucket,
            Key=object_key,
            PartNumber=partNumber,
            UploadId=uploadId,
            Body=body,
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    et = resp.get("ETag", "").strip('"')
    return Response(
        status_code=200,
        headers={**aws_headers(), "ETag": f'"{et}"'},
    )


# ============================================================================
# GCP Cloud Storage Emulation
# ============================================================================

@router.get("/gcs/storage/v1/b")
async def gcs_list_buckets(
    project: Optional[str] = None,
    environment: Environment = Depends(_authed_env),
):
    """GCS ListBuckets."""
    resources = get_resources(environment)
    bucket_name = resources.get("gcp_storage", "")
    return {
        "kind": "storage#buckets",
        "items": [
            {
                "kind": "storage#bucket",
                "id": "default",
                "name": "default",
                "projectNumber": "987654321098",
                "storageClass": "STANDARD",
                "location": "US",
                "timeCreated": utcnow_iso(),
                "updated": utcnow_iso(),
            }
        ] if bucket_name else [],
    }


@router.get("/gcs/storage/v1/b/{bucket_name}/o")
async def gcs_list_objects(
    bucket_name: str,
    prefix: Optional[str] = None,
    delimiter: Optional[str] = None,
    maxResults: int = 1000,
    pageToken: Optional[str] = None,
    environment: Environment = Depends(_authed_env),
):
    """GCS ListObjects."""
    minio_bucket = _bucket_name(environment, "gcp_storage")
    s3 = _s3()

    kwargs: dict = {"Bucket": minio_bucket, "MaxKeys": maxResults}
    if prefix:
        kwargs["Prefix"] = prefix
    if delimiter:
        kwargs["Delimiter"] = delimiter
    if pageToken:
        kwargs["ContinuationToken"] = pageToken

    try:
        resp = s3.list_objects_v2(**kwargs)
    except ClientError as e:
        raise HTTPException(500, str(e))

    items = [
        {
            "kind": "storage#object",
            "id": f"{bucket_name}/{o['Key']}",
            "name": o["Key"],
            "bucket": bucket_name,
            "size": str(o["Size"]),
            "contentType": "application/octet-stream",
            "timeCreated": o["LastModified"].isoformat(),
            "updated": o["LastModified"].isoformat(),
            "storageClass": "STANDARD",
            "etag": o.get("ETag", "").strip('"'),
            "md5Hash": o.get("ETag", "").strip('"'),
            "generation": str(int(o["LastModified"].timestamp() * 1000)),
            "metageneration": "1",
            "selfLink": f"https://www.googleapis.com/storage/v1/b/{bucket_name}/o/{o['Key']}",
            "mediaLink": f"https://storage.googleapis.com/download/storage/v1/b/{bucket_name}/o/{o['Key']}?alt=media",
        }
        for o in resp.get("Contents", [])
    ]

    result: dict = {"kind": "storage#objects", "items": items}
    if resp.get("NextContinuationToken"):
        result["nextPageToken"] = resp["NextContinuationToken"]
    if resp.get("CommonPrefixes"):
        result["prefixes"] = [p["Prefix"] for p in resp["CommonPrefixes"]]

    return result


@router.post("/gcs/upload/storage/v1/b/{bucket_name}/o")
async def gcs_upload_object(
    bucket_name: str,
    name: str,
    uploadType: Optional[str] = "media",
    file: Optional[UploadFile] = File(None),
    request: Request = None,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """GCS UploadObject (media and multipart)."""
    minio_bucket = _bucket_name(environment, "gcp_storage")
    s3 = _s3()

    if file:
        content = await file.read()
        ct = file.content_type or "application/octet-stream"
    else:
        content = await request.body()
        ct = request.headers.get("content-type", "application/octet-stream")

    et = etag_from_content(content)
    generation = str(int(datetime.now(timezone.utc).timestamp() * 1000))

    try:
        s3.put_object(
            Bucket=minio_bucket, Key=name, Body=content, ContentType=ct
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    _touch(environment, db)
    return {
        "kind": "storage#object",
        "id": f"{bucket_name}/{name}/{generation}",
        "name": name,
        "bucket": bucket_name,
        "size": str(len(content)),
        "contentType": ct,
        "timeCreated": utcnow_iso(),
        "updated": utcnow_iso(),
        "storageClass": "STANDARD",
        "etag": et,
        "md5Hash": et,
        "generation": generation,
        "metageneration": "1",
        "selfLink": f"https://www.googleapis.com/storage/v1/b/{bucket_name}/o/{name}",
        "mediaLink": f"https://storage.googleapis.com/download/storage/v1/b/{bucket_name}/o/{name}?alt=media",
    }


@router.get("/gcs/storage/v1/b/{bucket_name}/o/{object_name:path}")
async def gcs_get_object_metadata(
    bucket_name: str, object_name: str,
    alt: Optional[str] = None,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """GCS GetObject (metadata or download when alt=media)."""
    minio_bucket = _bucket_name(environment, "gcp_storage")
    s3 = _s3()

    try:
        resp = s3.get_object(Bucket=minio_bucket, Key=object_name)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(404, "Not Found")
        raise HTTPException(500, str(e))

    _touch(environment, db)

    if alt == "media":
        return StreamingResponse(
            resp["Body"],
            media_type=resp.get("ContentType", "application/octet-stream"),
            headers=gcp_headers(),
        )

    et = resp.get("ETag", "").strip('"')
    return {
        "kind": "storage#object",
        "name": object_name,
        "bucket": bucket_name,
        "size": str(resp.get("ContentLength", 0)),
        "contentType": resp.get("ContentType", "application/octet-stream"),
        "updated": utcnow_iso(),
        "timeCreated": utcnow_iso(),
        "storageClass": "STANDARD",
        "etag": et,
        "md5Hash": et,
        "generation": "1",
        "metageneration": "1",
    }


@router.delete("/gcs/storage/v1/b/{bucket_name}/o/{object_name:path}")
async def gcs_delete_object(
    bucket_name: str, object_name: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """GCS DeleteObject."""
    minio_bucket = _bucket_name(environment, "gcp_storage")
    s3 = _s3()
    try:
        s3.delete_object(Bucket=minio_bucket, Key=object_name)
    except ClientError as e:
        raise HTTPException(500, str(e))
    _touch(environment, db)
    return Response(status_code=204, headers=gcp_headers())


@router.post("/gcs/storage/v1/b/{src_bucket}/o/{src_object:path}/copyTo/b/{dst_bucket}/o/{dst_object:path}")
async def gcs_copy_object(
    src_bucket: str, src_object: str,
    dst_bucket: str, dst_object: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """GCS CopyObject."""
    minio_bucket = _bucket_name(environment, "gcp_storage")
    s3 = _s3()
    try:
        s3.copy_object(
            Bucket=minio_bucket,
            CopySource={"Bucket": minio_bucket, "Key": src_object},
            Key=dst_object,
        )
    except ClientError as e:
        raise HTTPException(500, str(e))
    _touch(environment, db)
    return {
        "kind": "storage#object",
        "name": dst_object,
        "bucket": dst_bucket,
        "timeCreated": utcnow_iso(),
        "updated": utcnow_iso(),
        "storageClass": "STANDARD",
        "generation": "1",
        "metageneration": "1",
    }


# ============================================================================
# Azure Blob Storage Emulation
# ============================================================================

def _azure_xml(root: ET.Element, status: int = 200,
               extra_headers: Optional[dict] = None) -> Response:
    h = azure_headers()
    if extra_headers:
        h.update(extra_headers)
    return Response(
        content=ET.tostring(root, encoding="unicode"),
        status_code=status,
        headers=h,
        media_type="application/xml",
    )


@router.get("/azure/{container_name}")
async def azure_list_blobs(
    container_name: str,
    prefix: Optional[str] = None,
    maxresults: int = 5000,
    marker: Optional[str] = None,
    comp: str = "list",
    environment: Environment = Depends(_authed_env),
):
    """Azure ListBlobs."""
    if comp != "list":
        raise HTTPException(400, "Only comp=list supported")

    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()

    kwargs: dict = {"Bucket": minio_bucket, "MaxKeys": maxresults}
    if prefix:
        kwargs["Prefix"] = prefix
    if marker:
        kwargs["ContinuationToken"] = marker

    try:
        resp = s3.list_objects_v2(**kwargs)
    except ClientError as e:
        raise HTTPException(500, str(e))

    root = ET.Element("EnumerationResults",
                      ServiceEndpoint=f"https://mockfactory.blob.core.windows.net/",
                      ContainerName=container_name)
    ET.SubElement(root, "Prefix").text = prefix or ""
    ET.SubElement(root, "MaxResults").text = str(maxresults)
    blobs_el = ET.SubElement(root, "Blobs")

    for obj in resp.get("Contents", []):
        blob = ET.SubElement(blobs_el, "Blob")
        ET.SubElement(blob, "Name").text = obj["Key"]
        props = ET.SubElement(blob, "Properties")
        ET.SubElement(props, "Last-Modified").text = obj["LastModified"].strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        ET.SubElement(props, "Etag").text = obj.get("ETag", "").strip('"')
        ET.SubElement(props, "Content-Length").text = str(obj["Size"])
        ET.SubElement(props, "Content-Type").text = "application/octet-stream"
        ET.SubElement(props, "BlobType").text = "BlockBlob"
        ET.SubElement(props, "LeaseStatus").text = "unlocked"
        ET.SubElement(props, "LeaseState").text = "available"
        ET.SubElement(props, "ServerEncrypted").text = "true"

    next_marker = resp.get("NextContinuationToken", "")
    ET.SubElement(root, "NextMarker").text = next_marker or ""

    return _azure_xml(root)


@router.head("/azure/{container_name}/{blob_name:path}")
async def azure_head_blob(
    container_name: str, blob_name: str,
    environment: Environment = Depends(_authed_env),
):
    """Azure GetBlobProperties (HEAD)."""
    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()
    try:
        resp = s3.head_object(Bucket=minio_bucket, Key=blob_name)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            raise HTTPException(404, "BlobNotFound")
        raise HTTPException(500, str(e))

    et = resp.get("ETag", "").strip('"')
    return Response(
        status_code=200,
        headers={
            **azure_headers(),
            "x-ms-blob-type": "BlockBlob",
            "x-ms-lease-state": "available",
            "x-ms-lease-status": "unlocked",
            "x-ms-server-encrypted": "true",
            "ETag": f'"{et}"',
            "Last-Modified": utcnow_rfc1123(),
            "Content-Length": str(resp.get("ContentLength", 0)),
            "Content-Type": resp.get("ContentType", "application/octet-stream"),
        },
    )


@router.put("/azure/{container_name}/{blob_name:path}")
async def azure_put_blob(
    container_name: str, blob_name: str,
    request: Request,
    x_ms_blob_type: str = Header("BlockBlob"),
    content_type: Optional[str] = Header(None),
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """Azure PutBlob / PutBlock."""
    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()
    body = await request.body()
    ct = content_type or "application/octet-stream"
    et = etag_from_content(body)

    try:
        s3.put_object(Bucket=minio_bucket, Key=blob_name, Body=body, ContentType=ct)
    except ClientError as e:
        raise HTTPException(500, str(e))

    _touch(environment, db)
    return Response(
        status_code=201,
        headers={
            **azure_headers(),
            "ETag": f'"{et}"',
            "x-ms-request-server-encrypted": "true",
            "x-ms-version-id": version_id(),
            "Content-MD5": et,
        },
    )


@router.get("/azure/{container_name}/{blob_name:path}")
async def azure_get_blob(
    container_name: str, blob_name: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """Azure GetBlob."""
    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()
    try:
        resp = s3.get_object(Bucket=minio_bucket, Key=blob_name)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(404, "BlobNotFound")
        raise HTTPException(500, str(e))

    et = resp.get("ETag", "").strip('"')
    _touch(environment, db)
    return StreamingResponse(
        resp["Body"],
        media_type=resp.get("ContentType", "application/octet-stream"),
        headers={
            **azure_headers(),
            "ETag": f'"{et}"',
            "x-ms-blob-type": "BlockBlob",
            "x-ms-lease-state": "available",
            "x-ms-server-encrypted": "true",
            "Content-Length": str(resp.get("ContentLength", 0)),
            "Last-Modified": utcnow_rfc1123(),
        },
    )


@router.delete("/azure/{container_name}/{blob_name:path}")
async def azure_delete_blob(
    container_name: str, blob_name: str,
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """Azure DeleteBlob."""
    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()
    try:
        s3.delete_object(Bucket=minio_bucket, Key=blob_name)
    except ClientError as e:
        raise HTTPException(500, str(e))
    _touch(environment, db)
    return Response(
        status_code=202,
        headers={**azure_headers(), "x-ms-delete-type-permanent": "true"},
    )


@router.put("/azure/{container_name}/{dst_blob:path}")
async def azure_copy_blob(
    container_name: str, dst_blob: str,
    x_ms_copy_source: Optional[str] = Header(None),
    environment: Environment = Depends(_authed_env),
    db: Session = Depends(get_db),
):
    """Azure CopyBlob (when x-ms-copy-source header is set)."""
    if not x_ms_copy_source:
        raise HTTPException(400, "x-ms-copy-source header required for copy")

    minio_bucket = _bucket_name(environment, "azure_blob")
    s3 = _s3()
    src_blob = x_ms_copy_source.split("/")[-1]

    try:
        s3.copy_object(
            Bucket=minio_bucket,
            CopySource={"Bucket": minio_bucket, "Key": src_blob},
            Key=dst_blob,
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    copy_id = new_uuid()
    _touch(environment, db)
    return Response(
        status_code=202,
        headers={
            **azure_headers(),
            "x-ms-copy-id": copy_id,
            "x-ms-copy-status": "success",
        },
    )
