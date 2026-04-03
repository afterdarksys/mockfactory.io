from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from typing import Dict, Any
from app.services.provisioning_manager import provisioning_manager

router = APIRouter()

@router.get("/status")
async def get_dashboard_status(request: Request) -> Dict[str, Any]:
    """
    Returns the status and connection strings of the currently provisioned
    real services for this specific tenant's sandbox.
    """
    if not hasattr(request.state, "is_tenant_request") or not request.state.is_tenant_request:
        raise HTTPException(
            status_code=400, 
            detail="This endpoint must be accessed via a client subdomain (e.g., client-1.clients.mockfactory.io)"
        )
        
    tenant_id = request.state.tenant_id
    
    # Get the actual live status of the tenant's containerized services
    status_report = provisioning_manager.status(tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "environment": "isolated-sandbox",
        "services": status_report
    }

@router.post("/provision/{service_name}")
async def provision_service(service_name: str, request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Manually triggers the provisioning of a real service for the tenant."""
    if not hasattr(request.state, "is_tenant_request") or not request.state.is_tenant_request:
        raise HTTPException(
            status_code=400, 
            detail="This endpoint must be accessed via a client subdomain"
        )
        
    tenant_id = request.state.tenant_id
    
    if service_name == "postgres":
        res = provisioning_manager.provision_postgres(tenant_id)
    elif service_name == "redis":
        res = provisioning_manager.provision_redis(tenant_id)
    elif service_name == "rabbitmq":
        res = provisioning_manager.provision_rabbitmq(tenant_id)
    elif service_name == "mailpit":
        res = provisioning_manager.provision_mailpit(tenant_id)
    else:
        raise HTTPException(status_code=400, detail="Unknown or unsupported service")
        
    return res
