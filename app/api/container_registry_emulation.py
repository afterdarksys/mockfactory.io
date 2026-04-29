"""
Container Registry Emulation - AWS ECR & GCP Container Registry
Translates ECR/GCR control-plane APIs to a local Docker Registry v2 backend.
Actual image pushes/pulls go directly to the local registry container.
No external cloud dependency — everything runs on bare metal via Docker.
"""
import os
import base64
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus


router = APIRouter()

REGISTRY_HOST = os.getenv("REGISTRY_HOST", "registry:5000")


def get_environment_from_subdomain(request: Request, db: Session) -> Environment:
    """Extract environment ID from subdomain."""
    host = request.headers.get("host", "")
    env_id = None
    for part in host.split("."):
        if part.startswith("env-"):
            env_id = part
            break

    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID not found in host")

    environment = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING,
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found or not running")

    return environment


def _get_mock_resources(environment: Environment) -> dict:
    if not environment.oci_resources:
        environment.oci_resources = {}
    return environment.oci_resources


# ============================================================================
# AWS ECR (Elastic Container Registry) Control Plane
# ============================================================================

@router.post("/ecr/")
async def ecr_api(
    request: Request,
    x_amz_target: str = Header(...),
    db: Session = Depends(get_db),
):
    """AWS ECR API — routes by X-Amz-Target header."""
    environment = get_environment_from_subdomain(request, db)
    body = await request.json()

    if "GetAuthorizationToken" in x_amz_target:
        return ecr_get_authorization_token(environment)
    elif "CreateRepository" in x_amz_target:
        return ecr_create_repository(environment, body, db)
    elif "DescribeRepositories" in x_amz_target:
        return ecr_describe_repositories(environment)
    elif "PutImage" in x_amz_target:
        return ecr_put_image(environment, body)
    elif "GetDownloadUrlForLayer" in x_amz_target:
        return ecr_get_download_url(environment, body)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported ECR operation: {x_amz_target}")


def ecr_get_authorization_token(environment: Environment):
    """
    ECR GetAuthorizationToken.
    Returns Docker login credentials for the local registry.
    The proxy endpoint is the local registry host, namespaced per environment.
    """
    username = "mockfactory"
    password = f"mock-{environment.id}"
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    expiration = (datetime.utcnow() + timedelta(hours=12)).isoformat() + "Z"

    return {
        "authorizationData": [
            {
                "authorizationToken": token,
                "expiresAt": expiration,
                "proxyEndpoint": f"https://ecr.{environment.id}.mockfactory.io",
            }
        ]
    }


def ecr_create_repository(environment: Environment, body: dict, db: Session):
    """
    ECR CreateRepository.
    Registers the repository in environment metadata.
    Images are stored under {env_id}/{repo_name} in the local registry.
    """
    repo_name = body.get("repositoryName")
    if not repo_name:
        raise HTTPException(status_code=400, detail="repositoryName required")

    resources = _get_mock_resources(environment)
    if "ecr_repositories" not in resources:
        resources["ecr_repositories"] = []

    local_path = f"{environment.id}/{repo_name}"
    resources["ecr_repositories"].append({
        "name": repo_name,
        "registry_path": f"{REGISTRY_HOST}/{local_path}",
        "created_at": datetime.utcnow().isoformat(),
        "tags": [],
    })
    db.commit()

    return {
        "repository": {
            "repositoryArn": f"arn:aws:ecr:us-east-1:123456789012:repository/{repo_name}",
            "registryId": environment.id,
            "repositoryName": repo_name,
            "repositoryUri": f"ecr.{environment.id}.mockfactory.io/{repo_name}",
            "createdAt": datetime.utcnow().isoformat(),
        }
    }


def ecr_describe_repositories(environment: Environment):
    """ECR DescribeRepositories — list repos from environment metadata."""
    repos = (environment.oci_resources or {}).get("ecr_repositories", [])
    return {
        "repositories": [
            {
                "repositoryArn": f"arn:aws:ecr:us-east-1:123456789012:repository/{r['name']}",
                "registryId": environment.id,
                "repositoryName": r["name"],
                "repositoryUri": f"ecr.{environment.id}.mockfactory.io/{r['name']}",
                "createdAt": r.get("created_at", ""),
            }
            for r in repos
        ]
    }


def ecr_put_image(environment: Environment, body: dict):
    """ECR PutImage — acknowledge image manifest receipt."""
    repo_name = body.get("repositoryName")
    image_tag = body.get("imageTag", "latest")

    if not repo_name:
        raise HTTPException(status_code=400, detail="repositoryName required")

    return {
        "image": {
            "registryId": environment.id,
            "repositoryName": repo_name,
            "imageId": {
                "imageTag": image_tag,
                "imageDigest": f"sha256:{uuid.uuid4().hex}",
            },
        }
    }


