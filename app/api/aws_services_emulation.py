"""
AWS Services Emulation - Route53, IAM, Lambda, SQS, SNS
Mock AWS APIs for testing without real AWS accounts
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import json
import uuid
from datetime import datetime
import xml.etree.ElementTree as ET

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus


router = APIRouter()


def get_environment_from_subdomain(request: Request, db: Session) -> Environment:
    """Extract environment ID from subdomain"""
    host = request.headers.get("host", "")
    env_id = None
    for part in host.split("."):
        if part.startswith("env-"):
            env_id = part
            break

    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID not found")

    environment = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    return environment


# ============================================================================
# AWS Route53 (DNS) Emulation
# ============================================================================

@router.post("/route53/")
async def route53_api(
    request: Request,
    x_amz_target: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    AWS Route53 API
    Mock DNS management for testing
    """
    environment = get_environment_from_subdomain(request, db)
    body = await request.json()

    action = body.get("Action") or (x_amz_target.split(".")[-1] if x_amz_target else None)

    if action == "CreateHostedZone":
        return await route53_create_hosted_zone(environment, body)
    elif action == "ListHostedZones":
        return await route53_list_hosted_zones(environment)
    elif action == "ChangeResourceRecordSets":
        return await route53_change_records(environment, body)
    elif action == "ListResourceRecordSets":
        return await route53_list_records(environment, body)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported Route53 action: {action}")


async def route53_create_hosted_zone(environment: Environment, body: dict):
    """Create a hosted zone (DNS zone)"""
    zone_name = body.get("Name")
    if not zone_name:
        raise HTTPException(status_code=400, detail="Name required")

    zone_id = f"Z{uuid.uuid4().hex[:10].upper()}"

    # Store in environment
    if "route53_zones" not in environment.oci_resources:
        environment.oci_resources["route53_zones"] = []

    environment.oci_resources["route53_zones"].append({
        "id": zone_id,
        "name": zone_name,
        "records": [],
        "created_at": datetime.utcnow().isoformat()
    })

    return {
        "HostedZone": {
            "Id": f"/hostedzone/{zone_id}",
            "Name": zone_name,
            "CallerReference": str(uuid.uuid4()),
            "ResourceRecordSetCount": 0
        },
        "ChangeInfo": {
            "Id": f"/change/{uuid.uuid4().hex}",
            "Status": "INSYNC",
            "SubmittedAt": datetime.utcnow().isoformat()
        }
    }


async def route53_list_hosted_zones(environment: Environment):
    """List all hosted zones"""
    zones = environment.oci_resources.get("route53_zones", [])

    hosted_zones = []
    for zone in zones:
        hosted_zones.append({
            "Id": f"/hostedzone/{zone['id']}",
            "Name": zone["name"],
            "ResourceRecordSetCount": len(zone.get("records", []))
        })

    return {"HostedZones": hosted_zones}


async def route53_change_records(environment: Environment, body: dict):
    """Create/update/delete DNS records"""
    zone_id = body.get("HostedZoneId", "").split("/")[-1]
    changes = body.get("ChangeBatch", {}).get("Changes", [])

    # Find zone
    zones = environment.oci_resources.get("route53_zones", [])
    zone = next((z for z in zones if z["id"] == zone_id), None)

    if not zone:
        raise HTTPException(status_code=404, detail="Hosted zone not found")

    # Apply changes
    for change in changes:
        action = change.get("Action")  # CREATE, UPSERT, DELETE
        record_set = change.get("ResourceRecordSet", {})

        if action in ["CREATE", "UPSERT"]:
            # Add or update record
            zone["records"].append({
                "name": record_set.get("Name"),
                "type": record_set.get("Type"),
                "ttl": record_set.get("TTL", 300),
                "values": [r.get("Value") for r in record_set.get("ResourceRecords", [])]
            })
        elif action == "DELETE":
            # Remove record
            zone["records"] = [
                r for r in zone["records"]
                if r["name"] != record_set.get("Name") or r["type"] != record_set.get("Type")
            ]

    return {
        "ChangeInfo": {
            "Id": f"/change/{uuid.uuid4().hex}",
            "Status": "INSYNC",
            "SubmittedAt": datetime.utcnow().isoformat()
        }
    }


