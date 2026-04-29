"""
AWS VPC API Emulator
All VPC state stored in environment.oci_resources — no external cloud dependency.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.mock_helpers import (
    aws_request_id,
    ec2_igw_id,
    ec2_rtb_id,
    ec2_sg_id,
    ec2_subnet_id,
    ec2_vpc_id,
    find_by_id,
    flag_resources_modified,
    random_private_ip,
    remove_by_id,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_env(request: Request, db: Session) -> Environment:
    host = request.headers.get("host", "")
    env_id = next((p for p in host.split(".") if p.startswith("env-")), None)
    if not env_id:
        env_id = request.headers.get("X-Mock-Environment-ID")
    if not env_id:
        raise HTTPException(status_code=400, detail="Environment ID required")
    env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.status == EnvironmentStatus.RUNNING,
    ).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env


def _res(env: Environment) -> dict:
    if env.oci_resources is None:
        env.oci_resources = {}
    return env.oci_resources


def _ns(res: dict, key: str) -> list:
    if key not in res:
        res[key] = []
    return res[key]


def _rid() -> str:
    return str(uuid.uuid4())


def _xml(tag: str, inner: str, request_id: Optional[str] = None) -> Response:
    rid = request_id or aws_request_id()
    body = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<{tag} xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">'
        f"<requestId>{rid}</requestId>"
        f"{inner}"
        f"</{tag}>"
    )
    return Response(content=body, media_type="application/xml")


# ---------------------------------------------------------------------------
# Router entry point
# ---------------------------------------------------------------------------

@router.post("/aws/vpc")
async def aws_vpc_api(request: Request, db: Session = Depends(get_db)):
    env = _get_env(request, db)
    body = await request.body()
    params: dict = {}
    if body:
        params = dict(x.split("=", 1) for x in body.decode().split("&") if "=" in x)

    action = params.get("Action") or request.query_params.get("Action")
    dispatch = {
        "CreateVpc": _create_vpc,
        "DescribeVpcs": _describe_vpcs,
        "DeleteVpc": _delete_vpc,
        "CreateSubnet": _create_subnet,
        "DescribeSubnets": _describe_subnets,
        "DeleteSubnet": _delete_subnet,
        "CreateSecurityGroup": _create_sg,
        "DescribeSecurityGroups": _describe_sgs,
        "DeleteSecurityGroup": _delete_sg,
        "AuthorizeSecurityGroupIngress": _authorize_ingress,
        "AuthorizeSecurityGroupEgress": _authorize_egress,
        "CreateInternetGateway": _create_igw,
        "DescribeInternetGateways": _describe_igws,
        "AttachInternetGateway": _attach_igw,
        "DetachInternetGateway": _detach_igw,
        "DeleteInternetGateway": _delete_igw,
        "CreateRouteTable": _create_rtb,
        "DescribeRouteTables": _describe_rtbs,
        "CreateRoute": _create_route,
        "AssociateRouteTable": _associate_rtb,
        "DeleteRouteTable": _delete_rtb,
    }
    handler = dispatch.get(action)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unsupported VPC action: {action}")
    return handler(env, params, db)


# ---------------------------------------------------------------------------
# VPCs
# ---------------------------------------------------------------------------

def _create_vpc(env: Environment, params: dict, db: Session) -> Response:
    cidr = params.get("CidrBlock", "10.0.0.0/16")
    vpc_id = ec2_vpc_id()
    res = _res(env)
    _ns(res, "vpcs").append({
        "id": vpc_id,
        "cidr": cidr,
        "state": "available",
        "tenancy": "default",
        "is_default": False,
        "subnets": [],
        "sgs": [],
        "igws": [],
        "rtbs": [],
        "tags": [],
    })
    flag_resources_modified(db, env)
    return _xml("CreateVpcResponse", f"""
        <vpc>
            <vpcId>{vpc_id}</vpcId>
            <state>available</state>
            <cidrBlock>{cidr}</cidrBlock>
            <dhcpOptionsId>dopt-{uuid.uuid4().hex[:17]}</dhcpOptionsId>
            <instanceTenancy>default</instanceTenancy>
            <isDefault>false</isDefault>
        </vpc>""")


def _describe_vpcs(env: Environment, params: dict, db: Session) -> Response:
    vpcs = (env.oci_resources or {}).get("vpcs", [])
    items = "".join(f"""
        <item>
            <vpcId>{v['id']}</vpcId>
            <state>{v['state']}</state>
            <cidrBlock>{v['cidr']}</cidrBlock>
            <instanceTenancy>{v.get('tenancy','default')}</instanceTenancy>
            <isDefault>{str(v.get('is_default', False)).lower()}</isDefault>
        </item>""" for v in vpcs)
    return _xml("DescribeVpcsResponse", f"<vpcSet>{items}</vpcSet>")


def _delete_vpc(env: Environment, params: dict, db: Session) -> Response:
    vpc_id = params.get("VpcId")
    res = _res(env)
    if not remove_by_id(_ns(res, "vpcs"), "id", vpc_id):
        raise HTTPException(status_code=400, detail="VPC not found")
    flag_resources_modified(db, env)
    return _xml("DeleteVpcResponse", "<return>true</return>")


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

def _create_subnet(env: Environment, params: dict, db: Session) -> Response:
    vpc_id = params.get("VpcId")
    cidr = params.get("CidrBlock", "10.0.1.0/24")
    az = params.get("AvailabilityZone", "us-east-1a")
    res = _res(env)
    vpc = find_by_id(_ns(res, "vpcs"), "id", vpc_id)
    if not vpc:
        raise HTTPException(status_code=400, detail="VPC not found")

    subnet_id = ec2_subnet_id()
    subnet = {
        "id": subnet_id,
        "vpc_id": vpc_id,
        "cidr": cidr,
        "az": az,
        "state": "available",
        "available_ips": 251,
        "map_public_ip": False,
        "tags": [],
    }
    _ns(res, "subnets").append(subnet)
    flag_resources_modified(db, env)
    return _xml("CreateSubnetResponse", f"""
        <subnet>
            <subnetId>{subnet_id}</subnetId>
            <state>available</state>
            <vpcId>{vpc_id}</vpcId>
            <cidrBlock>{cidr}</cidrBlock>
            <availableIpAddressCount>251</availableIpAddressCount>
            <availabilityZone>{az}</availabilityZone>
            <defaultForAz>false</defaultForAz>
            <mapPublicIpOnLaunch>false</mapPublicIpOnLaunch>
        </subnet>""")


def _describe_subnets(env: Environment, params: dict, db: Session) -> Response:
    subnets = (env.oci_resources or {}).get("subnets", [])
    vpc_filter = params.get("Filter.1.Value.1")
    if vpc_filter:
        subnets = [s for s in subnets if s.get("vpc_id") == vpc_filter]
    items = "".join(f"""
        <item>
            <subnetId>{s['id']}</subnetId>
            <state>{s['state']}</state>
            <vpcId>{s['vpc_id']}</vpcId>
            <cidrBlock>{s['cidr']}</cidrBlock>
            <availableIpAddressCount>{s.get('available_ips', 251)}</availableIpAddressCount>
            <availabilityZone>{s['az']}</availabilityZone>
            <mapPublicIpOnLaunch>{str(s.get('map_public_ip', False)).lower()}</mapPublicIpOnLaunch>
        </item>""" for s in subnets)
    return _xml("DescribeSubnetsResponse", f"<subnetSet>{items}</subnetSet>")


def _delete_subnet(env: Environment, params: dict, db: Session) -> Response:
    subnet_id = params.get("SubnetId")
    res = _res(env)
    if not remove_by_id(_ns(res, "subnets"), "id", subnet_id):
        raise HTTPException(status_code=400, detail="Subnet not found")
    flag_resources_modified(db, env)
    return _xml("DeleteSubnetResponse", "<return>true</return>")


# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

def _create_sg(env: Environment, params: dict, db: Session) -> Response:
    vpc_id = params.get("VpcId")
    name = params.get("GroupName", "default")
    desc = params.get("GroupDescription", "Mock security group")
    sg_id = ec2_sg_id()
    res = _res(env)
    _ns(res, "security_groups").append({
        "id": sg_id,
        "vpc_id": vpc_id,
        "name": name,
        "description": desc,
        "ingress_rules": [],
        "egress_rules": [],
        "tags": [],
    })
    flag_resources_modified(db, env)
    return _xml("CreateSecurityGroupResponse", f"<groupId>{sg_id}</groupId>")


def _describe_sgs(env: Environment, params: dict, db: Session) -> Response:
    sgs = (env.oci_resources or {}).get("security_groups", [])
    items = "".join(f"""
        <item>
            <groupId>{sg['id']}</groupId>
            <groupName>{sg['name']}</groupName>
            <groupDescription>{sg['description']}</groupDescription>
            <vpcId>{sg.get('vpc_id','')}</vpcId>
            <ipPermissions>{_rules_xml(sg.get('ingress_rules',[]))}</ipPermissions>
            <ipPermissionsEgress>{_rules_xml(sg.get('egress_rules',[]))}</ipPermissionsEgress>
        </item>""" for sg in sgs)
    return _xml("DescribeSecurityGroupsResponse", f"<securityGroupInfo>{items}</securityGroupInfo>")


def _rules_xml(rules: list) -> str:
    out = ""
    for r in rules:
        out += f"""
            <item>
                <ipProtocol>{r.get('protocol','-1')}</ipProtocol>
                <fromPort>{r.get('from_port','')}</fromPort>
                <toPort>{r.get('to_port','')}</toPort>
                <ipRanges><item><cidrIp>{r.get('cidr','0.0.0.0/0')}</cidrIp></item></ipRanges>
            </item>"""
    return out


def _delete_sg(env: Environment, params: dict, db: Session) -> Response:
    sg_id = params.get("GroupId")
    res = _res(env)
    if not remove_by_id(_ns(res, "security_groups"), "id", sg_id):
        raise HTTPException(status_code=400, detail="Security group not found")
    flag_resources_modified(db, env)
    return _xml("DeleteSecurityGroupResponse", "<return>true</return>")


def _authorize_ingress(env: Environment, params: dict, db: Session) -> Response:
    return _add_rule(env, params, db, "ingress")


def _authorize_egress(env: Environment, params: dict, db: Session) -> Response:
    return _add_rule(env, params, db, "egress")


def _add_rule(env: Environment, params: dict, db: Session, direction: str) -> Response:
    sg_id = params.get("GroupId")
    res = _res(env)
    sg = find_by_id(_ns(res, "security_groups"), "id", sg_id)
    if not sg:
        raise HTTPException(status_code=400, detail="Security group not found")

    key = "ingress_rules" if direction == "ingress" else "egress_rules"
    sg.setdefault(key, []).append({
        "protocol": params.get("IpPermissions.1.IpProtocol", params.get("IpProtocol", "tcp")),
        "from_port": params.get("IpPermissions.1.FromPort", params.get("FromPort")),
        "to_port": params.get("IpPermissions.1.ToPort", params.get("ToPort")),
        "cidr": params.get("IpPermissions.1.IpRanges.1.CidrIp", params.get("CidrIp", "0.0.0.0/0")),
    })
    flag_resources_modified(db, env)
    tag = "AuthorizeSecurityGroupIngressResponse" if direction == "ingress" else "AuthorizeSecurityGroupEgressResponse"
    return _xml(tag, "<return>true</return>")


# ---------------------------------------------------------------------------
# Internet Gateways
# ---------------------------------------------------------------------------

def _create_igw(env: Environment, params: dict, db: Session) -> Response:
    igw_id = ec2_igw_id()
    res = _res(env)
    _ns(res, "internet_gateways").append({
        "id": igw_id,
        "state": "detached",
        "vpc_id": None,
        "tags": [],
    })
    flag_resources_modified(db, env)
    return _xml("CreateInternetGatewayResponse", f"""
        <internetGateway>
            <internetGatewayId>{igw_id}</internetGatewayId>
            <attachmentSet/>
            <tagSet/>
        </internetGateway>""")


def _describe_igws(env: Environment, params: dict, db: Session) -> Response:
    igws = (env.oci_resources or {}).get("internet_gateways", [])
    items = "".join(f"""
        <item>
            <internetGatewayId>{i['id']}</internetGatewayId>
            <attachmentSet>
                {"<item><vpcId>" + i['vpc_id'] + "</vpcId><state>available</state></item>" if i.get('vpc_id') else ""}
            </attachmentSet>
        </item>""" for i in igws)
    return _xml("DescribeInternetGatewaysResponse",
                f"<internetGatewaySet>{items}</internetGatewaySet>")


def _attach_igw(env: Environment, params: dict, db: Session) -> Response:
    igw_id = params.get("InternetGatewayId")
    vpc_id = params.get("VpcId")
    res = _res(env)
    igw = find_by_id(_ns(res, "internet_gateways"), "id", igw_id)
    if not igw:
        raise HTTPException(status_code=400, detail="IGW not found")
    igw["vpc_id"] = vpc_id
    igw["state"] = "attached"
    flag_resources_modified(db, env)
    return _xml("AttachInternetGatewayResponse", "<return>true</return>")


def _detach_igw(env: Environment, params: dict, db: Session) -> Response:
    igw_id = params.get("InternetGatewayId")
    res = _res(env)
    igw = find_by_id(_ns(res, "internet_gateways"), "id", igw_id)
    if igw:
        igw["vpc_id"] = None
        igw["state"] = "detached"
        flag_resources_modified(db, env)
    return _xml("DetachInternetGatewayResponse", "<return>true</return>")


def _delete_igw(env: Environment, params: dict, db: Session) -> Response:
    igw_id = params.get("InternetGatewayId")
    res = _res(env)
    if not remove_by_id(_ns(res, "internet_gateways"), "id", igw_id):
        raise HTTPException(status_code=400, detail="IGW not found")
    flag_resources_modified(db, env)
    return _xml("DeleteInternetGatewayResponse", "<return>true</return>")


# ---------------------------------------------------------------------------
# Route Tables
# ---------------------------------------------------------------------------

def _create_rtb(env: Environment, params: dict, db: Session) -> Response:
    vpc_id = params.get("VpcId")
    rtb_id = ec2_rtb_id()
    res = _res(env)
    _ns(res, "route_tables").append({
        "id": rtb_id,
        "vpc_id": vpc_id,
        "routes": [{"destination": "local", "target": "local", "state": "active"}],
        "associations": [],
        "tags": [],
    })
    flag_resources_modified(db, env)
    return _xml("CreateRouteTableResponse", f"""
        <routeTable>
            <routeTableId>{rtb_id}</routeTableId>
            <vpcId>{vpc_id}</vpcId>
            <routeSet>
                <item>
                    <destinationCidrBlock>local</destinationCidrBlock>
                    <gatewayId>local</gatewayId>
                    <state>active</state>
                </item>
            </routeSet>
        </routeTable>""")


def _describe_rtbs(env: Environment, params: dict, db: Session) -> Response:
    rtbs = (env.oci_resources or {}).get("route_tables", [])
    items = "".join(f"""
        <item>
            <routeTableId>{r['id']}</routeTableId>
            <vpcId>{r.get('vpc_id','')}</vpcId>
        </item>""" for r in rtbs)
    return _xml("DescribeRouteTablesResponse", f"<routeTableSet>{items}</routeTableSet>")


def _create_route(env: Environment, params: dict, db: Session) -> Response:
    rtb_id = params.get("RouteTableId")
    dest = params.get("DestinationCidrBlock", "0.0.0.0/0")
    gw = params.get("GatewayId") or params.get("NatGatewayId") or params.get("InstanceId")
    res = _res(env)
    rtb = find_by_id(_ns(res, "route_tables"), "id", rtb_id)
    if not rtb:
        raise HTTPException(status_code=400, detail="Route table not found")
    rtb.setdefault("routes", []).append({
        "destination": dest,
        "target": gw or "local",
        "state": "active",
    })
    flag_resources_modified(db, env)
    return _xml("CreateRouteResponse", "<return>true</return>")


def _associate_rtb(env: Environment, params: dict, db: Session) -> Response:
    rtb_id = params.get("RouteTableId")
    subnet_id = params.get("SubnetId")
    assoc_id = f"rtbassoc-{uuid.uuid4().hex[:17]}"
    res = _res(env)
    rtb = find_by_id(_ns(res, "route_tables"), "id", rtb_id)
    if not rtb:
        raise HTTPException(status_code=400, detail="Route table not found")
    rtb.setdefault("associations", []).append({
        "id": assoc_id,
        "subnet_id": subnet_id,
    })
    flag_resources_modified(db, env)
    return _xml("AssociateRouteTableResponse",
                f"<associationId>{assoc_id}</associationId>")


def _delete_rtb(env: Environment, params: dict, db: Session) -> Response:
    rtb_id = params.get("RouteTableId")
    res = _res(env)
    if not remove_by_id(_ns(res, "route_tables"), "id", rtb_id):
        raise HTTPException(status_code=400, detail="Route table not found")
    flag_resources_modified(db, env)
    return _xml("DeleteRouteTableResponse", "<return>true</return>")