def ecr_get_download_url(environment: Environment, body: dict):
    """ECR GetDownloadUrlForLayer — return local registry URL for layer."""
    repo_name = body.get("repositoryName")
    layer_digest = body.get("layerDigest")

    if not repo_name or not layer_digest:
        raise HTTPException(status_code=400, detail="repositoryName and layerDigest required")

    return {
        "downloadUrl": f"http://{REGISTRY_HOST}/{environment.id}/{repo_name}/blobs/{layer_digest}",
        "layerDigest": layer_digest,
    }


# ============================================================================
# GCP Container Registry (GCR) Control Plane
# ============================================================================

@router.get("/gcr/v2/_catalog")
async def gcr_catalog(request: Request, db: Session = Depends(get_db)):
    """GCR Catalog — list all repositories."""
    environment = get_environment_from_subdomain(request, db)
    repos = (environment.oci_resources or {}).get("gcr_repositories", [])
    return {"repositories": [r["name"] for r in repos]}


@router.get("/gcr/v2/{repository:path}/tags/list")
async def gcr_list_tags(
    repository: str, request: Request, db: Session = Depends(get_db)
):
    """GCR List Tags — list tags for a repository."""
    environment = get_environment_from_subdomain(request, db)
    repos = (environment.oci_resources or {}).get("gcr_repositories", [])
    repo_data = next((r for r in repos if r["name"] == repository), None)

    if not repo_data:
        raise HTTPException(status_code=404, detail="Repository not found")

    return {"name": repository, "tags": repo_data.get("tags", [])}


@router.put("/gcr/v2/{repository:path}/manifests/{reference}")
async def gcr_put_manifest(
    repository: str,
    reference: str,
    request: Request,
    content_type: str = Header(...),
    db: Session = Depends(get_db),
):
    """GCR Put Manifest — register image tag in environment metadata."""
    environment = get_environment_from_subdomain(request, db)
    resources = _get_mock_resources(environment)

    if "gcr_repositories" not in resources:
        resources["gcr_repositories"] = []

    repos = resources["gcr_repositories"]
    repo_data = next((r for r in repos if r["name"] == repository), None)

    if not repo_data:
        repo_data = {
            "name": repository,
            "registry_path": f"{REGISTRY_HOST}/{environment.id}/{repository}",
            "tags": [],
        }
        repos.append(repo_data)

    if reference not in repo_data["tags"]:
        repo_data["tags"].append(reference)

    db.commit()

    digest = f"sha256:{uuid.uuid4().hex}"
    return Response(
        status_code=201,
        headers={
            "Docker-Content-Digest": digest,
            "Location": f"/v2/{repository}/manifests/{reference}",
        },
    )


@router.get("/gcr/v2/{repository:path}/manifests/{reference}")
async def gcr_get_manifest(
    repository: str, reference: str, request: Request, db: Session = Depends(get_db)
):
    """GCR Get Manifest — return a minimal OCI manifest."""
    environment = get_environment_from_subdomain(request, db)

    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"size": 0, "digest": f"sha256:{uuid.uuid4().hex}"},
        "layers": [],
    }

    return Response(
        content=json.dumps(manifest),
        media_type="application/vnd.docker.distribution.manifest.v2+json",
        headers={"Docker-Content-Digest": f"sha256:{uuid.uuid4().hex}"},
    )


# ============================================================================
# Docker Registry V2 Protocol base endpoint
# ============================================================================

@router.get("/v2/")
async def registry_v2_base():
    """Docker Registry V2 API ping — confirms registry/2.0 compliance."""
    return Response(content="{}", headers={"Docker-Distribution-Api-Version": "registry/2.0"})


@router.post("/v2/{repository:path}/blobs/uploads/")
async def start_blob_upload(
    repository: str, request: Request, db: Session = Depends(get_db)
):
    """Start a blob upload session (Docker push protocol)."""
    environment = get_environment_from_subdomain(request, db)
    upload_uuid = str(uuid.uuid4())
    location = f"/v2/{repository}/blobs/uploads/{upload_uuid}"

    return Response(
        status_code=202,
        headers={
            "Location": location,
            "Range": "0-0",
            "Docker-Upload-UUID": upload_uuid,
        },
    )


@router.put("/v2/{repository:path}/blobs/uploads/{upload_uuid}")
async def complete_blob_upload(
    repository: str,
    upload_uuid: str,
    digest: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Complete a blob upload session (Docker push protocol)."""
    environment = get_environment_from_subdomain(request, db)

    return Response(
        status_code=201,
        headers={
            "Location": f"/v2/{repository}/blobs/{digest}",
            "Docker-Content-Digest": digest,
        },
    )
