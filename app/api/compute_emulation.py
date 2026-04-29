"""
GCP Compute Engine + Azure VM Emulation
Both backed entirely by in-memory state stored in environment.oci_resources.
No external cloud dependency — pure Docker host.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    azure_error,
    azure_headers,
    azure_resource_id,
    azure_subscription,
    AZURE_VM_SIZES,
    ec2_volume_id,
    find_by_id,
    flag_resources_modified,
    gcp_disk_id,
    gcp_error,
    gcp_headers,
    gcp_instance_id,
    gcp_network_id,
    gcp_operation_id,
    gcp_project,
    gcp_self_link,
    gcp_zone_self_link,
    GCP_INSTANCE_STATES,
    GCP_MACHINE_TYPES,
    new_uuid,
    paginate,
    random_private_ip,
    random_public_ip,
    remove_by_id,
    utcnow_azure,
    utcnow_gcp,
    utcnow_iso,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DEFAULT_GCP_PROJECT = "mockfactory-dev"
DEFAULT_GCP_ZONE = "us-central1-a"
DEFAULT_GCP_REGION = "us-central1"
DEFAULT_AZURE_SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
DEFAULT_AZURE_RESOURCE_GROUP = "mockfactory-rg"
DEFAULT_AZURE_LOCATION = "eastus"


def _get_env(request: Request, db: Session) -> Environment:
    host = request.headers.get("host", "")
    env_id = next((p for p in host.split(".") if p.startswith("env-")), None)
    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID not found in host")
    env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING,
    ).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found or not running")
    return env


def _res(env: Environment) -> Dict:
    if env.oci_resources is None:
        env.oci_resources = {}
    return env.oci_resources


def _ns(res: Dict, key: str) -> List:
    if key not in res:
        res[key] = []
    return res[key]


def _gcp_operation(op_type: str, resource_link: str, status: str = "DONE") -> Dict:
    return {
        "kind": "compute#operation",
        "id": str(random.randint(10**18, 10**19 - 1)),
        "name": gcp_operation_id(),
        "operationType": op_type,
        "targetLink": resource_link,
        "status": status,
        "progress": 100,
        "insertTime": utcnow_gcp(),
        "startTime": utcnow_gcp(),
        "endTime": utcnow_gcp(),
        "zone": f"https://www.googleapis.com/compute/v1/projects/{DEFAULT_GCP_PROJECT}/zones/{DEFAULT_GCP_ZONE}",
    }


# ============================================================================
# GCP Compute Engine
# ============================================================================

# --- Zones & Machine Types ---

@router.get("/gcp/compute/v1/projects/{project}/zones")
async def gcp_list_zones(project: str, request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    zones = [
        {"name": z, "status": "UP",
         "selfLink": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{z}",
         "region": f"https://www.googleapis.com/compute/v1/projects/{project}/regions/{z.rsplit('-', 1)[0]}"}
        for z in ["us-central1-a", "us-central1-b", "us-east1-b", "us-west1-a",
                  "europe-west1-b", "asia-east1-a"]
    ]
    return {"kind": "compute#zoneList", "id": "zones", "items": zones,
            "selfLink": f"https://www.googleapis.com/compute/v1/projects/{project}/zones"}


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/machineTypes")
async def gcp_list_machine_types(project: str, zone: str, request: Request,
                                  db: Session = Depends(get_db)):
    _get_env(request, db)
    types = [
        {"kind": "compute#machineType", "name": mt,
         "description": mt,
         "guestCpus": 2 if "2" in mt else 4,
         "memoryMb": 3840,
         "selfLink": gcp_self_link("machineTypes", mt, project, zone),
         "zone": zone}
        for mt in GCP_MACHINE_TYPES
    ]
    return {"kind": "compute#machineTypeList", "items": types}


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/machineTypes/{machine_type}")
async def gcp_get_machine_type(project: str, zone: str, machine_type: str,
                                request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    return {"kind": "compute#machineType", "name": machine_type,
            "selfLink": gcp_self_link("machineTypes", machine_type, project, zone),
            "zone": zone, "guestCpus": 2, "memoryMb": 3840}


# --- Images ---

@router.get("/gcp/compute/v1/projects/{project}/global/images")
async def gcp_list_images(project: str, request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    images = [
        {"kind": "compute#image", "id": str(random.randint(10**18, 10**19 - 1)),
         "name": name, "family": family, "status": "READY",
         "diskSizeGb": "10",
         "selfLink": f"https://www.googleapis.com/compute/v1/projects/debian-cloud/global/images/{name}",
         "creationTimestamp": utcnow_gcp()}
        for name, family in [
            ("debian-11-bullseye-v20240213", "debian-11"),
            ("ubuntu-2204-jammy-v20240213", "ubuntu-2204-lts"),
            ("centos-stream-9-v20240213", "centos-stream-9"),
        ]
    ]
    return {"kind": "compute#imageList", "items": images}


# --- Instances ---

@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/instances")
async def gcp_create_instance(project: str, zone: str, request: Request,
                               db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    instances = _ns(res, "gcp_instances")

    name = body.get("name") or f"instance-{new_uuid()[:8]}"
    machine_type = body.get("machineType", f"zones/{zone}/machineTypes/n1-standard-1").split("/")[-1]

    existing = find_by_id(instances, "name", name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Instance {name} already exists")

    iid = gcp_instance_id()
    instance = {
        "kind": "compute#instance",
        "id": iid,
        "name": name,
        "zone": gcp_zone_self_link(zone, project),
        "machineType": gcp_self_link("machineTypes", machine_type, project, zone),
        "status": "RUNNING",
        "statusMessage": "",
        "selfLink": gcp_self_link("instances", name, project, zone),
        "networkInterfaces": [
            {
                "kind": "compute#networkInterface",
                "network": gcp_self_link("networks", "default", project, zone),
                "subnetwork": f"https://www.googleapis.com/compute/v1/projects/{project}/regions/{zone.rsplit('-', 1)[0]}/subnetworks/default",
                "networkIP": random_private_ip(len(instances)),
                "name": "nic0",
                "fingerprint": uuid.uuid4().hex[:12],
                "accessConfigs": [
                    {
                        "kind": "compute#accessConfig",
                        "type": "ONE_TO_ONE_NAT",
                        "name": "External NAT",
                        "natIP": random_public_ip(),
                    }
                ],
            }
        ],
        "disks": [
            {
                "kind": "compute#attachedDisk",
                "type": "PERSISTENT",
                "mode": "READ_WRITE",
                "source": gcp_self_link("disks", name, project, zone),
                "deviceName": "persistent-disk-0",
                "index": 0,
                "boot": True,
                "autoDelete": True,
                "interface": "SCSI",
            }
        ],
        "metadata": body.get("metadata", {"kind": "compute#metadata", "items": []}),
        "tags": body.get("tags", {"items": [], "fingerprint": uuid.uuid4().hex[:12]}),
        "labels": body.get("labels", {}),
        "creationTimestamp": utcnow_gcp(),
        "lastStartTimestamp": utcnow_gcp(),
        "startRestricted": False,
        "deletionProtection": False,
        "fingerprint": uuid.uuid4().hex[:12],
    }

    instances.append(instance)
    flag_resources_modified(db, env)

    return Response(
        content=str(_gcp_operation("insert", instance["selfLink"])),
        media_type="application/json",
        status_code=200,
        headers=gcp_headers(),
    )


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/instances")
async def gcp_list_instances(project: str, zone: str, request: Request,
                              db: Session = Depends(get_db)):
    env = _get_env(request, db)
    instances = (env.oci_resources or {}).get("gcp_instances", [])
    zone_instances = [i for i in instances if zone in i.get("zone", "")]
    return {"kind": "compute#instanceList", "id": f"projects/{project}/zones/{zone}/instances",
            "items": zone_instances, "selfLink": gcp_self_link("instances", "", project, zone)}


@router.get("/gcp/compute/v1/projects/{project}/aggregated/instances")
async def gcp_aggregated_instances(project: str, request: Request,
                                    db: Session = Depends(get_db)):
    env = _get_env(request, db)
    instances = (env.oci_resources or {}).get("gcp_instances", [])
    items: Dict[str, Any] = {}
    for inst in instances:
        zone_name = inst.get("zone", "").split("/")[-1] or DEFAULT_GCP_ZONE
        key = f"zones/{zone_name}"
        if key not in items:
            items[key] = {"instances": []}
        items[key]["instances"].append(inst)
    return {"kind": "compute#instanceAggregatedList", "id": f"projects/{project}/aggregated/instances",
            "items": items}


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance}")
async def gcp_get_instance(project: str, zone: str, instance: str,
                            request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    instances = (env.oci_resources or {}).get("gcp_instances", [])
    inst = find_by_id(instances, "name", instance)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance {instance} not found")
    return inst


@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/start")
async def gcp_start_instance(project: str, zone: str, instance: str,
                              request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    instances = res.get("gcp_instances", [])
    inst = find_by_id(instances, "name", instance)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance {instance} not found")
    inst["status"] = "RUNNING"
    inst["lastStartTimestamp"] = utcnow_gcp()
    flag_resources_modified(db, env)
    return _gcp_operation("start", inst["selfLink"])


@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/stop")
async def gcp_stop_instance(project: str, zone: str, instance: str,
                             request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    instances = res.get("gcp_instances", [])
    inst = find_by_id(instances, "name", instance)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance {instance} not found")
    inst["status"] = "TERMINATED"
    inst["lastStopTimestamp"] = utcnow_gcp()
    flag_resources_modified(db, env)
    return _gcp_operation("stop", inst["selfLink"])


@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/reset")
async def gcp_reset_instance(project: str, zone: str, instance: str,
                              request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    instances = res.get("gcp_instances", [])
    inst = find_by_id(instances, "name", instance)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance {instance} not found")
    inst["status"] = "RUNNING"
    inst["lastStartTimestamp"] = utcnow_gcp()
    flag_resources_modified(db, env)
    return _gcp_operation("reset", inst["selfLink"])


@router.delete("/gcp/compute/v1/projects/{project}/zones/{zone}/instances/{instance}")
async def gcp_delete_instance(project: str, zone: str, instance: str,
                               request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    instances = _ns(res, "gcp_instances")
    inst = find_by_id(instances, "name", instance)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance {instance} not found")
    self_link = inst["selfLink"]
    remove_by_id(instances, "name", instance)
    flag_resources_modified(db, env)
    return _gcp_operation("delete", self_link)


# --- Networks ---

@router.post("/gcp/compute/v1/projects/{project}/global/networks")
async def gcp_create_network(project: str, request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    networks = _ns(res, "gcp_networks")

    name = body.get("name") or f"network-{new_uuid()[:8]}"
    network = {
        "kind": "compute#network",
        "id": gcp_network_id(),
        "name": name,
        "autoCreateSubnetworks": body.get("autoCreateSubnetworks", True),
        "selfLink": gcp_self_link("networks", name, project),
        "subnetworks": [],
        "routingConfig": {"routingMode": "REGIONAL"},
        "creationTimestamp": utcnow_gcp(),
    }
    networks.append(network)
    flag_resources_modified(db, env)
    return _gcp_operation("insert", network["selfLink"])


@router.get("/gcp/compute/v1/projects/{project}/global/networks")
async def gcp_list_networks(project: str, request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    networks = (env.oci_resources or {}).get("gcp_networks", [])
    return {"kind": "compute#networkList", "items": networks}


@router.get("/gcp/compute/v1/projects/{project}/global/networks/{network}")
async def gcp_get_network(project: str, network: str, request: Request,
                           db: Session = Depends(get_db)):
    env = _get_env(request, db)
    networks = (env.oci_resources or {}).get("gcp_networks", [])
    net = find_by_id(networks, "name", network)
    if not net:
        raise HTTPException(status_code=404, detail=f"Network {network} not found")
    return net


@router.delete("/gcp/compute/v1/projects/{project}/global/networks/{network}")
async def gcp_delete_network(project: str, network: str, request: Request,
                              db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    networks = _ns(res, "gcp_networks")
    net = find_by_id(networks, "name", network)
    if not net:
        raise HTTPException(status_code=404, detail=f"Network {network} not found")
    self_link = net["selfLink"]
    remove_by_id(networks, "name", network)
    flag_resources_modified(db, env)
    return _gcp_operation("delete", self_link)


# --- Subnetworks ---

@router.post("/gcp/compute/v1/projects/{project}/regions/{region}/subnetworks")
async def gcp_create_subnetwork(project: str, region: str, request: Request,
                                 db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    subnets = _ns(res, "gcp_subnetworks")

    name = body.get("name") or f"subnet-{new_uuid()[:8]}"
    subnet = {
        "kind": "compute#subnetwork",
        "id": gcp_network_id(),
        "name": name,
        "network": body.get("network", gcp_self_link("networks", "default", project)),
        "region": f"https://www.googleapis.com/compute/v1/projects/{project}/regions/{region}",
        "ipCidrRange": body.get("ipCidrRange", "10.0.0.0/24"),
        "privateIpGoogleAccess": body.get("privateIpGoogleAccess", False),
        "selfLink": f"https://www.googleapis.com/compute/v1/projects/{project}/regions/{region}/subnetworks/{name}",
        "creationTimestamp": utcnow_gcp(),
    }
    subnets.append(subnet)
    flag_resources_modified(db, env)
    return _gcp_operation("insert", subnet["selfLink"])


@router.get("/gcp/compute/v1/projects/{project}/regions/{region}/subnetworks")
async def gcp_list_subnetworks(project: str, region: str, request: Request,
                                db: Session = Depends(get_db)):
    env = _get_env(request, db)
    subnets = (env.oci_resources or {}).get("gcp_subnetworks", [])
    region_subnets = [s for s in subnets if region in s.get("region", "")]
    return {"kind": "compute#subnetworkList", "items": region_subnets}


# --- Firewalls ---

@router.post("/gcp/compute/v1/projects/{project}/global/firewalls")
async def gcp_create_firewall(project: str, request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    firewalls = _ns(res, "gcp_firewalls")

    name = body.get("name") or f"firewall-{new_uuid()[:8]}"
    firewall = {
        "kind": "compute#firewall",
        "id": gcp_network_id(),
        "name": name,
        "network": body.get("network", gcp_self_link("networks", "default", project)),
        "priority": body.get("priority", 1000),
        "direction": body.get("direction", "INGRESS"),
        "allowed": body.get("allowed", [{"IPProtocol": "tcp", "ports": ["80", "443"]}]),
        "denied": body.get("denied", []),
        "sourceRanges": body.get("sourceRanges", ["0.0.0.0/0"]),
        "targetTags": body.get("targetTags", []),
        "disabled": False,
        "selfLink": gcp_self_link("firewalls", name, project),
        "creationTimestamp": utcnow_gcp(),
    }
    firewalls.append(firewall)
    flag_resources_modified(db, env)
    return _gcp_operation("insert", firewall["selfLink"])


@router.get("/gcp/compute/v1/projects/{project}/global/firewalls")
async def gcp_list_firewalls(project: str, request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    firewalls = (env.oci_resources or {}).get("gcp_firewalls", [])
    return {"kind": "compute#firewallList", "items": firewalls}


@router.get("/gcp/compute/v1/projects/{project}/global/firewalls/{firewall}")
async def gcp_get_firewall(project: str, firewall: str, request: Request,
                            db: Session = Depends(get_db)):
    env = _get_env(request, db)
    firewalls = (env.oci_resources or {}).get("gcp_firewalls", [])
    fw = find_by_id(firewalls, "name", firewall)
    if not fw:
        raise HTTPException(status_code=404, detail=f"Firewall {firewall} not found")
    return fw


@router.patch("/gcp/compute/v1/projects/{project}/global/firewalls/{firewall}")
async def gcp_patch_firewall(project: str, firewall: str, request: Request,
                              db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    firewalls = _ns(res, "gcp_firewalls")
    fw = find_by_id(firewalls, "name", firewall)
    if not fw:
        raise HTTPException(status_code=404, detail=f"Firewall {firewall} not found")
    fw.update({k: v for k, v in body.items() if k not in ("kind", "id", "selfLink")})
    flag_resources_modified(db, env)
    return _gcp_operation("patch", fw["selfLink"])


@router.delete("/gcp/compute/v1/projects/{project}/global/firewalls/{firewall}")
async def gcp_delete_firewall(project: str, firewall: str, request: Request,
                               db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    firewalls = _ns(res, "gcp_firewalls")
    fw = find_by_id(firewalls, "name", firewall)
    if not fw:
        raise HTTPException(status_code=404, detail=f"Firewall {firewall} not found")
    self_link = fw["selfLink"]
    remove_by_id(firewalls, "name", firewall)
    flag_resources_modified(db, env)
    return _gcp_operation("delete", self_link)


# --- Disks ---

@router.post("/gcp/compute/v1/projects/{project}/zones/{zone}/disks")
async def gcp_create_disk(project: str, zone: str, request: Request,
                           db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    disks = _ns(res, "gcp_disks")

    name = body.get("name") or f"disk-{new_uuid()[:8]}"
    disk = {
        "kind": "compute#disk",
        "id": gcp_disk_id(),
        "name": name,
        "zone": gcp_zone_self_link(zone, project),
        "sizeGb": str(body.get("sizeGb", 10)),
        "type": body.get("type", f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/diskTypes/pd-standard"),
        "status": "READY",
        "selfLink": gcp_self_link("disks", name, project, zone),
        "sourceImage": body.get("sourceImage", ""),
        "creationTimestamp": utcnow_gcp(),
        "lastAttachTimestamp": "",
        "lastDetachTimestamp": "",
        "users": [],
    }
    disks.append(disk)
    flag_resources_modified(db, env)
    return _gcp_operation("insert", disk["selfLink"])


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/disks")
async def gcp_list_disks(project: str, zone: str, request: Request,
                          db: Session = Depends(get_db)):
    env = _get_env(request, db)
    disks = (env.oci_resources or {}).get("gcp_disks", [])
    zone_disks = [d for d in disks if zone in d.get("zone", "")]
    return {"kind": "compute#diskList", "items": zone_disks}


@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/disks/{disk}")
async def gcp_get_disk(project: str, zone: str, disk: str,
                        request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    disks = (env.oci_resources or {}).get("gcp_disks", [])
    d = find_by_id(disks, "name", disk)
    if not d:
        raise HTTPException(status_code=404, detail=f"Disk {disk} not found")
    return d


@router.delete("/gcp/compute/v1/projects/{project}/zones/{zone}/disks/{disk}")
async def gcp_delete_disk(project: str, zone: str, disk: str,
                           request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    disks = _ns(res, "gcp_disks")
    d = find_by_id(disks, "name", disk)
    if not d:
        raise HTTPException(status_code=404, detail=f"Disk {disk} not found")
    self_link = d["selfLink"]
    remove_by_id(disks, "name", disk)
    flag_resources_modified(db, env)
    return _gcp_operation("delete", self_link)


# --- Operations (async long-running) ---

@router.get("/gcp/compute/v1/projects/{project}/zones/{zone}/operations/{operation}")
async def gcp_get_zone_operation(project: str, zone: str, operation: str,
                                  request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    return {
        "kind": "compute#operation",
        "name": operation,
        "status": "DONE",
        "progress": 100,
        "zone": gcp_zone_self_link(zone, project),
    }


@router.get("/gcp/compute/v1/projects/{project}/global/operations/{operation}")
async def gcp_get_global_operation(project: str, operation: str,
                                    request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    return {"kind": "compute#operation", "name": operation, "status": "DONE", "progress": 100}


# ============================================================================
# Azure Virtual Machines
# ============================================================================

# --- Resource Groups ---

@router.get("/azure/subscriptions/{subscription}/resourceGroups")
async def azure_list_resource_groups(subscription: str, request: Request,
                                      db: Session = Depends(get_db)):
    env = _get_env(request, db)
    groups = (env.oci_resources or {}).get("azure_resource_groups", [
        {
            "id": f"/subscriptions/{subscription}/resourceGroups/{DEFAULT_AZURE_RESOURCE_GROUP}",
            "name": DEFAULT_AZURE_RESOURCE_GROUP,
            "type": "Microsoft.Resources/resourceGroups",
            "location": DEFAULT_AZURE_LOCATION,
            "properties": {"provisioningState": "Succeeded"},
        }
    ])
    return {"value": groups}


@router.put("/azure/subscriptions/{subscription}/resourceGroups/{resource_group}")
async def azure_create_or_update_resource_group(subscription: str, resource_group: str,
                                                  request: Request,
                                                  db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    groups = _ns(res, "azure_resource_groups")

    existing = find_by_id(groups, "name", resource_group)
    if existing:
        existing.update({"location": body.get("location", DEFAULT_AZURE_LOCATION)})
        flag_resources_modified(db, env)
        return existing

    group = {
        "id": f"/subscriptions/{subscription}/resourceGroups/{resource_group}",
        "name": resource_group,
        "type": "Microsoft.Resources/resourceGroups",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "tags": body.get("tags", {}),
        "properties": {"provisioningState": "Succeeded"},
    }
    groups.append(group)
    flag_resources_modified(db, env)
    return Response(content=str(group), media_type="application/json", status_code=201,
                    headers=azure_headers())


# --- Virtual Networks ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}")
async def azure_create_vnet(subscription: str, rg: str, vnet_name: str,
                             request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    vnets = _ns(res, "azure_vnets")

    existing = find_by_id(vnets, "name", vnet_name)
    if existing:
        return existing

    address_space = body.get("properties", {}).get("addressSpace", {}).get("addressPrefixes", ["10.0.0.0/16"])
    vnet = {
        "id": azure_resource_id("Microsoft.Network/virtualNetworks", vnet_name, rg, subscription),
        "name": vnet_name,
        "type": "Microsoft.Network/virtualNetworks",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "tags": body.get("tags", {}),
        "properties": {
            "provisioningState": "Succeeded",
            "addressSpace": {"addressPrefixes": address_space},
            "subnets": [],
            "virtualNetworkPeerings": [],
            "enableDdosProtection": False,
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }
    vnets.append(vnet)
    flag_resources_modified(db, env)
    return Response(content=str(vnet), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks")
async def azure_list_vnets(subscription: str, rg: str, request: Request,
                            db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vnets = (env.oci_resources or {}).get("azure_vnets", [])
    return {"value": vnets}


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}")
async def azure_get_vnet(subscription: str, rg: str, vnet_name: str,
                          request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vnets = (env.oci_resources or {}).get("azure_vnets", [])
    vnet = find_by_id(vnets, "name", vnet_name)
    if not vnet:
        raise HTTPException(status_code=404, detail=f"VNet {vnet_name} not found")
    return vnet


@router.delete("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}")
async def azure_delete_vnet(subscription: str, rg: str, vnet_name: str,
                             request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    vnets = _ns(res, "azure_vnets")
    if not remove_by_id(vnets, "name", vnet_name):
        raise HTTPException(status_code=404, detail=f"VNet {vnet_name} not found")
    flag_resources_modified(db, env)
    return Response(status_code=200, headers=azure_headers())


# --- Subnets ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}/subnets/{subnet_name}")
async def azure_create_subnet(subscription: str, rg: str, vnet_name: str, subnet_name: str,
                               request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    vnets = _ns(res, "azure_vnets")

    vnet = find_by_id(vnets, "name", vnet_name)
    if not vnet:
        raise HTTPException(status_code=404, detail=f"VNet {vnet_name} not found")

    subnet = {
        "id": f"{vnet['id']}/subnets/{subnet_name}",
        "name": subnet_name,
        "type": "Microsoft.Network/virtualNetworks/subnets",
        "properties": {
            "provisioningState": "Succeeded",
            "addressPrefix": body.get("properties", {}).get("addressPrefix", "10.0.0.0/24"),
            "networkSecurityGroup": body.get("properties", {}).get("networkSecurityGroup"),
            "privateEndpointNetworkPolicies": "Enabled",
            "privateLinkServiceNetworkPolicies": "Enabled",
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }

    subnets = vnet["properties"].setdefault("subnets", [])
    existing = find_by_id(subnets, "name", subnet_name)
    if existing:
        existing.update(subnet)
    else:
        subnets.append(subnet)

    flag_resources_modified(db, env)
    return Response(content=str(subnet), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}/subnets")
async def azure_list_subnets(subscription: str, rg: str, vnet_name: str,
                              request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vnets = (env.oci_resources or {}).get("azure_vnets", [])
    vnet = find_by_id(vnets, "name", vnet_name)
    if not vnet:
        raise HTTPException(status_code=404, detail=f"VNet {vnet_name} not found")
    return {"value": vnet.get("properties", {}).get("subnets", [])}


# --- Network Security Groups ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkSecurityGroups/{nsg_name}")
async def azure_create_nsg(subscription: str, rg: str, nsg_name: str,
                            request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    nsgs = _ns(res, "azure_nsgs")

    existing = find_by_id(nsgs, "name", nsg_name)
    if existing:
        return existing

    nsg = {
        "id": azure_resource_id("Microsoft.Network/networkSecurityGroups", nsg_name, rg, subscription),
        "name": nsg_name,
        "type": "Microsoft.Network/networkSecurityGroups",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "tags": body.get("tags", {}),
        "properties": {
            "provisioningState": "Succeeded",
            "securityRules": body.get("properties", {}).get("securityRules", []),
            "defaultSecurityRules": [
                {
                    "name": "AllowVnetInBound",
                    "properties": {
                        "priority": 65000, "protocol": "*", "access": "Allow",
                        "direction": "Inbound",
                        "sourceAddressPrefix": "VirtualNetwork",
                        "sourcePortRange": "*",
                        "destinationAddressPrefix": "VirtualNetwork",
                        "destinationPortRange": "*",
                        "provisioningState": "Succeeded",
                    },
                },
                {
                    "name": "DenyAllInBound",
                    "properties": {
                        "priority": 65500, "protocol": "*", "access": "Deny",
                        "direction": "Inbound",
                        "sourceAddressPrefix": "*", "sourcePortRange": "*",
                        "destinationAddressPrefix": "*", "destinationPortRange": "*",
                        "provisioningState": "Succeeded",
                    },
                },
            ],
            "networkInterfaces": [],
            "subnets": [],
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }
    nsgs.append(nsg)
    flag_resources_modified(db, env)
    return Response(content=str(nsg), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkSecurityGroups")
async def azure_list_nsgs(subscription: str, rg: str, request: Request,
                           db: Session = Depends(get_db)):
    env = _get_env(request, db)
    nsgs = (env.oci_resources or {}).get("azure_nsgs", [])
    return {"value": nsgs}


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkSecurityGroups/{nsg_name}")
async def azure_get_nsg(subscription: str, rg: str, nsg_name: str,
                         request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    nsgs = (env.oci_resources or {}).get("azure_nsgs", [])
    nsg = find_by_id(nsgs, "name", nsg_name)
    if not nsg:
        raise HTTPException(status_code=404, detail=f"NSG {nsg_name} not found")
    return nsg


@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkSecurityGroups/{nsg_name}/securityRules/{rule_name}")
async def azure_create_security_rule(subscription: str, rg: str, nsg_name: str, rule_name: str,
                                      request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    nsgs = _ns(res, "azure_nsgs")
    nsg = find_by_id(nsgs, "name", nsg_name)
    if not nsg:
        raise HTTPException(status_code=404, detail=f"NSG {nsg_name} not found")

    rule_props = body.get("properties", {})
    rule = {
        "id": f"{nsg['id']}/securityRules/{rule_name}",
        "name": rule_name,
        "type": "Microsoft.Network/networkSecurityGroups/securityRules",
        "properties": {
            "provisioningState": "Succeeded",
            "priority": rule_props.get("priority", 100),
            "protocol": rule_props.get("protocol", "Tcp"),
            "access": rule_props.get("access", "Allow"),
            "direction": rule_props.get("direction", "Inbound"),
            "sourceAddressPrefix": rule_props.get("sourceAddressPrefix", "*"),
            "sourcePortRange": rule_props.get("sourcePortRange", "*"),
            "destinationAddressPrefix": rule_props.get("destinationAddressPrefix", "*"),
            "destinationPortRange": rule_props.get("destinationPortRange", "80"),
        },
    }

    rules = nsg["properties"].setdefault("securityRules", [])
    existing = find_by_id(rules, "name", rule_name)
    if existing:
        existing.update(rule)
    else:
        rules.append(rule)

    flag_resources_modified(db, env)
    return Response(content=str(rule), media_type="application/json", status_code=201,
                    headers=azure_headers())


# --- Network Interfaces ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkInterfaces/{nic_name}")
async def azure_create_nic(subscription: str, rg: str, nic_name: str,
                            request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    nics = _ns(res, "azure_nics")

    existing = find_by_id(nics, "name", nic_name)
    if existing:
        return existing

    ip_configs = body.get("properties", {}).get("ipConfigurations", [])
    if not ip_configs:
        ip_configs = [{
            "name": "ipconfig1",
            "properties": {
                "privateIPAllocationMethod": "Dynamic",
                "privateIPAddress": random_private_ip(len(nics)),
                "provisioningState": "Succeeded",
            },
        }]

    nic = {
        "id": azure_resource_id("Microsoft.Network/networkInterfaces", nic_name, rg, subscription),
        "name": nic_name,
        "type": "Microsoft.Network/networkInterfaces",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "tags": body.get("tags", {}),
        "properties": {
            "provisioningState": "Succeeded",
            "ipConfigurations": ip_configs,
            "networkSecurityGroup": body.get("properties", {}).get("networkSecurityGroup"),
            "primary": True,
            "virtualMachine": None,
            "macAddress": ":".join(f"{random.randint(0,255):02x}" for _ in range(6)),
            "enableAcceleratedNetworking": False,
            "enableIPForwarding": False,
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }
    nics.append(nic)
    flag_resources_modified(db, env)
    return Response(content=str(nic), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/networkInterfaces")
async def azure_list_nics(subscription: str, rg: str, request: Request,
                           db: Session = Depends(get_db)):
    env = _get_env(request, db)
    nics = (env.oci_resources or {}).get("azure_nics", [])
    return {"value": nics}


# --- Public IP Addresses ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/publicIPAddresses/{pip_name}")
async def azure_create_public_ip(subscription: str, rg: str, pip_name: str,
                                  request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    pips = _ns(res, "azure_public_ips")

    existing = find_by_id(pips, "name", pip_name)
    if existing:
        return existing

    pip = {
        "id": azure_resource_id("Microsoft.Network/publicIPAddresses", pip_name, rg, subscription),
        "name": pip_name,
        "type": "Microsoft.Network/publicIPAddresses",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "sku": body.get("sku", {"name": "Basic"}),
        "properties": {
            "provisioningState": "Succeeded",
            "publicIPAllocationMethod": body.get("properties", {}).get("publicIPAllocationMethod", "Dynamic"),
            "publicIPAddressVersion": "IPv4",
            "ipAddress": random_public_ip(),
            "idleTimeoutInMinutes": 4,
            "ipTags": [],
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }
    pips.append(pip)
    flag_resources_modified(db, env)
    return Response(content=str(pip), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Network/publicIPAddresses")
async def azure_list_public_ips(subscription: str, rg: str, request: Request,
                                 db: Session = Depends(get_db)):
    env = _get_env(request, db)
    pips = (env.oci_resources or {}).get("azure_public_ips", [])
    return {"value": pips}


# --- Managed Disks ---

@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/disks/{disk_name}")
async def azure_create_disk(subscription: str, rg: str, disk_name: str,
                             request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    disks = _ns(res, "azure_disks")

    existing = find_by_id(disks, "name", disk_name)
    if existing:
        return existing

    disk_props = body.get("properties", {})
    disk = {
        "id": azure_resource_id("Microsoft.Compute/disks", disk_name, rg, subscription),
        "name": disk_name,
        "type": "Microsoft.Compute/disks",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "sku": body.get("sku", {"name": "Premium_LRS", "tier": "Premium"}),
        "tags": body.get("tags", {}),
        "properties": {
            "provisioningState": "Succeeded",
            "diskState": "Unattached",
            "diskSizeGB": disk_props.get("diskSizeGB", 128),
            "diskIOPSReadWrite": disk_props.get("diskIOPSReadWrite", 500),
            "diskMBpsReadWrite": disk_props.get("diskMBpsReadWrite", 100),
            "osType": disk_props.get("osType", "Linux"),
            "creationData": disk_props.get("creationData", {"createOption": "Empty"}),
            "timeCreated": utcnow_azure(),
            "uniqueId": new_uuid(),
        },
        "etag": f'W/"{uuid.uuid4()}"',
    }
    disks.append(disk)
    flag_resources_modified(db, env)
    return Response(content=str(disk), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/disks")
async def azure_list_disks(subscription: str, rg: str, request: Request,
                            db: Session = Depends(get_db)):
    env = _get_env(request, db)
    disks = (env.oci_resources or {}).get("azure_disks", [])
    return {"value": disks}


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/disks/{disk_name}")
async def azure_get_disk(subscription: str, rg: str, disk_name: str,
                          request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    disks = (env.oci_resources or {}).get("azure_disks", [])
    disk = find_by_id(disks, "name", disk_name)
    if not disk:
        raise HTTPException(status_code=404, detail=f"Disk {disk_name} not found")
    return disk


@router.delete("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/disks/{disk_name}")
async def azure_delete_disk(subscription: str, rg: str, disk_name: str,
                             request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    disks = _ns(res, "azure_disks")
    if not remove_by_id(disks, "name", disk_name):
        raise HTTPException(status_code=404, detail=f"Disk {disk_name} not found")
    flag_resources_modified(db, env)
    return Response(status_code=200, headers=azure_headers())


# --- Virtual Machines ---

def _build_vm(subscription: str, rg: str, vm_name: str, body: dict, index: int) -> Dict:
    props = body.get("properties", {})
    hw = props.get("hardwareProfile", {})
    os_profile = props.get("osProfile", {})
    storage = props.get("storageProfile", {})
    network = props.get("networkProfile", {})

    return {
        "id": azure_resource_id("Microsoft.Compute/virtualMachines", vm_name, rg, subscription),
        "name": vm_name,
        "type": "Microsoft.Compute/virtualMachines",
        "location": body.get("location", DEFAULT_AZURE_LOCATION),
        "tags": body.get("tags", {}),
        "properties": {
            "provisioningState": "Succeeded",
            "vmId": new_uuid(),
            "hardwareProfile": {
                "vmSize": hw.get("vmSize", "Standard_D2s_v3"),
            },
            "osProfile": {
                "computerName": os_profile.get("computerName", vm_name[:15]),
                "adminUsername": os_profile.get("adminUsername", "azureuser"),
                "linuxConfiguration": os_profile.get("linuxConfiguration", {
                    "disablePasswordAuthentication": True,
                    "provisionVMAgent": True,
                }),
            },
            "storageProfile": {
                "imageReference": storage.get("imageReference", {
                    "publisher": "Canonical",
                    "offer": "UbuntuServer",
                    "sku": "20.04-LTS",
                    "version": "latest",
                }),
                "osDisk": {
                    "name": storage.get("osDisk", {}).get("name", f"{vm_name}-osdisk"),
                    "createOption": "FromImage",
                    "managedDisk": {"storageAccountType": "Premium_LRS"},
                    "diskSizeGB": 30,
                    "osType": "Linux",
                },
                "dataDisks": storage.get("dataDisks", []),
            },
            "networkProfile": {
                "networkInterfaces": network.get("networkInterfaces", [
                    {
                        "id": azure_resource_id(
                            "Microsoft.Network/networkInterfaces",
                            f"{vm_name}-nic", rg, subscription
                        ),
                        "properties": {"primary": True},
                    }
                ]),
            },
            "diagnosticsProfile": {"bootDiagnostics": {"enabled": False}},
            "instanceView": {
                "platformUpdateDomain": 0,
                "platformFaultDomain": 0,
                "vmAgent": {"vmAgentVersion": "2.7.41491.1", "statuses": []},
                "statuses": [
                    {
                        "code": "PowerState/running",
                        "level": "Info",
                        "displayStatus": "VM running",
                        "time": utcnow_azure(),
                    }
                ],
            },
            "timeCreated": utcnow_azure(),
        },
        "etag": f'W/"{uuid.uuid4()}"',
        # Internal state tracking
        "_power_state": "running",
    }


@router.put("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_create_or_update_vm(subscription: str, rg: str, vm_name: str,
                                     request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.json()
    res = _res(env)
    vms = _ns(res, "azure_vms")

    existing = find_by_id(vms, "name", vm_name)
    if existing:
        # Update — merge properties
        existing["tags"] = body.get("tags", existing.get("tags", {}))
        flag_resources_modified(db, env)
        return existing

    vm = _build_vm(subscription, rg, vm_name, body, len(vms))
    vms.append(vm)
    flag_resources_modified(db, env)
    return Response(content=str(vm), media_type="application/json", status_code=201,
                    headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines")
async def azure_list_vms(subscription: str, rg: str, request: Request,
                          db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vms = (env.oci_resources or {}).get("azure_vms", [])
    return {"value": [_public_vm(v) for v in vms]}


@router.get("/azure/subscriptions/{subscription}/providers/Microsoft.Compute/virtualMachines")
async def azure_list_all_vms(subscription: str, request: Request,
                              db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vms = (env.oci_resources or {}).get("azure_vms", [])
    return {"value": [_public_vm(v) for v in vms]}


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_get_vm(subscription: str, rg: str, vm_name: str,
                        request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vms = (env.oci_resources or {}).get("azure_vms", [])
    vm = find_by_id(vms, "name", vm_name)
    if not vm:
        raise HTTPException(status_code=404, detail=f"VM {vm_name} not found")
    return _public_vm(vm)


def _public_vm(vm: Dict) -> Dict:
    """Strip internal tracking fields before returning to caller."""
    return {k: v for k, v in vm.items() if not k.startswith("_")}


def _set_vm_power_state(env: Environment, res: Dict, vm_name: str,
                         power_state: str, db: Session) -> Dict:
    vms = res.get("azure_vms", [])
    vm = find_by_id(vms, "name", vm_name)
    if not vm:
        raise HTTPException(status_code=404, detail=f"VM {vm_name} not found")

    vm["_power_state"] = power_state
    display_map = {
        "running": "VM running",
        "stopped": "VM stopped",
        "deallocated": "VM deallocated",
    }
    statuses = vm.get("properties", {}).get("instanceView", {}).get("statuses", [])
    for s in statuses:
        if s.get("code", "").startswith("PowerState/"):
            s["code"] = f"PowerState/{power_state}"
            s["displayStatus"] = display_map.get(power_state, power_state)
            s["time"] = utcnow_azure()

    flag_resources_modified(db, env)
    return vm


@router.post("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}/start")
async def azure_start_vm(subscription: str, rg: str, vm_name: str,
                          request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    _set_vm_power_state(env, res, vm_name, "running", db)
    return Response(status_code=200, headers=azure_headers())


@router.post("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}/powerOff")
async def azure_stop_vm(subscription: str, rg: str, vm_name: str,
                         request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    _set_vm_power_state(env, res, vm_name, "stopped", db)
    return Response(status_code=200, headers=azure_headers())


@router.post("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}/deallocate")
async def azure_deallocate_vm(subscription: str, rg: str, vm_name: str,
                               request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    _set_vm_power_state(env, res, vm_name, "deallocated", db)
    return Response(status_code=200, headers=azure_headers())


@router.post("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}/restart")
async def azure_restart_vm(subscription: str, rg: str, vm_name: str,
                            request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    _set_vm_power_state(env, res, vm_name, "running", db)
    return Response(status_code=200, headers=azure_headers())


@router.delete("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}")
async def azure_delete_vm(subscription: str, rg: str, vm_name: str,
                           request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    res = _res(env)
    vms = _ns(res, "azure_vms")
    if not remove_by_id(vms, "name", vm_name):
        raise HTTPException(status_code=404, detail=f"VM {vm_name} not found")
    flag_resources_modified(db, env)
    return Response(status_code=200, headers=azure_headers())


@router.get("/azure/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm_name}/instanceView")
async def azure_vm_instance_view(subscription: str, rg: str, vm_name: str,
                                  request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    vms = (env.oci_resources or {}).get("azure_vms", [])
    vm = find_by_id(vms, "name", vm_name)
    if not vm:
        raise HTTPException(status_code=404, detail=f"VM {vm_name} not found")
    return vm.get("properties", {}).get("instanceView", {})


# --- Azure Async Operations (long-running) ---

@router.get("/azure/subscriptions/{subscription}/providers/Microsoft.Compute/locations/{location}/operations/{operation_id}")
async def azure_get_operation(subscription: str, location: str, operation_id: str,
                               request: Request, db: Session = Depends(get_db)):
    _get_env(request, db)
    return {
        "id": f"/subscriptions/{subscription}/providers/Microsoft.Compute/locations/{location}/operations/{operation_id}",
        "name": operation_id,
        "status": "Succeeded",
        "startTime": utcnow_azure(),
        "endTime": utcnow_azure(),
        "percentComplete": 100.0,
        "properties": {},
    }