async def route53_list_records(environment: Environment, body: dict):
    """List DNS records in a zone"""
    zone_id = body.get("HostedZoneId", "").split("/")[-1]

    zones = environment.oci_resources.get("route53_zones", [])
    zone = next((z for z in zones if z["id"] == zone_id), None)

    if not zone:
        raise HTTPException(status_code=404, detail="Hosted zone not found")

    record_sets = []
    for record in zone.get("records", []):
        record_sets.append({
            "Name": record["name"],
            "Type": record["type"],
            "TTL": record["ttl"],
            "ResourceRecords": [{"Value": v} for v in record["values"]]
        })

    return {"ResourceRecordSets": record_sets}


# ============================================================================
# AWS IAM Emulation
# ============================================================================

@router.post("/iam/")
async def iam_api(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    AWS IAM API
    Mock identity and access management
    """
    environment = get_environment_from_subdomain(request, db)

    # Parse form data (IAM uses form-encoded)
    form_data = await request.form()
    action = form_data.get("Action")

    if action == "CreateUser":
        return await iam_create_user(environment, form_data)
    elif action == "ListUsers":
        return await iam_list_users(environment)
    elif action == "CreateAccessKey":
        return await iam_create_access_key(environment, form_data)
    elif action == "CreateRole":
        return await iam_create_role(environment, form_data)
    elif action == "ListRoles":
        return await iam_list_roles(environment)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported IAM action: {action}")


async def iam_create_user(environment: Environment, form_data):
    """Create IAM user"""
    username = form_data.get("UserName")
    if not username:
        raise HTTPException(status_code=400, detail="UserName required")

    user_id = f"AIDA{uuid.uuid4().hex[:16].upper()}"

    if "iam_users" not in environment.oci_resources:
        environment.oci_resources["iam_users"] = []

    environment.oci_resources["iam_users"].append({
        "id": user_id,
        "name": username,
        "arn": f"arn:aws:iam::{environment.id}:user/{username}",
        "created_at": datetime.utcnow().isoformat(),
        "access_keys": []
    })

    # Return XML response (IAM uses XML)
    root = ET.Element("CreateUserResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateUserResult")
    user = ET.SubElement(result, "User")
    ET.SubElement(user, "UserId").text = user_id
    ET.SubElement(user, "UserName").text = username
    ET.SubElement(user, "Arn").text = f"arn:aws:iam::{environment.id}:user/{username}"

    return Response(content=ET.tostring(root, encoding="unicode"), media_type="text/xml")


async def iam_list_users(environment: Environment):
    """List IAM users"""
    users = environment.oci_resources.get("iam_users", [])

    root = ET.Element("ListUsersResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListUsersResult")
    users_elem = ET.SubElement(result, "Users")

    for u in users:
        user = ET.SubElement(users_elem, "member")
        ET.SubElement(user, "UserId").text = u["id"]
        ET.SubElement(user, "UserName").text = u["name"]
        ET.SubElement(user, "Arn").text = u["arn"]

    return Response(content=ET.tostring(root, encoding="unicode"), media_type="text/xml")


async def iam_create_access_key(environment: Environment, form_data):
    """Create access key for user"""
    username = form_data.get("UserName")

    users = environment.oci_resources.get("iam_users", [])
    user = next((u for u in users if u["name"] == username), None)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    access_key_id = f"AKIA{uuid.uuid4().hex[:16].upper()}"
    secret_key = uuid.uuid4().hex + uuid.uuid4().hex

    user["access_keys"].append({
        "access_key_id": access_key_id,
        "secret_key": secret_key,
        "status": "Active",
        "created_at": datetime.utcnow().isoformat()
    })

    root = ET.Element("CreateAccessKeyResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateAccessKeyResult")
    key = ET.SubElement(result, "AccessKey")
    ET.SubElement(key, "AccessKeyId").text = access_key_id
    ET.SubElement(key, "SecretAccessKey").text = secret_key
    ET.SubElement(key, "Status").text = "Active"

    return Response(content=ET.tostring(root, encoding="unicode"), media_type="text/xml")


async def iam_create_role(environment: Environment, form_data):
    """Create IAM role"""
    role_name = form_data.get("RoleName")
    assume_role_policy = form_data.get("AssumeRolePolicyDocument", "{}")

    if not role_name:
        raise HTTPException(status_code=400, detail="RoleName required")

    role_id = f"AROA{uuid.uuid4().hex[:16].upper()}"

    if "iam_roles" not in environment.oci_resources:
        environment.oci_resources["iam_roles"] = []

    environment.oci_resources["iam_roles"].append({
        "id": role_id,
        "name": role_name,
        "arn": f"arn:aws:iam::{environment.id}:role/{role_name}",
        "policy": assume_role_policy,
        "created_at": datetime.utcnow().isoformat()
    })

    root = ET.Element("CreateRoleResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateRoleResult")
    role = ET.SubElement(result, "Role")
    ET.SubElement(role, "RoleId").text = role_id
    ET.SubElement(role, "RoleName").text = role_name
    ET.SubElement(role, "Arn").text = f"arn:aws:iam::{environment.id}:role/{role_name}"

    return Response(content=ET.tostring(root, encoding="unicode"), media_type="text/xml")


async def iam_list_roles(environment: Environment):
    """List IAM roles"""
    roles = environment.oci_resources.get("iam_roles", [])

    root = ET.Element("ListRolesResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListRolesResult")
    roles_elem = ET.SubElement(result, "Roles")

    for r in roles:
        role = ET.SubElement(roles_elem, "member")
        ET.SubElement(role, "RoleId").text = r["id"]
        ET.SubElement(role, "RoleName").text = r["name"]
        ET.SubElement(role, "Arn").text = r["arn"]

    return Response(content=ET.tostring(root, encoding="unicode"), media_type="text/xml")


# ============================================================================
# AWS Lambda Emulation
# ============================================================================

@router.post("/lambda/2015-03-31/functions")
async def lambda_create_function(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    AWS Lambda CreateFunction
    Store function code and config (backed by OCI Functions)
    """
    environment = get_environment_from_subdomain(request, db)
    body = await request.json()

    function_name = body.get("FunctionName")
    runtime = body.get("Runtime", "python3.9")
    handler = body.get("Handler", "index.handler")
    code = body.get("Code", {})

    if not function_name:
        raise HTTPException(status_code=400, detail="FunctionName required")

    function_arn = f"arn:aws:lambda:us-east-1:{environment.id}:function:{function_name}"

    if "lambda_functions" not in environment.oci_resources:
        environment.oci_resources["lambda_functions"] = []

    environment.oci_resources["lambda_functions"].append({
        "name": function_name,
        "arn": function_arn,
        "runtime": runtime,
        "handler": handler,
        "code": code,
        "created_at": datetime.utcnow().isoformat()
    })

    return {
        "FunctionName": function_name,
        "FunctionArn": function_arn,
        "Runtime": runtime,
        "Handler": handler,
        "State": "Active"
    }


@router.post("/lambda/2015-03-31/functions/{function_name}/invocations")
async def lambda_invoke(
    function_name: str,
    request: Request,
    x_amz_invocation_type: str = Header("RequestResponse"),
    db: Session = Depends(get_db)
):
    """
    AWS Lambda Invoke
    Execute lambda function
    """
    environment = get_environment_from_subdomain(request, db)
    payload = await request.json()

    # Find function
    functions = environment.oci_resources.get("lambda_functions", [])
    func = next((f for f in functions if f["name"] == function_name), None)

    if not func:
        raise HTTPException(status_code=404, detail="Function not found")

    # Mock execution (in production, would use OCI Functions)
    result = {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"MockFactory Lambda executed: {function_name}",
            "input": payload,
            "runtime": func["runtime"]
        })
    }

    # Update last activity
    environment.last_activity = datetime.utcnow()

    return result


@router.get("/lambda/2015-03-31/functions")
async def lambda_list_functions(
    request: Request,
    db: Session = Depends(get_db)
):
    """List Lambda functions"""
    environment = get_environment_from_subdomain(request, db)

    functions = environment.oci_resources.get("lambda_functions", [])

    function_list = []
    for func in functions:
        function_list.append({
            "FunctionName": func["name"],
            "FunctionArn": func["arn"],
            "Runtime": func["runtime"],
            "Handler": func["handler"]
        })

    return {"Functions": function_list}
