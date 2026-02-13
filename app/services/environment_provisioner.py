"""
Environment Provisioner - Orchestrates Docker containers and OCI resources
"""
import asyncio
import subprocess
import json
import secrets
import string
import os
import docker
from datetime import datetime
from typing import Dict, List
from sqlalchemy.orm import Session

from app.models.environment import Environment, EnvironmentStatus, EnvironmentUsageLog
from app.models.port_allocation import PortAllocation


class EnvironmentProvisioner:
    """
    Provisions and manages mock environments
    - Spins up Docker containers for databases (Redis, MySQL, etc.)
    - Creates OCI resources for cloud service emulation (S3, etc.)
    - Manages lifecycle (start, stop, destroy)
    """

    def __init__(self, db: Session):
        self.db = db

        # Initialize Docker client
        # Uses DOCKER_HOST env var if set (for docker-proxy)
        # Falls back to unix socket for local development
        docker_host = os.getenv('DOCKER_HOST')
        if docker_host:
            self.docker_client = docker.DockerClient(base_url=docker_host)
        else:
            self.docker_client = docker.from_env()

    def _generate_secure_password(self, length: int = 32) -> str:
        """
        Generate a cryptographically secure random password

        Uses secrets module for CSPRNG
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    async def provision(self, environment: Environment):
        """
        Provision all services for an environment

        Creates:
        - Docker containers for Redis, MySQL, PostgreSQL, MongoDB
        - OCI Object Storage buckets for S3/GCP/Azure emulation
        - Connection strings and endpoints
        """
        try:
            endpoints = {}
            docker_containers = {}
            oci_resources = {}

            # Check if SQS/SNS requested (share same ElasticMQ container)
            has_sqs_or_sns = any(s in ["aws_sqs", "aws_sns"] for s in environment.services.keys())
            elasticmq_container_id = None
            elasticmq_endpoint = None

            # Provision each service
            for service_name, service_config in environment.services.items():
                if service_name in ["redis", "postgresql", "postgresql_supabase", "postgresql_pgvector", "postgresql_postgis"]:
                    # Container-based services
                    container_info = await self._provision_container(
                        environment.id,
                        service_name,
                        service_config
                    )
                    docker_containers[service_name] = container_info["container_id"]
                    endpoints[service_name] = container_info["endpoint"]

                elif service_name in ["aws_sqs", "aws_sns"]:
                    # ElasticMQ for SQS/SNS (share same container)
                    if not elasticmq_container_id:
                        container_info = await self._provision_container(
                            environment.id,
                            "elasticmq",
                            service_config
                        )
                        elasticmq_container_id = container_info["container_id"]
                        elasticmq_endpoint = container_info["endpoint"]
                        docker_containers["elasticmq"] = elasticmq_container_id

                    # Both SQS and SNS use same ElasticMQ endpoint
                    endpoints[service_name] = elasticmq_endpoint

                elif service_name in ["aws_s3", "gcp_storage", "azure_blob"]:
                    # OCI-backed cloud storage emulation
                    oci_info = await self._provision_oci_storage(
                        environment.id,
                        service_name
                    )
                    oci_resources[service_name] = oci_info["bucket_name"]
                    endpoints[service_name] = oci_info["endpoint"]

            # Update environment with endpoints and resource tracking
            environment.endpoints = endpoints
            environment.docker_containers = docker_containers
            environment.oci_resources = oci_resources
            environment.status = EnvironmentStatus.RUNNING
            environment.started_at = datetime.utcnow()

            # Create initial usage log
            usage_log = EnvironmentUsageLog(
                environment_id=environment.id,
                user_id=environment.user_id,
                period_start=datetime.utcnow(),
                hourly_rate=environment.hourly_rate
            )
            self.db.add(usage_log)
            self.db.commit()

        except Exception as e:
            environment.status = EnvironmentStatus.ERROR
            self.db.commit()
            raise e

    async def _provision_container(
        self,
        env_id: str,
        service_type: str,
        config: dict
    ) -> Dict[str, str]:
        """
        Provision a Docker container for a database service

        Returns container ID and connection endpoint
        """
        version = config.get("version", "latest")
        container_name = f"{env_id}-{service_type}"

        # Generate unique secure password for this environment
        db_password = self._generate_secure_password()
        redis_password = self._generate_secure_password()

        # Service-specific Docker configs
        docker_configs = {
            "redis": {
                "image": f"redis:{version}",
                "port": 6379,
                "env": {
                    "REDIS_PASSWORD": redis_password
                },
                "command": f"redis-server --requirepass {redis_password}",
                "connection_template": f"redis://:{redis_password}@localhost:{{port}}"
            },
            "postgresql": {
                "image": f"postgres:{version}",
                "port": 5432,
                "env": {
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "testdb"
                },
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb"
            },
            "postgresql_supabase": {
                "image": f"postgres:{version}",
                "port": 5432,
                "env": {
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "testdb"
                },
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb"
            },
            "postgresql_pgvector": {
                "image": "ankane/pgvector:latest",
                "port": 5432,
                "env": {
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "testdb"
                },
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb"
            },
            "postgresql_postgis": {
                "image": "postgis/postgis:15-3.3",
                "port": 5432,
                "env": {
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "testdb"
                },
                "connection_template": f"postgresql://postgres:{db_password}@localhost:{{port}}/testdb"
            },
            "elasticmq": {
                "image": "softwaremill/elasticmq:latest",
                "port": 9324,
                "env": {},
                "connection_template": "http://localhost:{port}"
            }
        }

        service_config = docker_configs.get(service_type)
        if not service_config:
            raise ValueError(f"Unknown service type: {service_type}")

        # Find available port (atomic database-tracked allocation)
        host_port = await self._get_available_port(env_id, service_type)

        # Run container using Docker SDK (works with docker-proxy)
        try:
            # Prepare port bindings
            ports = {
                f"{service_config['port']}/tcp": host_port
            }

            # Prepare command if specified
            command = None
            if "command" in service_config:
                command = service_config["command"]

            # Run container
            container = self.docker_client.containers.run(
                service_config["image"],
                name=container_name,
                environment=service_config["env"],
                ports=ports,
                detach=True,
                command=command,
                remove=False
            )

            container_id = container.id

        except docker.errors.APIError as e:
            raise RuntimeError(f"Failed to start {service_type} container: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Docker error for {service_type}: {str(e)}")

        # Generate connection string
        endpoint = service_config["connection_template"].format(port=host_port)

        return {
            "container_id": container_id,
            "endpoint": endpoint,
            "host_port": host_port
        }

    async def _get_available_port(self, environment_id: str, service_name: str) -> int:
        """
        Find and atomically allocate an available port for container port mapping

        Port range: 30000-40000
        Uses database transaction to prevent race conditions
        """
        PORT_RANGE_START = 30000
        PORT_RANGE_END = 40000
        MAX_RETRIES = 100

        for attempt in range(MAX_RETRIES):
            # Find first available port not in use
            allocated_ports = self.db.query(PortAllocation.port).filter(
                PortAllocation.is_active == True
            ).all()
            allocated_port_set = {p[0] for p in allocated_ports}

            # Find first free port
            for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
                if port not in allocated_port_set:
                    # Try to allocate this port atomically
                    try:
                        allocation = PortAllocation(
                            port=port,
                            environment_id=environment_id,
                            service_name=service_name,
                            is_active=True
                        )
                        self.db.add(allocation)
                        self.db.commit()
                        return port
                    except Exception as e:
                        # Unique constraint violation - port was allocated by another transaction
                        # Roll back and try next port
                        self.db.rollback()
                        continue

            # All ports checked in this iteration, wait briefly and retry
            await asyncio.sleep(0.1)

        raise RuntimeError(
            f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}. "
            f"All {PORT_RANGE_END - PORT_RANGE_START + 1} ports are allocated."
        )

    async def _provision_oci_storage(
        self,
        env_id: str,
        service_type: str
    ) -> Dict[str, str]:
        """
        Provision OCI Object Storage bucket for S3/GCP/Azure emulation

        Returns bucket name and emulated endpoint
        """
        bucket_name = f"mockfactory-{env_id}-{service_type}"

        # Create OCI bucket using CLI
        # Note: Replace with proper OCI SDK in production
        cmd = [
            "oci", "os", "bucket", "create",
            "--name", bucket_name,
            "--compartment-id", "ocid1.compartment.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create OCI bucket: {result.stderr}")
        except Exception as e:
            # Bucket might already exist, that's okay
            print(f"Warning: {e}")

        # Generate emulated endpoint
        # These will be served by our API emulation layer
        endpoints_map = {
            "aws_s3": f"https://s3.{env_id}.mockfactory.io",
            "gcp_storage": f"https://storage.{env_id}.mockfactory.io",
            "azure_blob": f"https://blob.{env_id}.mockfactory.io"
        }

        return {
            "bucket_name": bucket_name,
            "endpoint": endpoints_map.get(service_type, f"https://{env_id}.mockfactory.io")
        }

    async def stop(self, environment: Environment):
        """Stop all containers for an environment"""
        if not environment.docker_containers:
            return

        for service_name, container_id in environment.docker_containers.items():
            try:
                container = self.docker_client.containers.get(container_id)
                container.stop(timeout=10)
            except docker.errors.NotFound:
                print(f"Warning: Container {container_id} not found for {service_name}")
            except docker.errors.APIError as e:
                print(f"Warning: Failed to stop {service_name} container: {e}")

        # Close current usage log
        active_log = self.db.query(EnvironmentUsageLog).filter(
            EnvironmentUsageLog.environment_id == environment.id,
            EnvironmentUsageLog.period_end.is_(None)
        ).first()

        if active_log:
            active_log.period_end = datetime.utcnow()
            # Calculate cost: (end - start) in hours * hourly_rate
            duration_hours = (active_log.period_end - active_log.period_start).total_seconds() / 3600
            active_log.cost = round(duration_hours * active_log.hourly_rate, 2)
            environment.total_cost += active_log.cost
            self.db.commit()

    async def start(self, environment: Environment):
        """Start all stopped containers for an environment"""
        if not environment.docker_containers:
            return

        for service_name, container_id in environment.docker_containers.items():
            try:
                container = self.docker_client.containers.get(container_id)
                container.start()
            except docker.errors.NotFound:
                print(f"Warning: Container {container_id} not found for {service_name}")
            except docker.errors.APIError as e:
                print(f"Warning: Failed to start {service_name} container: {e}")

        # Create new usage log
        usage_log = EnvironmentUsageLog(
            environment_id=environment.id,
            user_id=environment.user_id,
            period_start=datetime.utcnow(),
            hourly_rate=environment.hourly_rate
        )
        self.db.add(usage_log)
        self.db.commit()

    async def destroy(self, environment: Environment):
        """Destroy all resources for an environment"""
        # Release allocated ports
        port_allocations = self.db.query(PortAllocation).filter(
            PortAllocation.environment_id == environment.id,
            PortAllocation.is_active == True
        ).all()

        for allocation in port_allocations:
            allocation.release()

        self.db.commit()

        # Stop and remove containers
        if environment.docker_containers:
            for service_name, container_id in environment.docker_containers.items():
                try:
                    container = self.docker_client.containers.get(container_id)
                    # Stop with timeout
                    container.stop(timeout=10)
                    # Remove container
                    container.remove()
                except docker.errors.NotFound:
                    print(f"Warning: Container {container_id} not found for {service_name}")
                except docker.errors.APIError as e:
                    print(f"Warning: Failed to remove {service_name} container: {e}")

        # Delete OCI buckets
        if environment.oci_resources:
            for service_name, bucket_name in environment.oci_resources.items():
                try:
                    # Delete all objects first
                    subprocess.run([
                        "oci", "os", "object", "bulk-delete",
                        "--bucket-name", bucket_name,
                        "--force"
                    ], capture_output=True)

                    # Delete bucket
                    subprocess.run([
                        "oci", "os", "bucket", "delete",
                        "--bucket-name", bucket_name,
                        "--force"
                    ], capture_output=True)
                except Exception as e:
                    print(f"Warning: Failed to delete {service_name} bucket: {e}")

        # Close final usage log and calculate total
        active_log = self.db.query(EnvironmentUsageLog).filter(
            EnvironmentUsageLog.environment_id == environment.id,
            EnvironmentUsageLog.period_end.is_(None)
        ).first()

        if active_log:
            active_log.period_end = datetime.utcnow()
            duration_hours = (active_log.period_end - active_log.period_start).total_seconds() / 3600
            active_log.cost = round(duration_hours * active_log.hourly_rate, 2)
            environment.total_cost += active_log.cost
            self.db.commit()
