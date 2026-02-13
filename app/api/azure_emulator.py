"""
Azure API Emulator
Emulates Microsoft Azure Virtual Machines, Blob Storage, Cosmos DB APIs
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
from app.models.cloud_resources import MockAzureVM, MockAzureBlobStorage

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
# Azure Virtual Machines Emulation
# ============================================================================

@router.put("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_vm_create_or_update(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create or update Azure Virtual Machine"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    # Extract VM properties
    location = body.get("location", "eastus")
    vm_size = body.get("properties", {}).get("hardwareProfile", {}).get("vmSize", "Standard_B1s")
    os_profile = body.get("properties", {}).get("osProfile", {})

    # Check if VM exists (update case)
    vm = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.vm_name == vm_name,
        MockAzureVM.resource_group == resource_group
    ).first()

    private_ip = f"10.0.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"
    public_ip = f"20.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"

    if not vm:
        # Create new VM
        vm = MockAzureVM(
            environment_id=environment.id,
            vm_name=vm_name,
            resource_group=resource_group,
            location=location,
            vm_size=vm_size,
            private_ip_address=private_ip,
            public_ip_address=public_ip,
            os_type=os_profile.get("linuxConfiguration") and "Linux" or "Windows",
            image_reference=body.get("properties", {}).get("storageProfile", {}).get("imageReference"),
            tags=body.get("tags", {}),
            provisioning_state="Succeeded",
            power_state="running"
        )
        db.add(vm)
    else:
        # Update existing VM
        vm.vm_size = vm_size
        vm.tags = body.get("tags", {})

    db.commit()
    db.refresh(vm)

    return {
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}",
        "name": vm_name,
        "type": "Microsoft.Compute/virtualMachines",
        "location": location,
        "tags": vm.tags,
        "properties": {
            "vmId": str(vm.id),
            "hardwareProfile": {
                "vmSize": vm.vm_size
            },
            "provisioningState": vm.provisioning_state,
            "instanceView": {
                "statuses": [
                    {
                        "code": "PowerState/running",
                        "level": "Info",
                        "displayStatus": "VM running"
                    }
                ]
            },
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/networkInterfaces/{vm_name}-nic",
                        "properties": {
                            "primary": True,
                            "ipConfigurations": [
                                {
                                    "name": "ipconfig1",
                                    "properties": {
                                        "privateIPAddress": vm.private_ip_address,
                                        "publicIPAddress": {
                                            "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/publicIPAddresses/{vm_name}-ip"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }


@router.get("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines")
async def azure_vm_list(
    subscription_id: str,
    resource_group: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List Azure Virtual Machines in resource group"""
    environment = get_environment_from_request(request, db)

    vms = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.resource_group == resource_group
    ).all()

    value = []
    for vm in vms:
        value.append({
            "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm.vm_name}",
            "name": vm.vm_name,
            "type": "Microsoft.Compute/virtualMachines",
            "location": vm.location,
            "tags": vm.tags,
            "properties": {
                "vmId": str(vm.id),
                "hardwareProfile": {"vmSize": vm.vm_size},
                "provisioningState": vm.provisioning_state
            }
        })

    return {"value": value}


