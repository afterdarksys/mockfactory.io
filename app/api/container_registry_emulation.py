"""
Container Registry Emulation - AWS ECR & GCP Container Registry
Translates ECR/GCR APIs to OCI Container Registry (OCIR) backend
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy.orm import Session
from typing import Optional, List
import subprocess
import json
import base64
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus


router = APIRouter()


def get_environment_from_subdomain(request: Request, db: Session) -> Environment:
    """Extract environment ID from subdomain"""
    host = request.headers.get("host", "")
    parts = host.split(".")

    env_id = None
    for part in parts:
        if part.startswith("env-"):
            env_id = part
            break

    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID not found in host")

    environment = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found or not running")

    return environment


# ============================================================================
# AWS ECR (Elastic Container Registry) Emulation
# ============================================================================

@router.post("/ecr/")
async def ecr_api(
    request: Request,
    x_amz_target: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    AWS ECR API Endpoint
    Handles all ECR operations via X-Amz-Target header
    """
    environment = get_environment_from_subdomain(request, db)

    # Parse request body
    body = await request.json()

    # Route based on operation
    if "GetAuthorizationToken" in x_amz_target:
        return await ecr_get_authorization_token(environment)

    elif "CreateRepository" in x_amz_target:
        return await ecr_create_repository(environment, body)

    elif "DescribeRepositories" in x_amz_target:
        return await ecr_describe_repositories(environment, body)

    elif "PutImage" in x_amz_target:
        return await ecr_put_image(environment, body)

    elif "GetDownloadUrlForLayer" in x_amz_target:
        return await ecr_get_download_url(environment, body)

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported operation: {x_amz_target}")


async def ecr_get_authorization_token(environment: Environment):
    """
    ECR GetAuthorizationToken
    Returns Docker login credentials
    """
    # Generate token (base64 encoded username:password)
    username = "AWS"
    password = f"mockfactory-{environment.id}"
    token = base64.b64encode(f"{username}:{password}".encode()).decode()

    # Token expires in 12 hours
    expiration = (datetime.utcnow() + timedelta(hours=12)).isoformat() + "Z"

    return {
        "authorizationData": [
            {
                "authorizationToken": token,
                "expiresAt": expiration,
                "proxyEndpoint": f"https://ecr.{environment.id}.mockfactory.io"
            }
        ]
    }


async def ecr_create_repository(environment: Environment, body: dict):
    """
    ECR CreateRepository
    Creates a new repository (maps to OCIR)
    """
    repo_name = body.get("repositoryName")
    if not repo_name:
        raise HTTPException(status_code=400, detail="repositoryName required")

    # Create OCIR repository
    # Format: <region>.ocir.io/<namespace>/<repo-name>
    namespace = "idd2oizp8xvc"  # Your OCI namespace
    ocir_repo = f"{namespace}/{environment.id}/{repo_name}"

    # OCIR repos are created automatically on first push
    # Store repo metadata in environment
    if not environment.oci_resources:
        environment.oci_resources = {}

    if "ecr_repositories" not in environment.oci_resources:
        environment.oci_resources["ecr_repositories"] = []

    environment.oci_resources["ecr_repositories"].append({
        "name": repo_name,
        "ocir_path": ocir_repo,
        "created_at": datetime.utcnow().isoformat()
    })

    # Note: Would normally update DB here, but in async context
    # This is simplified for POC

    return {
        "repository": {
            "repositoryArn": f"arn:aws:ecr:us-east-1:123456789012:repository/{repo_name}",
            "registryId": environment.id,
            "repositoryName": repo_name,
            "repositoryUri": f"ecr.{environment.id}.mockfactory.io/{repo_name}",
            "createdAt": datetime.utcnow().isoformat()
        }
    }


async def ecr_describe_repositories(environment: Environment, body: dict):
    """
    ECR DescribeRepositories
    List repositories
    """
    repos = environment.oci_resources.get("ecr_repositories", [])

    repositories = []
    for repo in repos:
        repositories.append({
            "repositoryArn": f"arn:aws:ecr:us-east-1:123456789012:repository/{repo['name']}",
            "registryId": environment.id,
            "repositoryName": repo["name"],
            "repositoryUri": f"ecr.{environment.id}.mockfactory.io/{repo['name']}",
            "createdAt": repo.get("created_at", "")
        })

    return {
        "repositories": repositories
    }


async def ecr_put_image(environment: Environment, body: dict):
    """
    ECR PutImage
    Upload image manifest
    """
    repo_name = body.get("repositoryName")
    image_manifest = body.get("imageManifest")
    image_tag = body.get("imageTag", "latest")

    if not repo_name or not image_manifest:
        raise HTTPException(status_code=400, detail="repositoryName and imageManifest required")

    # In real implementation, would proxy to OCIR
    # For POC, just acknowledge receipt

    return {
        "image": {
            "registryId": environment.id,
            "repositoryName": repo_name,
            "imageId": {
                "imageTag": image_tag,
                "imageDigest": "sha256:fake-digest-for-poc"
            }
        }
    }


