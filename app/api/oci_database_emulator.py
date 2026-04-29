"""
OCI Database Emulator
Emulates Autonomous Database (ATP/ADW) and MySQL Database Service.
State stored in environment resources JSON (in-memory, no real DB spun up).

API version: 20160918 (same prefix as Compute/Networking)

Covered:
  Autonomous Databases — create, get, list, delete, start, stop, restart
  MySQL DB Systems     — create, get, list, delete, start, stop, restart
  DB Connections       — get connection strings for both
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    DEFAULT_OCI_COMPARTMENT, DEFAULT_OCI_REGION,
    find_by_id, flag_resources_modified, get_resources,
    new_uuid, oci_headers, ocid, paginate, remove_by_id, utcnow_iso,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_DB_PREFIX = "/20160918"
_MYSQL_PREFIX = "/20190415"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(request: Request, db: Session) -> Environment:
    host = request.headers.get("host", "")
    env_id = next((p for p in host.split(".") if p.startswith("env-")), None)
    if not env_id:
        raise HTTPException(400, "Environment ID not found in host")
    env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING,
    ).first()
    if not env:
        raise HTTPException(404, "Environment not found or not running")
    return env


def _ok(body, status: int = 200) -> Response:
    return Response(
        content=json.dumps(body),
        status_code=status,
        headers=oci_headers(),
        media_type="application/json",
    )


def _adb_connection_strings(db_name: str, region: str = DEFAULT_OCI_REGION) -> dict:
    hostname = f"{db_name.lower()}.adb.{region}.oraclecloud.com"
    return {
        "high":   f"{db_name.upper()}_high",
        "medium": f"{db_name.upper()}_medium",
        "low":    f"{db_name.upper()}_low",
        "tp":     f"{db_name.upper()}_tp",
        "tpurgent": f"{db_name.upper()}_tpurgent",
        "allConnectionStrings": {
            "high":     f"(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host={hostname}))(connect_data=(service_name={db_name.lower()}_high.adb.oraclecloud.com)))",
            "medium":   f"(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host={hostname}))(connect_data=(service_name={db_name.lower()}_medium.adb.oraclecloud.com)))",
            "low":      f"(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host={hostname}))(connect_data=(service_name={db_name.lower()}_low.adb.oraclecloud.com)))",
        },
    }


# ---------------------------------------------------------------------------
# Autonomous Databases (ATP / ADW)
# ---------------------------------------------------------------------------

@router.post(_DB_PREFIX + "/autonomousDatabases")
async def create_autonomous_database(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_autonomous_dbs", [])

    db_name = body.get("dbName", f"adb{new_uuid()[:8].replace('-','')}")
    adb_id = ocid("autonomousdatabase")

    adb = {
        "id": adb_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "dbName": db_name,
        "displayName": body.get("displayName", db_name),
        "dbWorkload": body.get("dbWorkload", "OLTP"),       # OLTP (ATP) | DW (ADW)
        "dbVersion": body.get("dbVersion", "19c"),
        "cpuCoreCount": body.get("cpuCoreCount", 1),
        "dataStorageSizeInTBs": body.get("dataStorageSizeInTBs", 1),
        "isAutoScalingEnabled": body.get("isAutoScalingEnabled", False),
        "isMtlsConnectionRequired": body.get("isMtlsConnectionRequired", True),
        "isFreeTier": body.get("isFreeTier", False),
        "licenseModel": body.get("licenseModel", "LICENSE_INCLUDED"),
        "lifecycleState": "PROVISIONING",
        "timeCreated": utcnow_iso(),
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "connectionStrings": _adb_connection_strings(db_name),
        "serviceConsoleUrl": f"https://adb.{DEFAULT_OCI_REGION}.oraclecloud.com/ords/sql-developer?tenant={adb_id}",
        "adminPassword": None,  # never echoed back
    }
    # Immediately transition to AVAILABLE
    adb["lifecycleState"] = "AVAILABLE"
    resources["oci_autonomous_dbs"].append(adb)
    flag_resources_modified(db, env)
    logger.info("Created OCI Autonomous Database: %s (%s)", db_name, adb["dbWorkload"])
    return _ok(adb, 200)


@router.get(_DB_PREFIX + "/autonomousDatabases")
async def list_autonomous_databases(
    compartmentId: Optional[str] = None,
    dbWorkload: Optional[str] = None,
    lifecycleState: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    adbs = resources.get("oci_autonomous_dbs", [])
    if dbWorkload:
        adbs = [a for a in adbs if a.get("dbWorkload") == dbWorkload]
    if lifecycleState:
        adbs = [a for a in adbs if a.get("lifecycleState") == lifecycleState]
    items, next_page = paginate(adbs, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_DB_PREFIX + "/autonomousDatabases/{adb_id}")
async def get_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    return _ok(adb)


@router.put(_DB_PREFIX + "/autonomousDatabases/{adb_id}")
async def update_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    for k in ("displayName", "cpuCoreCount", "dataStorageSizeInTBs",
              "isAutoScalingEnabled", "freeformTags", "definedTags"):
        if k in body:
            adb[k] = body[k]
    flag_resources_modified(db, env)
    return _ok(adb)


@router.delete(_DB_PREFIX + "/autonomousDatabases/{adb_id}")
async def delete_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adbs = resources.get("oci_autonomous_dbs", [])
    adb = find_by_id(adbs, "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    adb["lifecycleState"] = "TERMINATING"
    remove_by_id(adbs, "id", adb_id)
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.post(_DB_PREFIX + "/autonomousDatabases/{adb_id}/actions/start")
async def start_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    adb["lifecycleState"] = "AVAILABLE"
    flag_resources_modified(db, env)
    return _ok(adb)


@router.post(_DB_PREFIX + "/autonomousDatabases/{adb_id}/actions/stop")
async def stop_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    adb["lifecycleState"] = "STOPPED"
    flag_resources_modified(db, env)
    return _ok(adb)


@router.post(_DB_PREFIX + "/autonomousDatabases/{adb_id}/actions/restart")
async def restart_autonomous_database(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    adb["lifecycleState"] = "AVAILABLE"
    flag_resources_modified(db, env)
    return _ok(adb)


@router.get(_DB_PREFIX + "/autonomousDatabases/{adb_id}/autonomousDatabaseConnectionStrings")
async def get_connection_strings(adb_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    adb = find_by_id(resources.get("oci_autonomous_dbs", []), "id", adb_id)
    if not adb:
        raise HTTPException(404, "Autonomous Database not found")
    return _ok(adb.get("connectionStrings", {}))


# ---------------------------------------------------------------------------
# MySQL Database Service
# ---------------------------------------------------------------------------

@router.post(_MYSQL_PREFIX + "/dbSystems")
async def create_mysql_db_system(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    resources = get_resources(env)
    resources.setdefault("oci_mysql_systems", [])

    sys_id = ocid("dbsystem")
    display_name = body.get("displayName", f"mysql-{sys_id[-8:]}")

    system = {
        "id": sys_id,
        "compartmentId": body.get("compartmentId", DEFAULT_OCI_COMPARTMENT),
        "displayName": display_name,
        "description": body.get("description", ""),
        "availabilityDomain": body.get("availabilityDomain", "US-ASHBURN-AD-1"),
        "subnetId": body.get("subnetId"),
        "shapeName": body.get("shapeName", "MySQL.VM.Standard.E3.1.8GB"),
        "mysqlVersion": body.get("mysqlVersion", "8.0.35"),
        "dataStorageSizeInGBs": body.get("dataStorageSizeInGBs", 50),
        "adminUsername": body.get("adminUsername", "admin"),
        "ipAddress": f"10.0.{len(resources['oci_mysql_systems'])}.10",
        "port": 3306,
        "portX": 33060,
        "freeformTags": body.get("freeformTags", {}),
        "definedTags": body.get("definedTags", {}),
        "lifecycleState": "ACTIVE",
        "timeCreated": utcnow_iso(),
        "timeUpdated": utcnow_iso(),
    }
    resources["oci_mysql_systems"].append(system)
    flag_resources_modified(db, env)
    logger.info("Created OCI MySQL DB System: %s", display_name)
    return _ok(system, 200)


@router.get(_MYSQL_PREFIX + "/dbSystems")
async def list_mysql_db_systems(
    compartmentId: Optional[str] = None,
    lifecycleState: Optional[str] = None,
    limit: int = 50,
    page: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    systems = resources.get("oci_mysql_systems", [])
    if lifecycleState:
        systems = [s for s in systems if s.get("lifecycleState") == lifecycleState]
    items, next_page = paginate(systems, page, limit)
    h = oci_headers()
    if next_page:
        h["opc-next-page"] = next_page
    return Response(content=json.dumps({"items": items}), headers=h, media_type="application/json")


@router.get(_MYSQL_PREFIX + "/dbSystems/{system_id}")
async def get_mysql_db_system(system_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    system = find_by_id(resources.get("oci_mysql_systems", []), "id", system_id)
    if not system:
        raise HTTPException(404, "MySQL DB System not found")
    return _ok(system)


@router.delete(_MYSQL_PREFIX + "/dbSystems/{system_id}")
async def delete_mysql_db_system(system_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    systems = resources.get("oci_mysql_systems", [])
    if not remove_by_id(systems, "id", system_id):
        raise HTTPException(404, "MySQL DB System not found")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=oci_headers())


@router.post(_MYSQL_PREFIX + "/dbSystems/{system_id}/actions/start")
async def start_mysql_db_system(system_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    system = find_by_id(resources.get("oci_mysql_systems", []), "id", system_id)
    if not system:
        raise HTTPException(404, "MySQL DB System not found")
    system["lifecycleState"] = "ACTIVE"
    flag_resources_modified(db, env)
    return _ok(system)


@router.post(_MYSQL_PREFIX + "/dbSystems/{system_id}/actions/stop")
async def stop_mysql_db_system(system_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    system = find_by_id(resources.get("oci_mysql_systems", []), "id", system_id)
    if not system:
        raise HTTPException(404, "MySQL DB System not found")
    system["lifecycleState"] = "INACTIVE"
    flag_resources_modified(db, env)
    return _ok(system)


@router.post(_MYSQL_PREFIX + "/dbSystems/{system_id}/actions/restart")
async def restart_mysql_db_system(system_id: str, request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    system = find_by_id(resources.get("oci_mysql_systems", []), "id", system_id)
    if not system:
        raise HTTPException(404, "MySQL DB System not found")
    system["lifecycleState"] = "ACTIVE"
    flag_resources_modified(db, env)
    return _ok(system)
