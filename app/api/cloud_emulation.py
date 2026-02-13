"""
Cloud API Emulation - AWS S3, GCP Storage, Azure Blob
Translates cloud provider APIs to OCI Object Storage backend
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import subprocess
import json
import base64
from datetime import datetime
import xml.etree.ElementTree as ET

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.models.user import User
from app.security.auth import require_authenticated_request


router = APIRouter()


def get_environment_from_subdomain(request: Request, db: Session) -> Environment:
    """
    Extract environment ID from subdomain
    Example: s3.env-abc123.mockfactory.io -> env-abc123
    """
    host = request.headers.get("host", "")
    parts = host.split(".")

    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid host format")

    # Extract env ID from subdomain (s3.env-abc123.mockfactory.io -> env-abc123)
    env_id = None
    for part in parts:
        if part.startswith("env-"):
            env_id = part
            break

    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID not found in host")

    # Look up environment
    environment = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found or not running")

    return environment


async def verify_environment_access(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated_request)
) -> Environment:
    """
    Verify user has access to the environment specified in the request

    1. Extract environment ID from subdomain
    2. Verify environment exists and is running
    3. Verify user owns the environment
    """
    environment = get_environment_from_subdomain(request, db)

    # Verify ownership
    if environment.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You do not own this environment."
        )

    return environment


# ============================================================================
# AWS S3 Emulation
# ============================================================================

@router.get("/s3/{bucket_name}")
async def s3_list_objects(
    bucket_name: str,
    prefix: Optional[str] = None,
    delimiter: Optional[str] = None,
    max_keys: Optional[int] = 1000,
    environment: Environment = Depends(verify_environment_access)
):
    """
    AWS S3 ListObjects API
    GET /bucket-name?prefix=...&delimiter=...

    Authentication: Requires API key or JWT token
    """

    # Map to OCI bucket
    oci_bucket = environment.oci_resources.get("aws_s3")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="S3 service not enabled for this environment")

    # List objects in OCI bucket
    cmd = ["oci", "os", "object", "list", "--bucket-name", oci_bucket, "--output", "json"]
    if prefix:
        cmd.extend(["--prefix", prefix])
    if delimiter:
        cmd.extend(["--delimiter", delimiter])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to list objects")

    oci_response = json.loads(result.stdout)

    # Convert OCI response to S3 XML format
    root = ET.Element("ListBucketResult", xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    ET.SubElement(root, "Name").text = bucket_name
    ET.SubElement(root, "Prefix").text = prefix or ""
    ET.SubElement(root, "MaxKeys").text = str(max_keys)
    ET.SubElement(root, "IsTruncated").text = "false"

    for obj in oci_response.get("data", []):
        contents = ET.SubElement(root, "Contents")
        ET.SubElement(contents, "Key").text = obj["name"]
        ET.SubElement(contents, "LastModified").text = obj.get("time-created", "")
        ET.SubElement(contents, "Size").text = str(obj.get("size", 0))
        ET.SubElement(contents, "StorageClass").text = "STANDARD"

    xml_response = ET.tostring(root, encoding="unicode")
    return Response(content=xml_response, media_type="application/xml")


@router.put("/s3/{bucket_name}/{object_key:path}")
async def s3_put_object(
    bucket_name: str,
    object_key: str,
    file: bytes = File(...),
    content_type: Optional[str] = Header(None),
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)
):
    """
    AWS S3 PutObject API
    PUT /bucket-name/object-key

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("aws_s3")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="S3 service not enabled")

    # Write file to temp location
    temp_file = f"/tmp/{environment.id}-{object_key.replace('/', '-')}"
    with open(temp_file, "wb") as f:
        f.write(file)

    # Upload to OCI
    cmd = [
        "oci", "os", "object", "put",
        "--bucket-name", oci_bucket,
        "--file", temp_file,
        "--name", object_key,
        "--force"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to upload object")

    # Clean up temp file
    subprocess.run(["rm", temp_file])

    # Update last activity
    environment.last_activity = datetime.utcnow()
    db.commit()

    return Response(
        status_code=200,
        headers={"ETag": f'"{object_key}"'}
    )


@router.get("/s3/{bucket_name}/{object_key:path}")
async def s3_get_object(
    bucket_name: str,
    object_key: str,
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)
):
    """
    AWS S3 GetObject API
    GET /bucket-name/object-key

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("aws_s3")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="S3 service not enabled")

    # Download from OCI
    temp_file = f"/tmp/{environment.id}-{object_key.replace('/', '-')}"
    cmd = [
        "oci", "os", "object", "get",
        "--bucket-name", oci_bucket,
        "--name", object_key,
        "--file", temp_file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=404, detail="Object not found")

    # Return file
    def iterfile():
        with open(temp_file, "rb") as f:
            yield from f
        subprocess.run(["rm", temp_file])  # Clean up after streaming

    # Update last activity
    environment.last_activity = datetime.utcnow()
    db.commit()

    return StreamingResponse(iterfile(), media_type="application/octet-stream")


@router.delete("/s3/{bucket_name}/{object_key:path}")
async def s3_delete_object(
    bucket_name: str,
    object_key: str,
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)
):
    """
    AWS S3 DeleteObject API
    DELETE /bucket-name/object-key

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("aws_s3")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="S3 service not enabled")

    # Delete from OCI
    cmd = [
        "oci", "os", "object", "delete",
        "--bucket-name", oci_bucket,
        "--name", object_key,
        "--force"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=404, detail="Object not found")

    # Update last activity
    environment.last_activity = datetime.utcnow()
    db.commit()

    return Response(status_code=204)


