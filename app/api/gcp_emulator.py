"""
GCP API Emulator
Emulates Google Cloud Compute Engine, Cloud Storage, Cloud SQL APIs
Translates requests to MockFactory infrastructure
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import Optional
import json
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.models.cloud_resources import (
    MockGCPComputeInstance, MockGCPStorageBucket, ResourceStatus
)

router = APIRouter()


def get_environment_from_request(request: Request, db: Session) -> Environment:
    """Extract environment from request"""
    host = request.headers.get("host", "")
    if "env-" in host:
        env_id = host.split(".")[0]
    else:
        env_id = request.headers.get("X-Mock-Environment-ID")

    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID required")

    environment = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    return environment


# ============================================================================
# GCP Compute Engine Emulation
# ============================================================================

@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/instances")
async def gcp_compute_create_instance(
    project: str,
    zone: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create GCP Compute Engine instance"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    name = body.get("name", f"instance-{uuid.uuid4().hex[:8]}")
    machine_type = body.get("machineType", "").split("/")[-1] or "e2-micro"

    internal_ip = f"10.128.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"
    external_ip = f"35.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"

    instance = MockGCPComputeInstance(
        environment_id=environment.id,
        name=name,
        zone=zone,
        machine_type=machine_type,
        internal_ip=internal_ip,
        external_ip=external_ip,
        status=ResourceStatus.RUNNING,
        labels=body.get("labels", {}),
        metadata=body.get("metadata", {})
    )

    db.add(instance)
    db.commit()
    db.refresh(instance)

    return {
        "kind": "compute#operation",
        "id": str(uuid.uuid4().int),
        "name": f"operation-{uuid.uuid4().hex[:16]}",
        "zone": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}",
        "operationType": "insert",
        "targetLink": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{name}",
        "status": "DONE",
        "user": "mock-user@example.com",
        "progress": 100,
        "insertTime": datetime.utcnow().isoformat() + "Z",
        "startTime": datetime.utcnow().isoformat() + "Z",
        "endTime": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/instances")
async def gcp_compute_list_instances(
    project: str,
    zone: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List GCP Compute Engine instances"""
    environment = get_environment_from_request(request, db)

    instances = db.query(MockGCPComputeInstance).filter(
        MockGCPComputeInstance.environment_id == environment.id,
        MockGCPComputeInstance.zone == zone
    ).all()

    items = []
    for inst in instances:
        items.append({
            "kind": "compute#instance",
            "id": str(inst.id),
            "creationTimestamp": inst.creation_timestamp.isoformat() + "Z",
            "name": inst.name,
            "zone": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}",
            "machineType": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/machineTypes/{inst.machine_type}",
            "status": inst.status.value.upper(),
            "networkInterfaces": [
                {
                    "network": f"https://www.googleapis.com/compute/v1/projects/{project}/global/networks/default",
                    "networkIP": inst.internal_ip,
                    "accessConfigs": [
                        {
                            "type": "ONE_TO_ONE_NAT",
                            "name": "External NAT",
                            "natIP": inst.external_ip
                        }
                    ]
                }
            ],
            "labels": inst.labels,
            "metadata": inst.metadata
        })

    return {
        "kind": "compute#instanceList",
        "id": f"projects/{project}/zones/{zone}/instances",
        "items": items,
        "selfLink": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances"
    }


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance_name}")
async def gcp_compute_get_instance(
    project: str,
    zone: str,
    instance_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get GCP Compute Engine instance"""
    environment = get_environment_from_request(request, db)

    instance = db.query(MockGCPComputeInstance).filter(
        MockGCPComputeInstance.environment_id == environment.id,
        MockGCPComputeInstance.zone == zone,
        MockGCPComputeInstance.name == instance_name
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    return {
        "kind": "compute#instance",
        "id": str(instance.id),
        "creationTimestamp": instance.creation_timestamp.isoformat() + "Z",
        "name": instance.name,
        "zone": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}",
        "machineType": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/machineTypes/{instance.machine_type}",
        "status": instance.status.value.upper(),
        "networkInterfaces": [
            {
                "network": f"https://www.googleapis.com/compute/v1/projects/{project}/global/networks/default",
                "networkIP": instance.internal_ip,
                "accessConfigs": [
                    {
                        "type": "ONE_TO_ONE_NAT",
                        "name": "External NAT",
                        "natIP": instance.external_ip
                    }
                ]
            }
        ],
        "labels": instance.labels
    }


@router.delete("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance_name}")
async def gcp_compute_delete_instance(
    project: str,
    zone: str,
    instance_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete GCP Compute Engine instance"""
    environment = get_environment_from_request(request, db)

    instance = db.query(MockGCPComputeInstance).filter(
        MockGCPComputeInstance.environment_id == environment.id,
        MockGCPComputeInstance.zone == zone,
        MockGCPComputeInstance.name == instance_name
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    instance.status = ResourceStatus.TERMINATED
    db.commit()

    return {
        "kind": "compute#operation",
        "id": str(uuid.uuid4().int),
        "name": f"operation-{uuid.uuid4().hex[:16]}",
        "operationType": "delete",
        "status": "DONE",
        "progress": 100
    }


# ============================================================================
# GCP Cloud Storage Emulation
# ============================================================================

@router.get("/gcp/storage/v1/b")
async def gcp_storage_list_buckets(
    request: Request,
    db: Session = Depends(get_db)
):
    """List GCP Cloud Storage buckets"""
    environment = get_environment_from_request(request, db)

    buckets = db.query(MockGCPStorageBucket).filter(
        MockGCPStorageBucket.environment_id == environment.id
    ).all()

    items = []
    for bucket in buckets:
        items.append({
            "kind": "storage#bucket",
            "id": str(bucket.id),
            "name": bucket.name,
            "timeCreated": bucket.time_created.isoformat() + "Z",
            "updated": bucket.time_created.isoformat() + "Z",
            "location": bucket.location,
            "storageClass": bucket.storage_class,
            "labels": bucket.labels
        })

    return {
        "kind": "storage#buckets",
        "items": items
    }


@router.post("/gcp/storage/v1/b")
async def gcp_storage_create_bucket(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create GCP Cloud Storage bucket"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    bucket_name = body.get("name")
    if not bucket_name:
        raise HTTPException(status_code=400, detail="Bucket name required")

    # Check if bucket exists
    existing = db.query(MockGCPStorageBucket).filter(
        MockGCPStorageBucket.name == bucket_name
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Bucket already exists")

    bucket = MockGCPStorageBucket(
        environment_id=environment.id,
        name=bucket_name,
        location=body.get("location", "US"),
        storage_class=body.get("storageClass", "STANDARD"),
        labels=body.get("labels", {})
    )

    db.add(bucket)
    db.commit()
    db.refresh(bucket)

    return {
        "kind": "storage#bucket",
        "id": str(bucket.id),
        "name": bucket.name,
        "timeCreated": bucket.time_created.isoformat() + "Z",
        "updated": bucket.time_created.isoformat() + "Z",
        "location": bucket.location,
        "storageClass": bucket.storage_class
    }


@router.get("/gcp/storage/v1/b/{bucket_name}")
async def gcp_storage_get_bucket(
    bucket_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get GCP Cloud Storage bucket"""
    environment = get_environment_from_request(request, db)

    bucket = db.query(MockGCPStorageBucket).filter(
        MockGCPStorageBucket.environment_id == environment.id,
        MockGCPStorageBucket.name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")

    return {
        "kind": "storage#bucket",
        "id": str(bucket.id),
        "name": bucket.name,
        "timeCreated": bucket.time_created.isoformat() + "Z",
        "updated": bucket.time_created.isoformat() + "Z",
        "location": bucket.location,
        "storageClass": bucket.storage_class,
        "labels": bucket.labels
    }


@router.delete("/gcp/storage/v1/b/{bucket_name}")
async def gcp_storage_delete_bucket(
    bucket_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete GCP Cloud Storage bucket"""
    environment = get_environment_from_request(request, db)

    bucket = db.query(MockGCPStorageBucket).filter(
        MockGCPStorageBucket.environment_id == environment.id,
        MockGCPStorageBucket.name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")

    db.delete(bucket)
    db.commit()

    return Response(status_code=204)


# ============================================================================
# GCP Cloud SQL Emulation (Basic)
# ============================================================================

@router.get("/gcp/sql/v1beta4/projects/{project}/instances")
async def gcp_sql_list_instances(
    project: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List Cloud SQL instances"""
    environment = get_environment_from_request(request, db)

    # For now, return empty list - can expand later
    return {
        "kind": "sql#instancesList",
        "items": []
    }


@router.post("/gcp/sql/v1beta4/projects/{project}/instances")
async def gcp_sql_create_instance(
    project: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create Cloud SQL instance"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    # Mock response - can be expanded later
    instance_name = body.get("name", f"sql-{uuid.uuid4().hex[:8]}")

    return {
        "kind": "sql#operation",
        "targetLink": f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance_name}",
        "status": "DONE",
        "operationType": "CREATE",
        "name": f"operation-{uuid.uuid4().hex[:16]}"
    }
