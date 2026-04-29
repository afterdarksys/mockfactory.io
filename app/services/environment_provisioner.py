"""
Environment Provisioner - Orchestrates Docker containers and MinIO/Registry resources
"""
import asyncio
import json
import secrets
import string
import os
import docker
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from datetime import datetime
from typing import Dict
from sqlalchemy.orm import Session

from app.models.environment import Environment, EnvironmentStatus, EnvironmentUsageLog
from app.models.port_allocation import PortAllocation


def _get_minio_client():
    """Return a boto3 S3 client pointed at the local MinIO instance."""
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("MINIO_ROOT_USER", "mockfactory"),
        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "mockfactory123"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


class EnvironmentProvisioner:
    """
    Provisions and manages mock environments.
    Spins up Docker containers for databases (Redis, MySQL, etc.)
    and MinIO buckets for cloud storage emulation (S3, GCS, Azure Blob).
    Everything runs on bare metal via Docker — no external cloud dependency.
    """

    def __init__(self, db: Session):
        self.db = db
        docker_host = os.getenv("DOCKER_HOST")
        if docker_host:
            self.docker_client = docker.DockerClient(base_url=docker_host)
        else:
            self.docker_client = docker.from_env()

    def _generate_secure_password(self, length: int = 32) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def provision(self, environment: Environment):
        """
        Provision all services for an environment.

        Container services (Redis, PostgreSQL, etc.) are started as Docker containers.
        Cloud storage services (S3, GCS, Azure) get a dedicated MinIO bucket.
        """
        try:
            endpoints = {}
            docker_containers = {}
            # Reuse the oci_resources column for generic mock resource tracking
            mock_resources = {}

            has_sqs_or_sns = any(s in ["aws_sqs", "aws_sns"] for s in environment.services.keys())
            elasticmq_container_id = None
            elasticmq_endpoint = None

            for service_name, service_config in environment.services.items():
                if service_name in [
                    "redis",
                    "postgresql",
                    "postgresql_supabase",
                    "postgresql_pgvector",
                    "postgresql_postgis",
                ]:
                    container_info = await self._provision_container(
                        environment.id, service_name, service_config
                    )
                    docker_containers[service_name] = container_info["container_id"]
                    endpoints[service_name] = container_info["endpoint"]

                elif service_name in ["aws_sqs", "aws_sns"]:
                    if not elasticmq_container_id:
                        container_info = await self._provision_container(
                            environment.id, "elasticmq", service_config
                        )
                        elasticmq_container_id = container_info["container_id"]
                        elasticmq_endpoint = container_info["endpoint"]
                        docker_containers["elasticmq"] = elasticmq_container_id
                    endpoints[service_name] = elasticmq_endpoint

                elif service_name in ["aws_s3", "gcp_storage", "azure_blob"]:
                    bucket_info = await self._provision_minio_bucket(
                        environment.id, service_name
                    )
                    mock_resources[service_name] = bucket_info["bucket_name"]
                    endpoints[service_name] = bucket_info["endpoint"]

            environment.endpoints = endpoints
            environment.docker_containers = docker_containers
            environment.oci_resources = mock_resources  # column reused for generic resources
            environment.status = EnvironmentStatus.RUNNING
            environment.started_at = datetime.utcnow()

            usage_log = EnvironmentUsageLog(
                environment_id=environment.id,
                user_id=environment.user_id,
                period_start=datetime.utcnow(),
                hourly_rate=environment.hourly_rate,
            )
            self.db.add(usage_log)
            self.db.commit()

        except Exception as e:
            environment.status = EnvironmentStatus.ERROR
            self.db.commit()
            raise e

    async def _provision_container(
        self, env_id: str, service_type: str, config: dict
    ) -> Dict[str, str]:
        """Spin up a Docker container for a database/queue service."""
        version = config.get("version", "latest")
        container_name = f"{env_id}-{service_type}"

        db_password = self._generate_secure_password()
        redis_password = self._generate_secure_password()

        docker_configs = {
            "redis": {
                "image": f"redis:{version}",
                "port": 6379,
                "env": {"REDIS_PASSWORD": redis_password},
                "command": f"redis-server --requirepass {redis_password}",
                "connection_template": f"redis://:{redis_password}@localhost:{{port}}",
            },
            "postgresql": {
                "image": f"postgres:{version}",
                "port": 5432,
                "env": {"POSTGRES_PASSWORD": db_password, "POSTGRES_DB": "testdb"},
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb",
            },
            "postgresql_supabase": {
                "image": f"postgres:{version}",
                "port": 5432,
                "env": {"POSTGRES_PASSWORD": db_password, "POSTGRES_DB": "testdb"},
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb",
            },
            "postgresql_pgvector": {
                "image": "ankane/pgvector:latest",
                "port": 5432,
                "env": {"POSTGRES_PASSWORD": db_password, "POSTGRES_DB": "testdb"},
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb",
            },
            "postgresql_postgis": {
                "image": "postgis/postgis:15-3.3",
                "port": 5432,
                "env": {"POSTGRES_PASSWORD": db_password, "POSTGRES_DB": "testdb"},
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb",
            },
            "elasticmq": {
                "image": "softwaremill/elasticmq:latest",
                "port": 9324,
                "env": {},
                "connection_template": "http://localhost:{port}",
            },
        }

        service_config = docker_configs.get(service_type)
        if not service_config:
            raise ValueError(f"Unknown service type: {service_type}")

        host_port = await self._get_available_port(env_id, service_type)

        try:
            ports = {f"{service_config['port']}/tcp": host_port}
            command = service_config.get("command")

            container = self.docker_client.containers.run(
                service_config["image"],
                name=container_name,
                environment=service_config["env"],
                ports=ports,
                detach=True,
                command=command,
                remove=False,
            )
            container_id = container.id

        except docker.errors.APIError as e:
            raise RuntimeError(f"Failed to start {service_type} container: {str(e)}")

        endpoint = service_config["connection_template"].format(port=host_port)
        return {"container_id": container_id, "endpoint": endpoint, "host_port": host_port}

    async def _provision_minio_bucket(
        self, env_id: str, service_type: str
    ) -> Dict[str, str]:
        """
        Create a MinIO bucket for S3/GCS/Azure emulation.
        Bucket name is namespaced per environment and service type.
        """
        bucket_name = f"env-{env_id}-{service_type.replace('_', '-')}"
        s3 = _get_minio_client()

        try:
            s3.create_bucket(Bucket=bucket_name)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise RuntimeError(f"Failed to create MinIO bucket {bucket_name}: {e}")

        endpoints_map = {
            "aws_s3": f"https://s3.{env_id}.mockfactory.io",
            "gcp_storage": f"https://storage.{env_id}.mockfactory.io",
            "azure_blob": f"https://blob.{env_id}.mockfactory.io",
        }

        return {
            "bucket_name": bucket_name,
            "endpoint": endpoints_map.get(service_type, f"https://{env_id}.mockfactory.io"),
        }

    async def _get_available_port(self, environment_id: str, service_name: str) -> int:
        """Atomically allocate an available host port in the 30000-40000 range."""
        PORT_RANGE_START = 30000
        PORT_RANGE_END = 40000
        MAX_RETRIES = 100

        for attempt in range(MAX_RETRIES):
            allocated_ports = self.db.query(PortAllocation.port).filter(
                PortAllocation.is_active == True
            ).all()
            allocated_port_set = {p[0] for p in allocated_ports}

            for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
                if port not in allocated_port_set:
                    try:
                        allocation = PortAllocation(
                            port=port,
                            environment_id=environment_id,
                            service_name=service_name,
                            is_active=True,
                        )
                        self.db.add(allocation)
                        self.db.commit()
                        return port
                    except Exception:
                        self.db.rollback()
                        continue

            await asyncio.sleep(0.1)

        raise RuntimeError(
            f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}."
        )

    async def stop(self, environment: Environment):
        """Stop all containers for an environment."""
        if environment.docker_containers:
            for service_name, container_id in environment.docker_containers.items():
                try:
                    container = self.docker_client.containers.get(container_id)
                    container.stop(timeout=10)
                except docker.errors.NotFound:
                    print(f"Warning: Container {container_id} not found for {service_name}")
                except docker.errors.APIError as e:
                    print(f"Warning: Failed to stop {service_name} container: {e}")

        active_log = self.db.query(EnvironmentUsageLog).filter(
            EnvironmentUsageLog.environment_id == environment.id,
            EnvironmentUsageLog.period_end.is_(None),
        ).first()

        if active_log:
            active_log.period_end = datetime.utcnow()
            duration_hours = (active_log.period_end - active_log.period_start).total_seconds() / 3600
            active_log.cost = round(duration_hours * active_log.hourly_rate, 2)
            environment.total_cost += active_log.cost
            self.db.commit()

    async def start(self, environment: Environment):
        """Start all stopped containers for an environment."""
        if environment.docker_containers:
            for service_name, container_id in environment.docker_containers.items():
                try:
                    container = self.docker_client.containers.get(container_id)
                    container.start()
                except docker.errors.NotFound:
                    print(f"Warning: Container {container_id} not found for {service_name}")
                except docker.errors.APIError as e:
                    print(f"Warning: Failed to start {service_name} container: {e}")

        usage_log = EnvironmentUsageLog(
            environment_id=environment.id,
            user_id=environment.user_id,
            period_start=datetime.utcnow(),
            hourly_rate=environment.hourly_rate,
        )
        self.db.add(usage_log)
        self.db.commit()

    async def destroy(self, environment: Environment):
        """Destroy all resources for an environment — containers and MinIO buckets."""
        # Release port allocations
        port_allocations = self.db.query(PortAllocation).filter(
            PortAllocation.environment_id == environment.id,
            PortAllocation.is_active == True,
        ).all()
        for allocation in port_allocations:
            allocation.release()
        self.db.commit()

        # Stop and remove containers
        if environment.docker_containers:
            for service_name, container_id in environment.docker_containers.items():
                try:
                    container = self.docker_client.containers.get(container_id)
                    container.stop(timeout=10)
                    container.remove()
                except docker.errors.NotFound:
                    print(f"Warning: Container {container_id} not found for {service_name}")
                except docker.errors.APIError as e:
                    print(f"Warning: Failed to remove {service_name} container: {e}")

        # Delete MinIO buckets
        if environment.oci_resources:
            s3 = _get_minio_client()
            for service_name, bucket_name in environment.oci_resources.items():
                if not isinstance(bucket_name, str):
                    continue  # skip non-bucket entries (e.g. ecr_repositories list)
                try:
                    # Delete all objects first
                    paginator = s3.get_paginator("list_objects_v2")
                    for page in paginator.paginate(Bucket=bucket_name):
                        objects = page.get("Contents", [])
                        if objects:
                            s3.delete_objects(
                                Bucket=bucket_name,
                                Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                            )
                    s3.delete_bucket(Bucket=bucket_name)
                except ClientError as e:
                    print(f"Warning: Failed to delete bucket {bucket_name}: {e}")

        # Close final usage log
        active_log = self.db.query(EnvironmentUsageLog).filter(
            EnvironmentUsageLog.environment_id == environment.id,
            EnvironmentUsageLog.period_end.is_(None),
        ).first()

        if active_log:
            active_log.period_end = datetime.utcnow()
            duration_hours = (active_log.period_end - active_log.period_start).total_seconds() / 3600
            active_log.cost = round(duration_hours * active_log.hourly_rate, 2)
            environment.total_cost += active_log.cost
            self.db.commit()