# ============================================================================
# GCP Cloud Storage Emulation
# ============================================================================

@router.get("/gcs/storage/v1/b/{bucket_name}/o")
async def gcs_list_objects(
    bucket_name: str,
    prefix: Optional[str] = None,
    delimiter: Optional[str] = None,
    maxResults: Optional[int] = 1000,
    environment: Environment = Depends(verify_environment_access)
):
    """
    GCP Cloud Storage List Objects API
    GET /storage/v1/b/{bucket}/o

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("gcp_storage")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="GCP Storage not enabled")

    # List objects from OCI
    cmd = ["oci", "os", "object", "list", "--bucket-name", oci_bucket, "--output", "json"]
    if prefix:
        cmd.extend(["--prefix", prefix])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to list objects")

    oci_response = json.loads(result.stdout)

    # Convert to GCS JSON format
    items = []
    for obj in oci_response.get("data", []):
        items.append({
            "name": obj["name"],
            "bucket": bucket_name,
            "size": str(obj.get("size", 0)),
            "timeCreated": obj.get("time-created", ""),
            "updated": obj.get("time-modified", obj.get("time-created", "")),
            "storageClass": "STANDARD"
        })

    return {
        "kind": "storage#objects",
        "items": items
    }


@router.post("/gcs/upload/storage/v1/b/{bucket_name}/o")
async def gcs_upload_object(
    bucket_name: str,
    name: str,
    file: UploadFile = File(...),
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)
):
    """
    GCP Cloud Storage Upload Object API
    POST /upload/storage/v1/b/{bucket}/o?name=...

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("gcp_storage")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="GCP Storage not enabled")

    # Save uploaded file
    temp_file = f"/tmp/{environment.id}-{name.replace('/', '-')}"
    with open(temp_file, "wb") as f:
        content = await file.read()
        f.write(content)

    # Upload to OCI
    cmd = [
        "oci", "os", "object", "put",
        "--bucket-name", oci_bucket,
        "--file", temp_file,
        "--name", name,
        "--force"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    subprocess.run(["rm", temp_file])

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Upload failed")

    environment.last_activity = datetime.utcnow()
    db.commit()

    return {
        "kind": "storage#object",
        "name": name,
        "bucket": bucket_name,
        "size": str(len(content))
    }


# ============================================================================
# Azure Blob Storage Emulation
# ============================================================================

@router.get("/azure/{container_name}")
async def azure_list_blobs(
    container_name: str,
    prefix: Optional[str] = None,
    maxresults: Optional[int] = 1000,
    comp: str = "list",
    environment: Environment = Depends(verify_environment_access)
):
    """
    Azure Blob Storage List Blobs API
    GET /{container}?comp=list&prefix=...

    Authentication: Requires API key or JWT token
    """
    if comp != "list":
        raise HTTPException(status_code=400, detail="Only comp=list supported")

    oci_bucket = environment.oci_resources.get("azure_blob")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="Azure Blob Storage not enabled")

    # List objects from OCI
    cmd = ["oci", "os", "object", "list", "--bucket-name", oci_bucket, "--output", "json"]
    if prefix:
        cmd.extend(["--prefix", prefix])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to list blobs")

    oci_response = json.loads(result.stdout)

    # Convert to Azure XML format
    root = ET.Element("EnumerationResults", ContainerName=container_name)
    blobs = ET.SubElement(root, "Blobs")

    for obj in oci_response.get("data", []):
        blob = ET.SubElement(blobs, "Blob")
        ET.SubElement(blob, "Name").text = obj["name"]
        properties = ET.SubElement(blob, "Properties")
        ET.SubElement(properties, "Last-Modified").text = obj.get("time-created", "")
        ET.SubElement(properties, "Content-Length").text = str(obj.get("size", 0))
        ET.SubElement(properties, "BlobType").text = "BlockBlob"

    xml_response = ET.tostring(root, encoding="unicode")
    return Response(content=xml_response, media_type="application/xml")


@router.put("/azure/{container_name}/{blob_name:path}")
async def azure_put_blob(
    container_name: str,
    blob_name: str,
    file: bytes = File(...),
    x_ms_blob_type: str = Header("BlockBlob"),
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)
):
    """
    Azure Blob Storage Put Blob API
    PUT /{container}/{blob}

    Authentication: Requires API key or JWT token
    """

    oci_bucket = environment.oci_resources.get("azure_blob")
    if not oci_bucket:
        raise HTTPException(status_code=404, detail="Azure Blob Storage not enabled")

    # Write to temp file
    temp_file = f"/tmp/{environment.id}-{blob_name.replace('/', '-')}"
    with open(temp_file, "wb") as f:
        f.write(file)

    # Upload to OCI
    cmd = [
        "oci", "os", "object", "put",
        "--bucket-name", oci_bucket,
        "--file", temp_file,
        "--name", blob_name,
        "--force"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    subprocess.run(["rm", temp_file])

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Upload failed")

    environment.last_activity = datetime.utcnow()
    db.commit()

    return Response(
        status_code=201,
        headers={"x-ms-request-id": environment.id}
    )
