from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import re
import logging

logger = logging.getLogger(__name__)

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to detect if the request is for a specific client environment 
    (e.g., client-123.clients.mockfactory.io) and attach the tenant ID.
    """
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        # Also check x-forwarded-host in case of proxies
        x_forwarded_host = request.headers.get("x-forwarded-host")
        if x_forwarded_host:
            host = x_forwarded_host
            
        # Provide a default tenant
        request.state.tenant_id = None
        request.state.is_tenant_request = False

        # Match pattern: <tenant-id>.clients.mockfactory.io or <tenant-id>.clients.mockfactory.local
        # Example domains:
        # env-123.clients.mockfactory.io
        # client_abc.clients.mockfactory.local:8000 (with port)
        
        # Remove port if present
        host_no_port = host.split(":")[0]
        
        match = re.match(r"^([a-zA-Z0-9_-]+)\.clients\.mockfactory\.(io|local)$", host_no_port)
        if match:
            tenant_id = match.group(1)
            request.state.tenant_id = tenant_id
            request.state.is_tenant_request = True
            
        response = await call_next(request)
        return response