async def ecr_get_download_url(environment: Environment, body: dict):
    """
    ECR GetDownloadUrlForLayer
    Get presigned URL for layer download
    """
    repo_name = body.get("repositoryName")
    layer_digest = body.get("layerDigest")

    if not repo_name or not layer_digest:
        raise HTTPException(status_code=400, detail="repositoryName and layerDigest required")

    # Generate presigned URL (would proxy to OCIR in production)
    download_url = f"https://ocir.{environment.id}.mockfactory.io/layer/{layer_digest}"

    return {
        "downloadUrl": download_url,
        "layerDigest": layer_digest
    }


# ============================================================================
# GCP Container Registry Emulation
# ============================================================================

@router.get("/gcr/v2/_catalog")
async def gcr_catalog(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    GCR Catalog API
    List all repositories
    """
    environment = get_environment_from_subdomain(request, db)

    repos = environment.oci_resources.get("gcr_repositories", [])
    repo_names = [repo["name"] for repo in repos]

    return {
        "repositories": repo_names
    }


@router.get("/gcr/v2/{repository:path}/tags/list")
async def gcr_list_tags(
    repository: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    GCR List Tags API
    List all tags for a repository
    """
    environment = get_environment_from_subdomain(request, db)

    # Find repository
    repos = environment.oci_resources.get("gcr_repositories", [])
    repo_data = next((r for r in repos if r["name"] == repository), None)

    if not repo_data:
        raise HTTPException(status_code=404, detail="Repository not found")

    tags = repo_data.get("tags", ["latest"])

    return {
        "name": repository,
        "tags": tags
    }


@router.put("/gcr/v2/{repository:path}/manifests/{reference}")
async def gcr_put_manifest(
    repository: str,
    reference: str,
    request: Request,
    content_type: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    GCR Upload Manifest
    Push image manifest
    """
    environment = get_environment_from_subdomain(request, db)

    # Read manifest
    manifest = await request.body()

    # Store repository info
    if not environment.oci_resources:
        environment.oci_resources = {}

    if "gcr_repositories" not in environment.oci_resources:
        environment.oci_resources["gcr_repositories"] = []

    # Find or create repo
    repos = environment.oci_resources["gcr_repositories"]
    repo_data = next((r for r in repos if r["name"] == repository), None)

    if not repo_data:
        repo_data = {
            "name": repository,
            "ocir_path": f"idd2oizp8xvc/{environment.id}/{repository}",
            "tags": []
        }
        repos.append(repo_data)

    # Add tag if not exists
    if reference not in repo_data["tags"]:
        repo_data["tags"].append(reference)

    # In production, would proxy to OCIR here

    return Response(
        status_code=201,
        headers={
            "Docker-Content-Digest": "sha256:fake-digest-for-poc",
            "Location": f"/v2/{repository}/manifests/{reference}"
        }
    )


@router.get("/gcr/v2/{repository:path}/manifests/{reference}")
async def gcr_get_manifest(
    repository: str,
    reference: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    GCR Get Manifest
    Pull image manifest
    """
    environment = get_environment_from_subdomain(request, db)

    # In production, would proxy from OCIR
    # For POC, return mock manifest

    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {
            "size": 1234,
            "digest": "sha256:fake-config-digest"
        },
        "layers": [
            {
                "size": 5678,
                "digest": "sha256:fake-layer-digest"
            }
        ]
    }

    return Response(
        content=json.dumps(manifest),
        media_type="application/vnd.docker.distribution.manifest.v2+json",
        headers={
            "Docker-Content-Digest": "sha256:fake-digest-for-poc"
        }
    )


# ============================================================================
# Docker Registry V2 Protocol (used by both ECR and GCR)
# ============================================================================

@router.get("/v2/")
async def registry_v2_base():
    """Docker Registry V2 API base endpoint"""
    return Response(
        content="{}",
        headers={"Docker-Distribution-Api-Version": "registry/2.0"}
    )


@router.post("/v2/{repository:path}/blobs/uploads/")
async def start_blob_upload(
    repository: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Start blob upload session
    Used by docker push
    """
    environment = get_environment_from_subdomain(request, db)

    # Generate upload UUID
    import uuid
    upload_uuid = str(uuid.uuid4())

    location = f"/v2/{repository}/blobs/uploads/{upload_uuid}"

    return Response(
        status_code=202,
        headers={
            "Location": location,
            "Range": "0-0",
            "Docker-Upload-UUID": upload_uuid
        }
    )


@router.put("/v2/{repository:path}/blobs/uploads/{uuid}")
async def complete_blob_upload(
    repository: str,
    uuid: str,
    request: Request,
    digest: str,
    db: Session = Depends(get_db)
):
    """
    Complete blob upload
    Final step of docker push
    """
    environment = get_environment_from_subdomain(request, db)

    # Read blob data
    blob_data = await request.body()

    # In production, would upload to OCIR here

    return Response(
        status_code=201,
        headers={
            "Location": f"/v2/{repository}/blobs/{digest}",
            "Docker-Content-Digest": digest
        }
    )
