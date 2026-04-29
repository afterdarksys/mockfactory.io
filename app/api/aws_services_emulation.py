"""
AWS Services Emulation — Route53, IAM, STS, Lambda (real Docker execution), EC2
All backed by in-memory state stored in environment.oci_resources JSON column.
Lambda functions are actually executed in Docker containers per their runtime.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from typing import Optional

import docker
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    DEFAULT_AWS_ACCOUNT_ID, DEFAULT_AWS_REGION,
    aws_headers, aws_request_id, ec2_instance_id, ec2_ami_id,
    ec2_vpc_id, ec2_subnet_id, ec2_sg_id, ec2_igw_id, ec2_rtb_id,
    ec2_volume_id, iam_user_id, iam_role_id, iam_access_key_id,
    iam_secret_key, iam_policy_id, lambda_arn, iam_arn, ec2_arn,
    route53_zone_id, route53_change_id, sns_topic_arn, sqs_queue_url,
    find_by_id, flag_resources_modified, get_resources, remove_by_id,
    utcnow_iso, utcnow_rfc1123, random_private_ip, random_public_ip,
    random_mac, EC2_STATES, AWS_INSTANCE_TYPES,
)


router = APIRouter()

LAMBDA_RUNTIME_IMAGES = {
    "python3.9":  "python:3.9-alpine",
    "python3.10": "python:3.10-alpine",
    "python3.11": "python:3.11-alpine",
    "python3.12": "python:3.12-alpine",
    "nodejs18.x": "node:18-alpine",
    "nodejs20.x": "node:20-alpine",
    "nodejs22.x": "node:22-alpine",
    "go1.x":      "golang:1.21-alpine",
    "ruby3.2":    "ruby:3.2-alpine",
}


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
        raise HTTPException(404, "Environment not found")
    return env


def _xml_resp(root: ET.Element, status: int = 200) -> Response:
    return Response(
        content=ET.tostring(root, encoding="unicode"),
        status_code=status,
        headers=aws_headers(),
        media_type="text/xml",
    )


def _json_resp(body: dict, status: int = 200) -> Response:
    return Response(
        content=json.dumps(body),
        status_code=status,
        headers={**aws_headers(), "Content-Type": "application/json"},
        media_type="application/json",
    )


def _ec2_instance_record(env_id: str, body: dict, idx: int) -> dict:
    inst_id = ec2_instance_id()
    private_ip = random_private_ip(idx)
    public_ip = random_public_ip()
    instance_type = body.get("InstanceType", "t3.micro")
    image_id = body.get("ImageId", ec2_ami_id())
    return {
        "instanceId": inst_id,
        "imageId": image_id,
        "instanceType": instance_type,
        "state": EC2_STATES["running"],
        "privateDnsName": f"ip-{private_ip.replace('.', '-')}.ec2.internal",
        "publicDnsName": f"ec2-{public_ip.replace('.', '-')}.compute-1.amazonaws.com",
        "privateIpAddress": private_ip,
        "publicIpAddress": public_ip,
        "macAddress": random_mac(),
        "placement": {"availabilityZone": f"{DEFAULT_AWS_REGION}a", "tenancy": "default"},
        "architecture": "x86_64",
        "hypervisor": "xen",
        "virtualizationType": "hvm",
        "rootDeviceType": "ebs",
        "rootDeviceName": "/dev/xvda",
        "blockDeviceMappings": [
            {"deviceName": "/dev/xvda", "ebs": {
                "volumeId": ec2_volume_id(), "status": "attached",
                "deleteOnTermination": True,
            }}
        ],
        "securityGroups": body.get("SecurityGroupIds", []),
        "subnetId": body.get("SubnetId", ec2_subnet_id()),
        "vpcId": body.get("VpcId", ec2_vpc_id()),
        "tags": [{"Key": t["Key"], "Value": t["Value"]}
                 for t in body.get("TagSpecifications", [{}])[0].get("Tags", [])
                 if body.get("TagSpecifications")],
        "launchTime": utcnow_iso(),
        "monitoringState": "disabled",
        "iamInstanceProfile": body.get("IamInstanceProfile", {}),
        "networkInterfaces": [{
            "networkInterfaceId": f"eni-{uuid.uuid4().hex[:17]}",
            "privateIpAddress": private_ip,
            "association": {"publicIp": public_ip},
        }],
    }


# ============================================================================
# AWS STS (Security Token Service)
# ============================================================================

@router.post("/sts/")
@router.get("/sts/")
async def sts_api(request: Request, db: Session = Depends(get_db)):
    """AWS STS — GetCallerIdentity, AssumeRole, GetSessionToken."""
    env = _env(request, db)
    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    action = body.get("Action", "")

    if action == "GetCallerIdentity":
        root = ET.Element("GetCallerIdentityResponse",
                          xmlns="https://sts.amazonaws.com/doc/2011-06-15/")
        result = ET.SubElement(root, "GetCallerIdentityResult")
        ET.SubElement(result, "UserId").text = iam_user_id()
        ET.SubElement(result, "Account").text = DEFAULT_AWS_ACCOUNT_ID
        ET.SubElement(result, "Arn").text = iam_arn(f"user/mockfactory-{env.id}")
        meta = ET.SubElement(root, "ResponseMetadata")
        ET.SubElement(meta, "RequestId").text = aws_request_id()
        return _xml_resp(root)

    if action == "AssumeRole":
        role_arn = body.get("RoleArn", iam_arn("role/MockRole"))
        session_name = body.get("RoleSessionName", "MockSession")
        access_key = iam_access_key_id()
        secret = iam_secret_key()
        session_token = base64.b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode()

        root = ET.Element("AssumeRoleResponse",
                          xmlns="https://sts.amazonaws.com/doc/2011-06-15/")
        result = ET.SubElement(root, "AssumeRoleResult")
        creds = ET.SubElement(result, "Credentials")
        ET.SubElement(creds, "AccessKeyId").text = access_key
        ET.SubElement(creds, "SecretAccessKey").text = secret
        ET.SubElement(creds, "SessionToken").text = session_token
        ET.SubElement(creds, "Expiration").text = utcnow_iso()
        assumed = ET.SubElement(result, "AssumedRoleUser")
        ET.SubElement(assumed, "AssumedRoleId").text = f"{iam_role_id()}:{session_name}"
        ET.SubElement(assumed, "Arn").text = f"{role_arn}/{session_name}"
        return _xml_resp(root)

    if action == "GetSessionToken":
        root = ET.Element("GetSessionTokenResponse",
                          xmlns="https://sts.amazonaws.com/doc/2011-06-15/")
        result = ET.SubElement(root, "GetSessionTokenResult")
        creds = ET.SubElement(result, "Credentials")
        ET.SubElement(creds, "AccessKeyId").text = iam_access_key_id()
        ET.SubElement(creds, "SecretAccessKey").text = iam_secret_key()
        ET.SubElement(creds, "SessionToken").text = base64.b64encode(uuid.uuid4().bytes).decode()
        ET.SubElement(creds, "Expiration").text = utcnow_iso()
        return _xml_resp(root)

    raise HTTPException(400, f"Unsupported STS action: {action}")


# ============================================================================
# AWS EC2
# ============================================================================

@router.post("/ec2/")
async def ec2_api(request: Request, db: Session = Depends(get_db)):
    """AWS EC2 API — routes by Action form parameter."""
    env = _env(request, db)
    form = await request.form()
    body = dict(form)
    action = body.get("Action", "")
    resources = get_resources(env)

    # --- Instances ---
    if action == "RunInstances":
        return await _ec2_run_instances(env, body, resources, db)
    if action == "DescribeInstances":
        return _ec2_describe_instances(env, body, resources)
    if action == "StartInstances":
        return _ec2_change_instance_state(env, body, resources, db, "running")
    if action == "StopInstances":
        return _ec2_change_instance_state(env, body, resources, db, "stopped")
    if action == "TerminateInstances":
        return _ec2_terminate_instances(env, body, resources, db)
    if action == "DescribeInstanceTypes":
        return _ec2_describe_instance_types()

    # --- VPC / Networking ---
    if action == "CreateVpc":
        return _ec2_create_vpc(env, body, resources, db)
    if action == "DescribeVpcs":
        return _ec2_describe_vpcs(env, resources)
    if action == "DeleteVpc":
        return _ec2_delete_resource(env, body, resources, db, "ec2_vpcs", "vpcId", "DeleteVpc")
    if action == "CreateSubnet":
        return _ec2_create_subnet(env, body, resources, db)
    if action == "DescribeSubnets":
        return _ec2_describe_subnets(env, resources)
    if action == "CreateSecurityGroup":
        return _ec2_create_security_group(env, body, resources, db)
    if action == "DescribeSecurityGroups":
        return _ec2_describe_security_groups(env, resources)
    if action == "AuthorizeSecurityGroupIngress":
        return _ec2_authorize_sg(env, body, resources, db, "ingress")
    if action == "AuthorizeSecurityGroupEgress":
        return _ec2_authorize_sg(env, body, resources, db, "egress")
    if action == "CreateInternetGateway":
        return _ec2_create_igw(env, body, resources, db)
    if action == "AttachInternetGateway":
        return _ec2_attach_igw(env, body, resources, db)
    if action == "CreateRouteTable":
        return _ec2_create_route_table(env, body, resources, db)
    if action == "CreateRoute":
        return _ec2_create_route(env, body, resources, db)
    if action == "AssociateRouteTable":
        return _ec2_assoc_route_table(env, body, resources, db)

    # --- Key Pairs ---
    if action == "CreateKeyPair":
        return _ec2_create_key_pair(env, body, resources, db)
    if action == "DescribeKeyPairs":
        return _ec2_describe_key_pairs(env, resources)

    # --- AMIs ---
    if action == "DescribeImages":
        return _ec2_describe_images()

    # --- Availability Zones ---
    if action == "DescribeAvailabilityZones":
        return _ec2_describe_azs()
    if action == "DescribeRegions":
        return _ec2_describe_regions()

    raise HTTPException(400, f"Unsupported EC2 action: {action}")


async def _ec2_run_instances(env, body, resources, db):
    if "ec2_instances" not in resources:
        resources["ec2_instances"] = []
    count = int(body.get("MaxCount", body.get("MinCount", 1)))
    instances = []
    for i in range(count):
        inst = _ec2_instance_record(env.id, body, len(resources["ec2_instances"]) + i)
        resources["ec2_instances"].append(inst)
        instances.append(inst)
    flag_resources_modified(db, env)

    root = ET.Element("RunInstancesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "reservationId").text = f"r-{uuid.uuid4().hex[:8]}"
    ET.SubElement(root, "ownerId").text = DEFAULT_AWS_ACCOUNT_ID
    items = ET.SubElement(root, "instancesSet")
    for inst in instances:
        _ec2_inst_xml(items, inst)
    return _xml_resp(root)


def _ec2_inst_xml(parent: ET.Element, inst: dict) -> None:
    item = ET.SubElement(parent, "item")
    ET.SubElement(item, "instanceId").text = inst["instanceId"]
    ET.SubElement(item, "imageId").text = inst["imageId"]
    state = ET.SubElement(item, "instanceState")
    ET.SubElement(state, "code").text = str(inst["state"]["code"])
    ET.SubElement(state, "name").text = inst["state"]["name"]
    ET.SubElement(item, "privateDnsName").text = inst["privateDnsName"]
    ET.SubElement(item, "publicDnsName").text = inst["publicDnsName"]
    ET.SubElement(item, "instanceType").text = inst["instanceType"]
    ET.SubElement(item, "launchTime").text = inst["launchTime"]
    placement = ET.SubElement(item, "placement")
    ET.SubElement(placement, "availabilityZone").text = inst["placement"]["availabilityZone"]
    ET.SubElement(placement, "tenancy").text = inst["placement"]["tenancy"]
    ET.SubElement(item, "privateIpAddress").text = inst["privateIpAddress"]
    ET.SubElement(item, "publicIpAddress").text = inst.get("publicIpAddress", "")
    ET.SubElement(item, "architecture").text = inst["architecture"]
    ET.SubElement(item, "hypervisor").text = inst["hypervisor"]
    ET.SubElement(item, "virtualizationType").text = inst["virtualizationType"]
    ET.SubElement(item, "subnetId").text = inst.get("subnetId", "")
    ET.SubElement(item, "vpcId").text = inst.get("vpcId", "")


def _ec2_describe_instances(env, body, resources):
    instances = resources.get("ec2_instances", [])
    root = ET.Element("DescribeInstancesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    res_set = ET.SubElement(root, "reservationSet")
    res_item = ET.SubElement(res_set, "item")
    ET.SubElement(res_item, "reservationId").text = f"r-{uuid.uuid4().hex[:8]}"
    ET.SubElement(res_item, "ownerId").text = DEFAULT_AWS_ACCOUNT_ID
    items = ET.SubElement(res_item, "instancesSet")
    for inst in instances:
        _ec2_inst_xml(items, inst)
    return _xml_resp(root)


def _ec2_change_instance_state(env, body, resources, db, new_state):
    inst_ids = [v for k, v in body.items() if k.startswith("InstanceId.")]
    instances = resources.get("ec2_instances", [])
    root = ET.Element("StartInstancesResponse" if new_state == "running" else "StopInstancesResponse",
                      xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    items = ET.SubElement(root, "instancesSet")
    for iid in inst_ids:
        inst = find_by_id(instances, "instanceId", iid)
        if inst:
            old_state = inst["state"].copy()
            inst["state"] = EC2_STATES[new_state]
            item = ET.SubElement(items, "item")
            ET.SubElement(item, "instanceId").text = iid
            prev = ET.SubElement(item, "previousState")
            ET.SubElement(prev, "code").text = str(old_state["code"])
            ET.SubElement(prev, "name").text = old_state["name"]
            cur = ET.SubElement(item, "currentState")
            ET.SubElement(cur, "code").text = str(inst["state"]["code"])
            ET.SubElement(cur, "name").text = inst["state"]["name"]
    flag_resources_modified(db, env)
    return _xml_resp(root)


def _ec2_terminate_instances(env, body, resources, db):
    inst_ids = [v for k, v in body.items() if k.startswith("InstanceId.")]
    instances = resources.get("ec2_instances", [])
    root = ET.Element("TerminateInstancesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    items = ET.SubElement(root, "instancesSet")
    for iid in inst_ids:
        inst = find_by_id(instances, "instanceId", iid)
        if inst:
            item = ET.SubElement(items, "item")
            ET.SubElement(item, "instanceId").text = iid
            cur = ET.SubElement(item, "currentState")
            ET.SubElement(cur, "code").text = "48"
            ET.SubElement(cur, "name").text = "terminated"
            remove_by_id(instances, "instanceId", iid)
    flag_resources_modified(db, env)
    return _xml_resp(root)


def _ec2_describe_instance_types():
    root = ET.Element("DescribeInstanceTypesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    items = ET.SubElement(root, "instanceTypeSet")
    for t in AWS_INSTANCE_TYPES:
        item = ET.SubElement(items, "item")
        ET.SubElement(item, "instanceType").text = t
    return _xml_resp(root)


def _ec2_create_vpc(env, body, resources, db):
    if "ec2_vpcs" not in resources:
        resources["ec2_vpcs"] = []
    vid = ec2_vpc_id()
    vpc = {
        "vpcId": vid, "cidrBlock": body.get("CidrBlock", "10.0.0.0/16"),
        "state": "available", "isDefault": False,
        "dhcpOptionsId": f"dopt-{uuid.uuid4().hex[:8]}",
        "instanceTenancy": body.get("InstanceTenancy", "default"),
        "ownerId": DEFAULT_AWS_ACCOUNT_ID,
    }
    resources["ec2_vpcs"].append(vpc)
    flag_resources_modified(db, env)
    root = ET.Element("CreateVpcResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    item = ET.SubElement(root, "vpc")
    for k, v in vpc.items():
        ET.SubElement(item, k).text = str(v)
    return _xml_resp(root)


def _ec2_describe_vpcs(env, resources):
    root = ET.Element("DescribeVpcsResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    vpc_set = ET.SubElement(root, "vpcSet")
    for vpc in resources.get("ec2_vpcs", []):
        item = ET.SubElement(vpc_set, "item")
        for k, v in vpc.items():
            ET.SubElement(item, k).text = str(v)
    return _xml_resp(root)


def _ec2_delete_resource(env, body, resources, db, collection, id_key, action_name):
    rid = body.get(id_key[0].upper() + id_key[1:], "")
    remove_by_id(resources.get(collection, []), id_key, rid)
    flag_resources_modified(db, env)
    root = ET.Element(f"{action_name}Response", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "return").text = "true"
    return _xml_resp(root)


def _ec2_create_subnet(env, body, resources, db):
    if "ec2_subnets" not in resources:
        resources["ec2_subnets"] = []
    idx = len(resources["ec2_subnets"])
    sid = ec2_subnet_id()
    subnet = {
        "subnetId": sid, "vpcId": body.get("VpcId", ""),
        "cidrBlock": body.get("CidrBlock", f"10.0.{idx}.0/24"),
        "availabilityZone": body.get("AvailabilityZone", f"{DEFAULT_AWS_REGION}a"),
        "availableIpAddressCount": 251, "state": "available",
        "defaultForAz": False, "mapPublicIpOnLaunch": False,
        "ownerId": DEFAULT_AWS_ACCOUNT_ID,
    }
    resources["ec2_subnets"].append(subnet)
    flag_resources_modified(db, env)
    root = ET.Element("CreateSubnetResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    item = ET.SubElement(root, "subnet")
    for k, v in subnet.items():
        ET.SubElement(item, k).text = str(v)
    return _xml_resp(root)


def _ec2_describe_subnets(env, resources):
    root = ET.Element("DescribeSubnetsResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    s_set = ET.SubElement(root, "subnetSet")
    for subnet in resources.get("ec2_subnets", []):
        item = ET.SubElement(s_set, "item")
        for k, v in subnet.items():
            ET.SubElement(item, k).text = str(v)
    return _xml_resp(root)


def _ec2_create_security_group(env, body, resources, db):
    if "ec2_security_groups" not in resources:
        resources["ec2_security_groups"] = []
    sgid = ec2_sg_id()
    sg = {
        "groupId": sgid, "groupName": body.get("GroupName", f"sg-{sgid}"),
        "description": body.get("Description", ""),
        "vpcId": body.get("VpcId", ""),
        "ownerId": DEFAULT_AWS_ACCOUNT_ID,
        "ipPermissions": [], "ipPermissionsEgress": [
            {"ipProtocol": "-1", "ipRanges": [{"cidrIp": "0.0.0.0/0"}]}
        ],
    }
    resources["ec2_security_groups"].append(sg)
    flag_resources_modified(db, env)
    root = ET.Element("CreateSecurityGroupResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "groupId").text = sgid
    return _xml_resp(root)


def _ec2_describe_security_groups(env, resources):
    root = ET.Element("DescribeSecurityGroupsResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    sg_set = ET.SubElement(root, "securityGroupInfo")
    for sg in resources.get("ec2_security_groups", []):
        item = ET.SubElement(sg_set, "item")
        ET.SubElement(item, "groupId").text = sg["groupId"]
        ET.SubElement(item, "groupName").text = sg["groupName"]
        ET.SubElement(item, "description").text = sg["description"]
        ET.SubElement(item, "vpcId").text = sg.get("vpcId", "")
        ET.SubElement(item, "ownerId").text = DEFAULT_AWS_ACCOUNT_ID
    return _xml_resp(root)


def _ec2_authorize_sg(env, body, resources, db, direction):
    sgid = body.get("GroupId", "")
    sgs = resources.get("ec2_security_groups", [])
    sg = find_by_id(sgs, "groupId", sgid)
    if sg:
        rule = {
            "ipProtocol": body.get("IpPermissions.1.IpProtocol", "tcp"),
            "fromPort": body.get("IpPermissions.1.FromPort", "0"),
            "toPort": body.get("IpPermissions.1.ToPort", "65535"),
            "ipRanges": [{"cidrIp": body.get("IpPermissions.1.IpRanges.1.CidrIp", "0.0.0.0/0")}],
        }
        key = "ipPermissions" if direction == "ingress" else "ipPermissionsEgress"
        sg.setdefault(key, []).append(rule)
        flag_resources_modified(db, env)
    root = ET.Element("AuthorizeSecurityGroupIngressResponse" if direction == "ingress"
                      else "AuthorizeSecurityGroupEgressResponse",
                      xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "return").text = "true"
    return _xml_resp(root)


def _ec2_create_igw(env, body, resources, db):
    if "ec2_igws" not in resources:
        resources["ec2_igws"] = []
    igwid = ec2_igw_id()
    igw = {"internetGatewayId": igwid, "attachments": [], "ownerId": DEFAULT_AWS_ACCOUNT_ID}
    resources["ec2_igws"].append(igw)
    flag_resources_modified(db, env)
    root = ET.Element("CreateInternetGatewayResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    item = ET.SubElement(root, "internetGateway")
    ET.SubElement(item, "internetGatewayId").text = igwid
    return _xml_resp(root)


def _ec2_attach_igw(env, body, resources, db):
    igwid = body.get("InternetGatewayId", "")
    vpcid = body.get("VpcId", "")
    igws = resources.get("ec2_igws", [])
    igw = find_by_id(igws, "internetGatewayId", igwid)
    if igw:
        igw["attachments"].append({"vpcId": vpcid, "state": "available"})
        flag_resources_modified(db, env)
    root = ET.Element("AttachInternetGatewayResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "return").text = "true"
    return _xml_resp(root)


def _ec2_create_route_table(env, body, resources, db):
    if "ec2_route_tables" not in resources:
        resources["ec2_route_tables"] = []
    rtid = ec2_rtb_id()
    rt = {"routeTableId": rtid, "vpcId": body.get("VpcId", ""),
          "routes": [], "associations": [], "ownerId": DEFAULT_AWS_ACCOUNT_ID}
    resources["ec2_route_tables"].append(rt)
    flag_resources_modified(db, env)
    root = ET.Element("CreateRouteTableResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    item = ET.SubElement(root, "routeTable")
    ET.SubElement(item, "routeTableId").text = rtid
    return _xml_resp(root)


def _ec2_create_route(env, body, resources, db):
    rtid = body.get("RouteTableId", "")
    rts = resources.get("ec2_route_tables", [])
    rt = find_by_id(rts, "routeTableId", rtid)
    if rt:
        rt["routes"].append({
            "destinationCidrBlock": body.get("DestinationCidrBlock", "0.0.0.0/0"),
            "gatewayId": body.get("GatewayId", ""),
            "state": "active",
        })
        flag_resources_modified(db, env)
    root = ET.Element("CreateRouteResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "return").text = "true"
    return _xml_resp(root)


def _ec2_assoc_route_table(env, body, resources, db):
    root = ET.Element("AssociateRouteTableResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "associationId").text = f"rtbassoc-{uuid.uuid4().hex[:8]}"
    return _xml_resp(root)


def _ec2_create_key_pair(env, body, resources, db):
    if "ec2_key_pairs" not in resources:
        resources["ec2_key_pairs"] = []
    name = body.get("KeyName", f"key-{uuid.uuid4().hex[:8]}")
    fp = ":".join([f"{uuid.uuid4().hex[:2]}" for _ in range(20)])
    kp = {"keyName": name, "keyFingerprint": fp, "keyPairId": f"key-{uuid.uuid4().hex[:8]}"}
    resources["ec2_key_pairs"].append(kp)
    flag_resources_modified(db, env)
    fake_pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        + base64.b64encode(uuid.uuid4().bytes * 16).decode() + "\n"
        + "-----END RSA PRIVATE KEY-----"
    )
    root = ET.Element("CreateKeyPairResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    ET.SubElement(root, "keyName").text = name
    ET.SubElement(root, "keyFingerprint").text = fp
    ET.SubElement(root, "keyMaterial").text = fake_pem
    return _xml_resp(root)


def _ec2_describe_key_pairs(env, resources):
    root = ET.Element("DescribeKeyPairsResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    kp_set = ET.SubElement(root, "keySet")
    for kp in resources.get("ec2_key_pairs", []):
        item = ET.SubElement(kp_set, "item")
        ET.SubElement(item, "keyName").text = kp["keyName"]
        ET.SubElement(item, "keyFingerprint").text = kp["keyFingerprint"]
        ET.SubElement(item, "keyPairId").text = kp["keyPairId"]
    return _xml_resp(root)


def _ec2_describe_images():
    root = ET.Element("DescribeImagesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    img_set = ET.SubElement(root, "imagesSet")
    for name, desc in [
        ("ami-0abcdef1234567890", "Amazon Linux 2023 AMI"),
        ("ami-0ubuntu22041234567", "Ubuntu 22.04 LTS"),
        ("ami-0debian11x86641234", "Debian 11 Bullseye"),
    ]:
        item = ET.SubElement(img_set, "item")
        ET.SubElement(item, "imageId").text = name
        ET.SubElement(item, "name").text = desc
        ET.SubElement(item, "imageState").text = "available"
        ET.SubElement(item, "architecture").text = "x86_64"
        ET.SubElement(item, "imageType").text = "machine"
        ET.SubElement(item, "rootDeviceType").text = "ebs"
        ET.SubElement(item, "virtualizationType").text = "hvm"
    return _xml_resp(root)


def _ec2_describe_azs():
    root = ET.Element("DescribeAvailabilityZonesResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    az_set = ET.SubElement(root, "availabilityZoneInfo")
    for suffix in ["a", "b", "c"]:
        item = ET.SubElement(az_set, "item")
        ET.SubElement(item, "zoneName").text = f"{DEFAULT_AWS_REGION}{suffix}"
        ET.SubElement(item, "zoneId").text = f"use1-az{suffix}"
        ET.SubElement(item, "zoneState").text = "available"
        ET.SubElement(item, "regionName").text = DEFAULT_AWS_REGION
    return _xml_resp(root)


def _ec2_describe_regions():
    root = ET.Element("DescribeRegionsResponse", xmlns="http://ec2.amazonaws.com/doc/2016-11-15/")
    ET.SubElement(root, "requestId").text = aws_request_id()
    rset = ET.SubElement(root, "regionInfo")
    for r in ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]:
        item = ET.SubElement(rset, "item")
        ET.SubElement(item, "regionName").text = r
        ET.SubElement(item, "regionEndpoint").text = f"ec2.{r}.amazonaws.com"
    return _xml_resp(root)


# ============================================================================
# AWS Route53
# ============================================================================

@router.post("/route53/")
async def route53_api(
    request: Request,
    x_amz_target: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    env = _env(request, db)
    try:
        body = await request.json()
    except Exception:
        body = {}
    resources = get_resources(env)
    action = body.get("Action") or (x_amz_target.split(".")[-1] if x_amz_target else "")

    if action == "CreateHostedZone":
        return _r53_create_zone(env, body, resources, db)
    if action == "ListHostedZones":
        return _r53_list_zones(resources)
    if action == "GetHostedZone":
        return _r53_get_zone(body, resources)
    if action == "ChangeResourceRecordSets":
        return _r53_change_records(env, body, resources, db)
    if action == "ListResourceRecordSets":
        return _r53_list_records(body, resources)
    if action == "GetChange":
        return _r53_get_change(body)
    raise HTTPException(400, f"Unsupported Route53 action: {action}")


def _r53_create_zone(env, body, resources, db):
    if "route53_zones" not in resources:
        resources["route53_zones"] = []
    zone_id = route53_zone_id()
    zone_name = body.get("Name", "example.com.")
    if not zone_name.endswith("."):
        zone_name += "."
    zone = {
        "id": zone_id, "name": zone_name,
        "callerReference": body.get("CallerReference", str(uuid.uuid4())),
        "privateZone": body.get("HostedZoneConfig", {}).get("PrivateZone", False),
        "records": [
            {"name": zone_name, "type": "SOA", "ttl": 900,
             "values": [f"ns1.mockfactory.io. admin.mockfactory.io. 1 7200 900 1209600 86400"]},
            {"name": zone_name, "type": "NS", "ttl": 172800,
             "values": ["ns1.mockfactory.io.", "ns2.mockfactory.io.",
                        "ns3.mockfactory.io.", "ns4.mockfactory.io."]},
        ],
        "resourceRecordSetCount": 2,
        "createdAt": utcnow_iso(),
    }
    resources["route53_zones"].append(zone)
    flag_resources_modified(db, env)
    return {
        "HostedZone": {"Id": f"/hostedzone/{zone_id}", "Name": zone_name,
                       "CallerReference": zone["callerReference"],
                       "Config": {"PrivateZone": zone["privateZone"]},
                       "ResourceRecordSetCount": 2},
        "ChangeInfo": {"Id": f"/change/{route53_change_id()}", "Status": "INSYNC",
                       "SubmittedAt": utcnow_iso()},
        "DelegationSet": {"NameServers": ["ns1.mockfactory.io", "ns2.mockfactory.io",
                                          "ns3.mockfactory.io", "ns4.mockfactory.io"]},
    }


def _r53_list_zones(resources):
    zones = resources.get("route53_zones", [])
    return {
        "HostedZones": [
            {"Id": f"/hostedzone/{z['id']}", "Name": z["name"],
             "CallerReference": z["callerReference"],
             "Config": {"PrivateZone": z["privateZone"]},
             "ResourceRecordSetCount": len(z.get("records", []))}
            for z in zones
        ],
        "IsTruncated": False, "MaxItems": "100",
    }


def _r53_get_zone(body, resources):
    zone_id = body.get("Id", "").split("/")[-1]
    zones = resources.get("route53_zones", [])
    zone = find_by_id(zones, "id", zone_id)
    if not zone:
        raise HTTPException(404, "NoSuchHostedZone")
    return {
        "HostedZone": {"Id": f"/hostedzone/{zone['id']}", "Name": zone["name"],
                       "ResourceRecordSetCount": len(zone.get("records", []))},
        "DelegationSet": {"NameServers": ["ns1.mockfactory.io", "ns2.mockfactory.io"]},
    }


def _r53_change_records(env, body, resources, db):
    zone_id = body.get("HostedZoneId", "").split("/")[-1]
    zones = resources.get("route53_zones", [])
    zone = find_by_id(zones, "id", zone_id)
    if not zone:
        raise HTTPException(404, "NoSuchHostedZone")
    for change in body.get("ChangeBatch", {}).get("Changes", []):
        action = change.get("Action")
        rrs = change.get("ResourceRecordSet", {})
        if action in ("CREATE", "UPSERT"):
            zone["records"].append({
                "name": rrs.get("Name"), "type": rrs.get("Type"),
                "ttl": rrs.get("TTL", 300),
                "values": [r.get("Value") for r in rrs.get("ResourceRecords", [])],
                "alias": rrs.get("AliasTarget"),
            })
        elif action == "DELETE":
            zone["records"] = [
                r for r in zone["records"]
                if not (r["name"] == rrs.get("Name") and r["type"] == rrs.get("Type"))
            ]
    flag_resources_modified(db, env)
    change_id = route53_change_id()
    return {"ChangeInfo": {"Id": f"/change/{change_id}", "Status": "INSYNC",
                           "SubmittedAt": utcnow_iso()}}


def _r53_list_records(body, resources):
    zone_id = body.get("HostedZoneId", "").split("/")[-1]
    zones = resources.get("route53_zones", [])
    zone = find_by_id(zones, "id", zone_id)
    if not zone:
        raise HTTPException(404, "NoSuchHostedZone")
    return {
        "ResourceRecordSets": [
            {"Name": r["name"], "Type": r["type"], "TTL": r.get("ttl", 300),
             "ResourceRecords": [{"Value": v} for v in r.get("values", [])]}
            for r in zone.get("records", [])
        ],
        "IsTruncated": False, "MaxItems": "300",
    }


def _r53_get_change(body):
    change_id = body.get("Id", "").split("/")[-1]
    return {"ChangeInfo": {"Id": f"/change/{change_id}", "Status": "INSYNC",
                           "SubmittedAt": utcnow_iso()}}


# ============================================================================
# AWS IAM
# ============================================================================

@router.post("/iam/")
async def iam_api(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    form = await request.form()
    body = dict(form)
    action = body.get("Action", "")
    resources = get_resources(env)

    if action == "CreateUser":
        return _iam_create_user(env, body, resources, db)
    if action == "ListUsers":
        return _iam_list_users(resources)
    if action == "GetUser":
        return _iam_get_user(body, resources)
    if action == "DeleteUser":
        return _iam_delete_user(env, body, resources, db)
    if action == "CreateAccessKey":
        return _iam_create_access_key(env, body, resources, db)
    if action == "ListAccessKeys":
        return _iam_list_access_keys(body, resources)
    if action == "DeleteAccessKey":
        return _iam_delete_access_key(env, body, resources, db)
    if action == "CreateRole":
        return _iam_create_role(env, body, resources, db)
    if action == "ListRoles":
        return _iam_list_roles(resources)
    if action == "GetRole":
        return _iam_get_role(body, resources)
    if action == "CreatePolicy":
        return _iam_create_policy(env, body, resources, db)
    if action == "ListPolicies":
        return _iam_list_policies(resources)
    if action == "AttachUserPolicy":
        return _iam_attach_policy(env, body, resources, db, "user")
    if action == "AttachRolePolicy":
        return _iam_attach_policy(env, body, resources, db, "role")
    raise HTTPException(400, f"Unsupported IAM action: {action}")


def _iam_user_xml(parent, user):
    ET.SubElement(parent, "UserId").text = user["userId"]
    ET.SubElement(parent, "UserName").text = user["userName"]
    ET.SubElement(parent, "Arn").text = user["arn"]
    ET.SubElement(parent, "Path").text = user.get("path", "/")
    ET.SubElement(parent, "CreateDate").text = user["createDate"]


def _iam_create_user(env, body, resources, db):
    if "iam_users" not in resources:
        resources["iam_users"] = []
    name = body.get("UserName")
    uid = iam_user_id()
    user = {"userId": uid, "userName": name, "path": body.get("Path", "/"),
             "arn": iam_arn(f"user/{name}"), "createDate": utcnow_iso(),
             "accessKeys": [], "attachedPolicies": []}
    resources["iam_users"].append(user)
    flag_resources_modified(db, env)
    root = ET.Element("CreateUserResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateUserResult")
    u = ET.SubElement(result, "User")
    _iam_user_xml(u, user)
    ET.SubElement(ET.SubElement(root, "ResponseMetadata"), "RequestId").text = aws_request_id()
    return _xml_resp(root)


def _iam_list_users(resources):
    root = ET.Element("ListUsersResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListUsersResult")
    users_el = ET.SubElement(result, "Users")
    for u in resources.get("iam_users", []):
        member = ET.SubElement(users_el, "member")
        _iam_user_xml(member, u)
    ET.SubElement(result, "IsTruncated").text = "false"
    return _xml_resp(root)


def _iam_get_user(body, resources):
    name = body.get("UserName")
    users = resources.get("iam_users", [])
    user = find_by_id(users, "userName", name) if name else (users[0] if users else None)
    if not user:
        raise HTTPException(404, "NoSuchEntity")
    root = ET.Element("GetUserResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "GetUserResult")
    u = ET.SubElement(result, "User")
    _iam_user_xml(u, user)
    return _xml_resp(root)


def _iam_delete_user(env, body, resources, db):
    name = body.get("UserName")
    users = resources.get("iam_users", [])
    remove_by_id(users, "userName", name)
    flag_resources_modified(db, env)
    root = ET.Element("DeleteUserResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    ET.SubElement(ET.SubElement(root, "ResponseMetadata"), "RequestId").text = aws_request_id()
    return _xml_resp(root)


def _iam_create_access_key(env, body, resources, db):
    name = body.get("UserName")
    users = resources.get("iam_users", [])
    user = find_by_id(users, "userName", name)
    if not user:
        raise HTTPException(404, "NoSuchEntity")
    key_id = iam_access_key_id()
    secret = iam_secret_key()
    key = {"accessKeyId": key_id, "secretAccessKey": secret, "status": "Active",
           "userName": name, "createDate": utcnow_iso()}
    user.setdefault("accessKeys", []).append({"accessKeyId": key_id, "status": "Active"})
    flag_resources_modified(db, env)
    root = ET.Element("CreateAccessKeyResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateAccessKeyResult")
    k = ET.SubElement(result, "AccessKey")
    ET.SubElement(k, "AccessKeyId").text = key_id
    ET.SubElement(k, "SecretAccessKey").text = secret
    ET.SubElement(k, "Status").text = "Active"
    ET.SubElement(k, "UserName").text = name
    return _xml_resp(root)


def _iam_list_access_keys(body, resources):
    name = body.get("UserName")
    users = resources.get("iam_users", [])
    user = find_by_id(users, "userName", name)
    root = ET.Element("ListAccessKeysResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListAccessKeysResult")
    members = ET.SubElement(result, "AccessKeyMetadata")
    for k in (user or {}).get("accessKeys", []):
        m = ET.SubElement(members, "member")
        ET.SubElement(m, "AccessKeyId").text = k["accessKeyId"]
        ET.SubElement(m, "Status").text = k["status"]
        ET.SubElement(m, "UserName").text = name or ""
    ET.SubElement(result, "IsTruncated").text = "false"
    return _xml_resp(root)


def _iam_delete_access_key(env, body, resources, db):
    name = body.get("UserName")
    key_id = body.get("AccessKeyId")
    users = resources.get("iam_users", [])
    user = find_by_id(users, "userName", name)
    if user:
        user["accessKeys"] = [k for k in user.get("accessKeys", [])
                               if k["accessKeyId"] != key_id]
        flag_resources_modified(db, env)
    root = ET.Element("DeleteAccessKeyResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    ET.SubElement(ET.SubElement(root, "ResponseMetadata"), "RequestId").text = aws_request_id()
    return _xml_resp(root)


def _iam_create_role(env, body, resources, db):
    if "iam_roles" not in resources:
        resources["iam_roles"] = []
    name = body.get("RoleName")
    role_id = iam_role_id()
    role = {"roleId": role_id, "roleName": name, "path": body.get("Path", "/"),
             "arn": iam_arn(f"role/{name}"),
             "assumeRolePolicyDocument": body.get("AssumeRolePolicyDocument", "{}"),
             "createDate": utcnow_iso(), "attachedPolicies": []}
    resources["iam_roles"].append(role)
    flag_resources_modified(db, env)
    root = ET.Element("CreateRoleResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreateRoleResult")
    r = ET.SubElement(result, "Role")
    ET.SubElement(r, "RoleId").text = role_id
    ET.SubElement(r, "RoleName").text = name
    ET.SubElement(r, "Arn").text = role["arn"]
    ET.SubElement(r, "Path").text = role["path"]
    ET.SubElement(r, "CreateDate").text = role["createDate"]
    return _xml_resp(root)


def _iam_list_roles(resources):
    root = ET.Element("ListRolesResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListRolesResult")
    roles_el = ET.SubElement(result, "Roles")
    for r in resources.get("iam_roles", []):
        m = ET.SubElement(roles_el, "member")
        ET.SubElement(m, "RoleId").text = r["roleId"]
        ET.SubElement(m, "RoleName").text = r["roleName"]
        ET.SubElement(m, "Arn").text = r["arn"]
    ET.SubElement(result, "IsTruncated").text = "false"
    return _xml_resp(root)


def _iam_get_role(body, resources):
    name = body.get("RoleName")
    role = find_by_id(resources.get("iam_roles", []), "roleName", name)
    if not role:
        raise HTTPException(404, "NoSuchEntity")
    root = ET.Element("GetRoleResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "GetRoleResult")
    r = ET.SubElement(result, "Role")
    ET.SubElement(r, "RoleId").text = role["roleId"]
    ET.SubElement(r, "RoleName").text = role["roleName"]
    ET.SubElement(r, "Arn").text = role["arn"]
    return _xml_resp(root)


def _iam_create_policy(env, body, resources, db):
    if "iam_policies" not in resources:
        resources["iam_policies"] = []
    name = body.get("PolicyName")
    pid = iam_policy_id()
    policy = {"policyId": pid, "policyName": name,
               "arn": iam_arn(f"policy/{name}"),
               "document": body.get("PolicyDocument", "{}"),
               "createDate": utcnow_iso(), "attachmentCount": 0}
    resources["iam_policies"].append(policy)
    flag_resources_modified(db, env)
    root = ET.Element("CreatePolicyResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "CreatePolicyResult")
    p = ET.SubElement(result, "Policy")
    ET.SubElement(p, "PolicyId").text = pid
    ET.SubElement(p, "PolicyName").text = name
    ET.SubElement(p, "Arn").text = policy["arn"]
    return _xml_resp(root)


def _iam_list_policies(resources):
    root = ET.Element("ListPoliciesResponse", xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    result = ET.SubElement(root, "ListPoliciesResult")
    pols = ET.SubElement(result, "Policies")
    for p in resources.get("iam_policies", []):
        m = ET.SubElement(pols, "member")
        ET.SubElement(m, "PolicyId").text = p["policyId"]
        ET.SubElement(m, "PolicyName").text = p["policyName"]
        ET.SubElement(m, "Arn").text = p["arn"]
    ET.SubElement(result, "IsTruncated").text = "false"
    return _xml_resp(root)


def _iam_attach_policy(env, body, resources, db, target_type):
    policy_arn = body.get("PolicyArn", "")
    target_name = body.get("UserName" if target_type == "user" else "RoleName", "")
    collection = "iam_users" if target_type == "user" else "iam_roles"
    id_key = "userName" if target_type == "user" else "roleName"
    target = find_by_id(resources.get(collection, []), id_key, target_name)
    if target:
        target.setdefault("attachedPolicies", []).append(policy_arn)
        flag_resources_modified(db, env)
    root = ET.Element(f"Attach{'User' if target_type == 'user' else 'Role'}PolicyResponse",
                      xmlns="https://iam.amazonaws.com/doc/2010-05-08/")
    ET.SubElement(ET.SubElement(root, "ResponseMetadata"), "RequestId").text = aws_request_id()
    return _xml_resp(root)


# ============================================================================
# AWS Lambda — real Docker execution
# ============================================================================

@router.post("/lambda/2015-03-31/functions")
async def lambda_create_function(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    body = await request.json()
    name = body.get("FunctionName")
    if not name:
        raise HTTPException(400, "FunctionName required")

    resources = get_resources(env)
    if "lambda_functions" not in resources:
        resources["lambda_functions"] = []

    runtime = body.get("Runtime", "python3.11")
    handler = body.get("Handler", "index.handler")
    fn_arn = lambda_arn(name)

    existing = find_by_id(resources["lambda_functions"], "name", name)
    if existing:
        existing.update({"runtime": runtime, "handler": handler,
                         "code": body.get("Code", {}),
                         "environment": body.get("Environment", {}).get("Variables", {}),
                         "timeout": body.get("Timeout", 30),
                         "memorySize": body.get("MemorySize", 128)})
        flag_resources_modified(db, env)
        return _json_resp({**existing, "FunctionName": name, "FunctionArn": fn_arn,
                           "Runtime": runtime, "Handler": handler, "State": "Active"})

    func = {"name": name, "arn": fn_arn, "runtime": runtime, "handler": handler,
             "code": body.get("Code", {}),
             "environment": body.get("Environment", {}).get("Variables", {}),
             "timeout": body.get("Timeout", 30),
             "memorySize": body.get("MemorySize", 128),
             "role": body.get("Role", ""),
             "description": body.get("Description", ""),
             "createdAt": utcnow_iso(), "lastModified": utcnow_iso()}
    resources["lambda_functions"].append(func)
    flag_resources_modified(db, env)

    return _json_resp({"FunctionName": name, "FunctionArn": fn_arn, "Runtime": runtime,
                       "Handler": handler, "State": "Active", "CodeSize": 0,
                       "Description": func["description"], "Timeout": func["timeout"],
                       "MemorySize": func["memorySize"], "LastModified": func["lastModified"],
                       "Role": func["role"]})


@router.get("/lambda/2015-03-31/functions")
async def lambda_list_functions(request: Request, db: Session = Depends(get_db)):
    env = _env(request, db)
    resources = get_resources(env)
    funcs = resources.get("lambda_functions", [])
    return _json_resp({"Functions": [
        {"FunctionName": f["name"], "FunctionArn": f["arn"],
         "Runtime": f["runtime"], "Handler": f["handler"],
         "State": "Active", "LastModified": f.get("lastModified", utcnow_iso())}
        for f in funcs
    ], "NextMarker": None})


@router.get("/lambda/2015-03-31/functions/{function_name}")
async def lambda_get_function(
    function_name: str, request: Request, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    func = find_by_id(resources.get("lambda_functions", []), "name", function_name)
    if not func:
        raise HTTPException(404, "ResourceNotFoundException")
    return _json_resp({"Configuration": {
        "FunctionName": func["name"], "FunctionArn": func["arn"],
        "Runtime": func["runtime"], "Handler": func["handler"],
        "State": "Active", "Timeout": func["timeout"],
        "MemorySize": func["memorySize"],
    }, "Code": {"Location": f"https://lambda.{DEFAULT_AWS_REGION}.amazonaws.com/code/{func['name']}"}})


@router.delete("/lambda/2015-03-31/functions/{function_name}")
async def lambda_delete_function(
    function_name: str, request: Request, db: Session = Depends(get_db),
):
    env = _env(request, db)
    resources = get_resources(env)
    funcs = resources.get("lambda_functions", [])
    if not remove_by_id(funcs, "name", function_name):
        raise HTTPException(404, "ResourceNotFoundException")
    flag_resources_modified(db, env)
    return Response(status_code=204, headers=aws_headers())


@router.post("/lambda/2015-03-31/functions/{function_name}/invocations")
async def lambda_invoke(
    function_name: str,
    request: Request,
    x_amz_invocation_type: str = Header("RequestResponse"),
    db: Session = Depends(get_db),
):
    """
    AWS Lambda Invoke — actually executes the function code in a Docker container.
    Supports Python 3.x, Node.js, Ruby runtimes.
    """
    env = _env(request, db)
    resources = get_resources(env)
    func = find_by_id(resources.get("lambda_functions", []), "name", function_name)
    if not func:
        raise HTTPException(404, "ResourceNotFoundException")

    if x_amz_invocation_type == "Event":
        # Async — fire and forget, return 202
        return Response(status_code=202, headers={**aws_headers(),
                                                   "x-amz-function-error": ""})

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    result = await _run_lambda_in_docker(func, payload)
    fn_error = "" if result.get("statusCode", 200) < 400 else "Handled"

    return Response(
        content=json.dumps(result),
        status_code=200,
        headers={
            **aws_headers(),
            "x-amz-function-error": fn_error,
            "x-amz-log-type": "None",
            "x-amz-executed-version": "$LATEST",
        },
        media_type="application/json",
    )


async def _run_lambda_in_docker(func: dict, payload: dict) -> dict:
    """Execute Lambda function code in an isolated Docker container."""
    runtime = func.get("runtime", "python3.11")
    image = LAMBDA_RUNTIME_IMAGES.get(runtime, "python:3.11-alpine")
    handler = func.get("handler", "index.handler")
    code = func.get("code", {})
    env_vars = func.get("environment", {})
    timeout = min(func.get("timeout", 30), 60)

    code_zip_b64 = code.get("ZipFile", "")
    if not code_zip_b64:
        return {"statusCode": 200, "body": json.dumps({
            "message": f"Lambda {func['name']} invoked (no code provided)",
            "input": payload, "runtime": runtime,
        })}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "function.zip")
            with open(zip_path, "wb") as f:
                f.write(base64.b64decode(code_zip_b64))

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)

            module_name, handler_fn = handler.rsplit(".", 1)

            if runtime.startswith("python"):
                exec_script = (
                    f"import sys, json\n"
                    f"sys.path.insert(0, '/function')\n"
                    f"import {module_name} as m\n"
                    f"event = {json.dumps(payload)}\n"
                    f"result = m.{handler_fn}(event, {{}})\n"
                    f"print(json.dumps(result) if not isinstance(result, str) else result)\n"
                )
                cmd = ["python", "-c", exec_script]

            elif runtime.startswith("nodejs"):
                exec_script = (
                    f"const h = require('/function/{module_name}').{handler_fn};\n"
                    f"const e = {json.dumps(payload)};\n"
                    f"Promise.resolve(h(e, {{}})).then(r => "
                    f"console.log(JSON.stringify(r))).catch(e => "
                    f"{{console.error(e.message); process.exit(1);}});\n"
                )
                cmd = ["node", "-e", exec_script]

            elif runtime.startswith("ruby"):
                exec_script = (
                    f"require 'json'\n"
                    f"require '/function/{module_name}'\n"
                    f"event = {json.dumps(payload)}\n"
                    f"result = method(:{handler_fn}).call(event, {{}})\n"
                    f"puts result.to_json\n"
                )
                cmd = ["ruby", "-e", exec_script]

            else:
                return {"statusCode": 500, "body": json.dumps(
                    {"errorMessage": f"Runtime {runtime} not supported for execution"})}

            client = docker.from_env()
            container_out = client.containers.run(
                image,
                command=cmd,
                volumes={tmpdir: {"bind": "/function", "mode": "ro"}},
                environment=env_vars,
                network_mode="none",
                mem_limit=f"{func.get('memorySize', 128)}m",
                cpu_quota=50000,
                remove=True,
                stdout=True,
                stderr=False,
                timeout=timeout,
            )

            output = container_out.decode("utf-8").strip()
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"statusCode": 200, "body": output}

    except docker.errors.ContainerError as e:
        return {"statusCode": 500, "body": json.dumps(
            {"errorMessage": str(e), "errorType": "ContainerError"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps(
            {"errorMessage": str(e), "errorType": "InvocationError"})}


# ============================================================================
# AWS SNS / SQS pass-through helpers (ElasticMQ is already S3-compatible)
# ============================================================================

@router.post("/sns/")
async def sns_api(request: Request, db: Session = Depends(get_db)):
    """AWS SNS — CreateTopic, ListTopics, Subscribe, Publish."""
    env = _env(request, db)
    form = await request.form()
    body = dict(form)
    action = body.get("Action", "")
    resources = get_resources(env)

    if action == "CreateTopic":
        name = body.get("Name")
        arn = sns_topic_arn(name)
        if "sns_topics" not in resources:
            resources["sns_topics"] = []
        if not find_by_id(resources["sns_topics"], "name", name):
            resources["sns_topics"].append({"name": name, "arn": arn,
                                             "subscriptions": [], "createdAt": utcnow_iso()})
            flag_resources_modified(db, env)
        root = ET.Element("CreateTopicResponse", xmlns="http://sns.amazonaws.com/doc/2010-03-31/")
        ET.SubElement(ET.SubElement(root, "CreateTopicResult"), "TopicArn").text = arn
        return _xml_resp(root)

    if action == "ListTopics":
        root = ET.Element("ListTopicsResponse", xmlns="http://sns.amazonaws.com/doc/2010-03-31/")
        result = ET.SubElement(root, "ListTopicsResult")
        topics_el = ET.SubElement(result, "Topics")
        for t in resources.get("sns_topics", []):
            m = ET.SubElement(topics_el, "member")
            ET.SubElement(m, "TopicArn").text = t["arn"]
        return _xml_resp(root)

    if action == "Publish":
        topic_arn = body.get("TopicArn", "")
        msg = body.get("Message", "")
        msg_id = str(uuid.uuid4())
        root = ET.Element("PublishResponse", xmlns="http://sns.amazonaws.com/doc/2010-03-31/")
        ET.SubElement(ET.SubElement(root, "PublishResult"), "MessageId").text = msg_id
        return _xml_resp(root)

    if action == "Subscribe":
        topic_arn = body.get("TopicArn", "")
        sub_arn = f"{topic_arn}:{uuid.uuid4()}"
        root = ET.Element("SubscribeResponse", xmlns="http://sns.amazonaws.com/doc/2010-03-31/")
        ET.SubElement(ET.SubElement(root, "SubscribeResult"), "SubscriptionArn").text = sub_arn
        return _xml_resp(root)

    raise HTTPException(400, f"Unsupported SNS action: {action}")
