import docker
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProvisioningManager:
    """
    Manages real container lifecycles for MockFactory sub-tenants.
    Rather than just mimicking API responses, this actually spins up genuine 
    Postgres, Redis, RabbitMQ, etc. isolated per tenant.
    """
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            self.client = None
            
    def _get_container_name(self, tenant_id: str, service: str) -> str:
        return f"mf-{service}-{tenant_id}"
        
    def _get_mapped_port(self, container, internal_port: str) -> Optional[str]:
        """Extract the randomly mapped host port for a given internal container port."""
        try:
            # Refresh container state
            container.reload()
            ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            port_bindings = ports.get(internal_port)
            if port_bindings and len(port_bindings) > 0:
                return port_bindings[0]['HostPort']
        except Exception as e:
            logger.error(f"Error getting mapped port: {e}")
        return None

    def _ensure_service(self, tenant_id: str, service: str, image: str, internal_ports: list, env: Dict[str, str] = None) -> Dict[str, Any]:
        """Ensures a container is running for a tenant and returns its connection details."""
        if not self.client:
            return {"status": "error", "message": "Docker socket not available"}
            
        container_name = self._get_container_name(tenant_id, service)
        
        # Prepare ports config for random host port mapping
        ports_config = {f"{p}/tcp": None for p in internal_ports}
        
        try:
            container = self.client.containers.get(container_name)
            if container.status != "running":
                container.start()
        except docker.errors.NotFound:
            try:
                env = env or {}
                labels = {
                    "io.mockfactory.tenant": tenant_id,
                    "io.mockfactory.service": service
                }
                logger.info(f"Provisioning new {service} container for {tenant_id}")
                container = self.client.containers.run(
                    image,
                    name=container_name,
                    detach=True,
                    ports=ports_config,
                    environment=env,
                    labels=labels
                )
            except Exception as e:
                logger.error(f"Error creating {service} for {tenant_id}: {e}")
                return {"status": "error", "message": str(e)}
        
        # Determine the host IP/domain. For now, assuming localhost or the Docker host IP.
        # In production this would be mapped back to the wildcard domain.
        host = "localhost" 
        
        # Extract mapped ports
        mapped_ports = {}
        for p in internal_ports:
            mapped_ports[str(p)] = self._get_mapped_port(container, f"{p}/tcp")
            
        return {
            "status": "running", 
            "id": container.short_id,
            "host": host,
            "ports": mapped_ports
        }

    def provision_postgres(self, tenant_id: str) -> Dict[str, Any]:
        res = self._ensure_service(
            tenant_id, 
            "postgres", 
            "postgres:15-alpine", 
            [5432], 
            env={"POSTGRES_PASSWORD": "mock", "POSTGRES_USER": "mock", "POSTGRES_DB": "mock"}
        )
        if res.get("status") == "running":
            port = res["ports"]["5432"]
            res["connection_string"] = f"postgres://mock:mock@{res['host']}:{port}/mock"
        return res

    def provision_redis(self, tenant_id: str) -> Dict[str, Any]:
        res = self._ensure_service(tenant_id, "redis", "redis:7-alpine", [6379])
        if res.get("status") == "running":
            port = res["ports"]["6379"]
            res["connection_string"] = f"redis://{res['host']}:{port}/0"
        return res

    def provision_rabbitmq(self, tenant_id: str) -> Dict[str, Any]:
        res = self._ensure_service(tenant_id, "rabbitmq", "rabbitmq:3-management-alpine", [5672, 15672])
        if res.get("status") == "running":
            amqp_port = res["ports"]["5672"]
            ui_port = res["ports"]["15672"]
            res["connection_string"] = f"amqp://guest:guest@{res['host']}:{amqp_port}/"
            res["ui_url"] = f"http://{res['host']}:{ui_port}/"
        return res
        
    def provision_mailpit(self, tenant_id: str) -> Dict[str, Any]:
        res = self._ensure_service(tenant_id, "mailpit", "axllent/mailpit", [1025, 8025])
        if res.get("status") == "running":
            smtp_port = res["ports"]["1025"]
            ui_port = res["ports"]["8025"]
            res["connection_string"] = f"smtp://{res['host']}:{smtp_port}"
            res["ui_url"] = f"http://{res['host']}:{ui_port}/"
        return res

    def status(self, tenant_id: str) -> Dict[str, Any]:
        """Get the status of all services for a given tenant without actually provisioning them."""
        if not self.client:
            return {"error": "Docker unavailable"}
            
        services = ["postgres", "redis", "rabbitmq", "mailpit"]
        status_report = {}
        
        for svc in services:
            container_name = self._get_container_name(tenant_id, svc)
            try:
                container = self.client.containers.get(container_name)
                
                # Fetch mapped ports
                internal_ports = []
                if svc == "postgres": internal_ports = [5432]
                elif svc == "redis": internal_ports = [6379]
                elif svc == "rabbitmq": internal_ports = [5672, 15672]
                elif svc == "mailpit": internal_ports = [1025, 8025]
                
                mapped_ports = {}
                for p in internal_ports:
                    mapped_ports[str(p)] = self._get_mapped_port(container, f"{p}/tcp")
                
                # Reconstruct connection strings
                host = "localhost"
                conn_string = ""
                ui_url = ""
                
                if svc == "postgres":
                    conn_string = f"postgres://mock:mock@{host}:{mapped_ports.get('5432')}/mock"
                elif svc == "redis":
                    conn_string = f"redis://{host}:{mapped_ports.get('6379')}/0"
                elif svc == "rabbitmq":
                    conn_string = f"amqp://guest:guest@{host}:{mapped_ports.get('5672')}/"
                    ui_url = f"http://{host}:{mapped_ports.get('15672')}/"
                elif svc == "mailpit":
                    conn_string = f"smtp://{host}:{mapped_ports.get('1025')}"
                    ui_url = f"http://{host}:{mapped_ports.get('8025')}/"
                
                status_report[svc] = {
                    "status": container.status,
                    "id": container.short_id,
                    "connection_string": conn_string,
                    "ui_url": ui_url
                }
            except docker.errors.NotFound:
                status_report[svc] = {
                    "status": "not_provisioned"
                }
                
        return status_report

provisioning_manager = ProvisioningManager()