@router.get("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_vm_get(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get Azure Virtual Machine"""
    environment = get_environment_from_request(request, db)

    vm = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.vm_name == vm_name,
        MockAzureVM.resource_group == resource_group
    ).first()

    if not vm:
        raise HTTPException(status_code=404, detail="Virtual machine not found")

    return {
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}",
        "name": vm_name,
        "type": "Microsoft.Compute/virtualMachines",
        "location": vm.location,
        "tags": vm.tags,
        "properties": {
            "vmId": str(vm.id),
            "hardwareProfile": {"vmSize": vm.vm_size},
            "osProfile": {"computerName": vm_name},
            "provisioningState": vm.provisioning_state,
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "properties": {
                            "ipConfigurations": [
                                {
                                    "properties": {
                                        "privateIPAddress": vm.private_ip_address,
                                        "publicIPAddress": {"ipAddress": vm.public_ip_address}
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }


@router.delete("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_vm_delete(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete Azure Virtual Machine"""
    environment = get_environment_from_request(request, db)

    vm = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.vm_name == vm_name,
        MockAzureVM.resource_group == resource_group
    ).first()

    if not vm:
        raise HTTPException(status_code=404, detail="Virtual machine not found")

    db.delete(vm)
    db.commit()

    return Response(status_code=202)  # Azure returns 202 Accepted for async delete


@router.post("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}/powerOff")
async def azure_vm_power_off(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Power off Azure Virtual Machine"""
    environment = get_environment_from_request(request, db)

    vm = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.vm_name == vm_name,
        MockAzureVM.resource_group == resource_group
    ).first()

    if not vm:
        raise HTTPException(status_code=404, detail="Virtual machine not found")

    vm.power_state = "stopped"
    db.commit()

    return Response(status_code=202)


@router.post("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/{vm_name}/start")
async def azure_vm_start(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Start Azure Virtual Machine"""
    environment = get_environment_from_request(request, db)

    vm = db.query(MockAzureVM).filter(
        MockAzureVM.environment_id == environment.id,
        MockAzureVM.vm_name == vm_name,
        MockAzureVM.resource_group == resource_group
    ).first()

    if not vm:
        raise HTTPException(status_code=404, detail="Virtual machine not found")

    vm.power_state = "running"
    db.commit()

    return Response(status_code=202)


# ============================================================================
# Azure Blob Storage Emulation
# ============================================================================

@router.put("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account_name}")
async def azure_storage_create_account(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create Azure Storage Account"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    location = body.get("location", "eastus")
    kind = body.get("kind", "StorageV2")

    # Check if account exists
    existing = db.query(MockAzureBlobStorage).filter(
        MockAzureBlobStorage.account_name == account_name
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Storage account already exists")

    storage = MockAzureBlobStorage(
        environment_id=environment.id,
        account_name=account_name,
        location=location,
        kind=kind,
        tags=body.get("tags", {})
    )

    db.add(storage)
    db.commit()
    db.refresh(storage)

    return {
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account_name}",
        "name": account_name,
        "type": "Microsoft.Storage/storageAccounts",
        "location": location,
        "kind": kind,
        "properties": {
            "provisioningState": "Succeeded",
            "creationTime": storage.created_time.isoformat() + "Z",
            "primaryEndpoints": {
                "blob": f"https://{account_name}.blob.core.windows.net/",
                "queue": f"https://{account_name}.queue.core.windows.net/",
                "table": f"https://{account_name}.table.core.windows.net/",
                "file": f"https://{account_name}.file.core.windows.net/"
            }
        }
    }


@router.get("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts")
async def azure_storage_list_accounts(
    subscription_id: str,
    resource_group: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List Azure Storage Accounts"""
    environment = get_environment_from_request(request, db)

    accounts = db.query(MockAzureBlobStorage).filter(
        MockAzureBlobStorage.environment_id == environment.id
    ).all()

    value = []
    for account in accounts:
        value.append({
            "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account.account_name}",
            "name": account.account_name,
            "type": "Microsoft.Storage/storageAccounts",
            "location": account.location,
            "kind": account.kind,
            "tags": account.tags
        })

    return {"value": value}


@router.delete("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{account_name}")
async def azure_storage_delete_account(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete Azure Storage Account"""
    environment = get_environment_from_request(request, db)

    account = db.query(MockAzureBlobStorage).filter(
        MockAzureBlobStorage.environment_id == environment.id,
        MockAzureBlobStorage.account_name == account_name
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Storage account not found")

    db.delete(account)
    db.commit()

    return Response(status_code=200)


# ============================================================================
# Azure Cosmos DB Emulation (Basic)
# ============================================================================

@router.get("/azure/subscriptions/{subscription_id}/providers/Microsoft.DocumentDB/databaseAccounts")
async def azure_cosmos_list_accounts(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """List Cosmos DB accounts"""
    environment = get_environment_from_request(request, db)

    # For now, return empty list - can expand later
    return {"value": []}


@router.put("/azure/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.DocumentDB/databaseAccounts/{account_name}")
async def azure_cosmos_create_account(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create Cosmos DB account"""
    environment = get_environment_from_request(request, db)
    body = await request.json()

    # Mock response - can be expanded later
    return {
        "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.DocumentDB/databaseAccounts/{account_name}",
        "name": account_name,
        "type": "Microsoft.DocumentDB/databaseAccounts",
        "location": body.get("location", "eastus"),
        "properties": {
            "provisioningState": "Succeeded",
            "documentEndpoint": f"https://{account_name}.documents.azure.com:443/"
        }
    }
