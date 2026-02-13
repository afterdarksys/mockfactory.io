"""
AWS VPC API Emulator
Creates REAL OCI VCNs/Subnets in isolated compartment
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import Optional
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.models.vpc_resources import (
    MockVPC, MockSubnet, MockSecurityGroup, MockSecurityGroupRule,
    MockInternetGateway, MockRouteTable, VPCState
)
from app.services.oci_network_service import get_oci_network_service

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
# VPC Operations
# ============================================================================

@router.post("/aws/vpc")
async def aws_vpc_api(request: Request, db: Session = Depends(get_db)):
    """
    AWS VPC API Endpoint
    Creates REAL OCI VCNs in isolated compartment
    """
    environment = get_environment_from_request(request, db)
    body = await request.body()

    # Parse AWS query string format
    params = {}
    if body:
        params = dict(x.split('=') for x in body.decode().split('&') if '=' in x)

    action = params.get('Action', request.query_params.get('Action'))

    if action == 'CreateVpc':
        return await create_vpc(environment, params, db)
    elif action == 'DescribeVpcs':
        return await describe_vpcs(environment, params, db)
    elif action == 'DeleteVpc':
        return await delete_vpc(environment, params, db)
    elif action == 'CreateSubnet':
        return await create_subnet(environment, params, db)
    elif action == 'DescribeSubnets':
        return await describe_subnets(environment, params, db)
    elif action == 'DeleteSubnet':
        return await delete_subnet(environment, params, db)
    elif action == 'CreateSecurityGroup':
        return await create_security_group(environment, params, db)
    elif action == 'DescribeSecurityGroups':
        return await describe_security_groups(environment, params, db)
    elif action == 'AuthorizeSecurityGroupIngress':
        return await authorize_security_group_ingress(environment, params, db)
    elif action == 'CreateInternetGateway':
        return await create_internet_gateway(environment, params, db)
    elif action == 'AttachInternetGateway':
        return await attach_internet_gateway(environment, params, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")


async def create_vpc(environment: Environment, params: dict, db: Session):
    """
    Create VPC - backed by REAL OCI VCN in isolated compartment
    """
    cidr_block = params.get('CidrBlock', '10.0.0.0/16')

    vpc_id = f"vpc-{uuid.uuid4().hex[:17]}"

    try:
        # Create REAL OCI VCN in isolated compartment
        oci_service = get_oci_network_service()
        oci_vcn = oci_service.create_vcn(
            cidr_block=cidr_block,
            display_name=f"mock-aws-vpc-{vpc_id}",
            dns_label=f"vpc{uuid.uuid4().hex[:8]}"
        )

        # Store in database
        vpc = MockVPC(
            id=vpc_id,
            environment_id=environment.id,
            cidr_block=cidr_block,
            state=VPCState.AVAILABLE,
            oci_vcn_id=oci_vcn["vcn_id"],
            oci_compartment_id=oci_vcn["compartment_id"]
        )

        db.add(vpc)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<CreateVpcResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <vpc>
        <vpcId>{vpc.id}</vpcId>
        <state>available</state>
        <cidrBlock>{vpc.cidr_block}</cidrBlock>
        <dhcpOptionsId>dopt-{uuid.uuid4().hex[:17]}</dhcpOptionsId>
        <instanceTenancy>default</instanceTenancy>
        <isDefault>false</isDefault>
        <cidrBlockAssociationSet>
            <item>
                <cidrBlock>{vpc.cidr_block}</cidrBlock>
                <associationId>vpc-cidr-assoc-{uuid.uuid4().hex[:17]}</associationId>
                <cidrBlockState>
                    <state>associated</state>
                </cidrBlockState>
            </item>
        </cidrBlockAssociationSet>
    </vpc>
</CreateVpcResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating VPC: {str(e)}")


async def describe_vpcs(environment: Environment, params: dict, db: Session):
    """Describe VPCs"""
    vpcs = db.query(MockVPC).filter(
        MockVPC.environment_id == environment.id
    ).all()

    vpcs_xml = ""
    for vpc in vpcs:
        vpcs_xml += f"""
        <item>
            <vpcId>{vpc.id}</vpcId>
            <state>{vpc.state.value}</state>
            <cidrBlock>{vpc.cidr_block}</cidrBlock>
            <dhcpOptionsId>dopt-{uuid.uuid4().hex[:17]}</dhcpOptionsId>
            <instanceTenancy>{vpc.instance_tenancy}</instanceTenancy>
            <isDefault>{str(vpc.is_default).lower()}</isDefault>
            <ociVcnId>{vpc.oci_vcn_id}</ociVcnId>
        </item>
        """

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DescribeVpcsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <vpcSet>
        {vpcs_xml}
    </vpcSet>
</DescribeVpcsResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def delete_vpc(environment: Environment, params: dict, db: Session):
    """Delete VPC and underlying OCI VCN"""
    vpc_id = params.get('VpcId')

    vpc = db.query(MockVPC).filter(
        MockVPC.environment_id == environment.id,
        MockVPC.id == vpc_id
    ).first()

    if not vpc:
        raise HTTPException(status_code=404, detail="VPC not found")

    try:
        # Delete REAL OCI VCN
        if vpc.oci_vcn_id:
            oci_service = get_oci_network_service()
            oci_service.delete_vcn(vpc.oci_vcn_id)

        # Delete from database
        db.delete(vpc)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DeleteVpcResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <return>true</return>
</DeleteVpcResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting VPC: {str(e)}")


# ============================================================================
# Subnet Operations
# ============================================================================

async def create_subnet(environment: Environment, params: dict, db: Session):
    """
    Create Subnet - backed by REAL OCI Subnet
    """
    vpc_id = params.get('VpcId')
    cidr_block = params.get('CidrBlock')
    availability_zone = params.get('AvailabilityZone', 'us-east-1a')

    vpc = db.query(MockVPC).filter(
        MockVPC.environment_id == environment.id,
        MockVPC.id == vpc_id
    ).first()

    if not vpc:
        raise HTTPException(status_code=404, detail="VPC not found")

    subnet_id = f"subnet-{uuid.uuid4().hex[:17]}"

    try:
        # Create REAL OCI Subnet
        oci_service = get_oci_network_service()
        oci_subnet = oci_service.create_subnet(
            vcn_id=vpc.oci_vcn_id,
            cidr_block=cidr_block,
            display_name=f"mock-aws-subnet-{subnet_id}",
            dns_label=f"subnet{uuid.uuid4().hex[:6]}",
            prohibit_public_ip=False
        )

        # Store in database
        subnet = MockSubnet(
            id=subnet_id,
            vpc_id=vpc_id,
            environment_id=environment.id,
            cidr_block=cidr_block,
            availability_zone=availability_zone,
            state=VPCState.AVAILABLE,
            oci_subnet_id=oci_subnet["subnet_id"]
        )

        db.add(subnet)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<CreateSubnetResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <subnet>
        <subnetId>{subnet.id}</subnetId>
        <state>available</state>
        <vpcId>{vpc_id}</vpcId>
        <cidrBlock>{cidr_block}</cidrBlock>
        <availableIpAddressCount>251</availableIpAddressCount>
        <availabilityZone>{availability_zone}</availabilityZone>
        <defaultForAz>false</defaultForAz>
        <mapPublicIpOnLaunch>false</mapPublicIpOnLaunch>
    </subnet>
</CreateSubnetResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating subnet: {str(e)}")


async def describe_subnets(environment: Environment, params: dict, db: Session):
    """Describe Subnets"""
    subnets = db.query(MockSubnet).filter(
        MockSubnet.environment_id == environment.id
    ).all()

    subnets_xml = ""
    for subnet in subnets:
        subnets_xml += f"""
        <item>
            <subnetId>{subnet.id}</subnetId>
            <state>{subnet.state.value}</state>
            <vpcId>{subnet.vpc_id}</vpcId>
            <cidrBlock>{subnet.cidr_block}</cidrBlock>
            <availableIpAddressCount>{subnet.available_ip_address_count}</availableIpAddressCount>
            <availabilityZone>{subnet.availability_zone}</availabilityZone>
            <mapPublicIpOnLaunch>{str(subnet.map_public_ip_on_launch).lower()}</mapPublicIpOnLaunch>
            <ociSubnetId>{subnet.oci_subnet_id}</ociSubnetId>
        </item>
        """

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DescribeSubnetsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <subnetSet>
        {subnets_xml}
    </subnetSet>
</DescribeSubnetsResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def delete_subnet(environment: Environment, params: dict, db: Session):
    """Delete Subnet and underlying OCI Subnet"""
    subnet_id = params.get('SubnetId')

    subnet = db.query(MockSubnet).filter(
        MockSubnet.environment_id == environment.id,
        MockSubnet.id == subnet_id
    ).first()

    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    try:
        # Delete REAL OCI Subnet
        if subnet.oci_subnet_id:
            oci_service = get_oci_network_service()
            oci_service.delete_subnet(subnet.oci_subnet_id)

        db.delete(subnet)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DeleteSubnetResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <return>true</return>
</DeleteSubnetResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting subnet: {str(e)}")


# ============================================================================
# Security Group Operations
# ============================================================================

async def create_security_group(environment: Environment, params: dict, db: Session):
    """
    Create Security Group - backed by REAL OCI NSG
    """
    vpc_id = params.get('VpcId')
    group_name = params.get('GroupName')
    description = params.get('GroupDescription', 'Mock security group')

    vpc = db.query(MockVPC).filter(
        MockVPC.environment_id == environment.id,
        MockVPC.id == vpc_id
    ).first()

    if not vpc:
        raise HTTPException(status_code=404, detail="VPC not found")

    sg_id = f"sg-{uuid.uuid4().hex[:17]}"

    try:
        # Create REAL OCI NSG
        oci_service = get_oci_network_service()
        oci_nsg = oci_service.create_network_security_group(
            vcn_id=vpc.oci_vcn_id,
            display_name=f"mock-aws-sg-{sg_id}"
        )

        # Store in database
        sg = MockSecurityGroup(
            id=sg_id,
            vpc_id=vpc_id,
            environment_id=environment.id,
            group_name=group_name,
            description=description,
            oci_nsg_id=oci_nsg["nsg_id"]
        )

        db.add(sg)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<CreateSecurityGroupResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <groupId>{sg_id}</groupId>
</CreateSecurityGroupResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating security group: {str(e)}")


async def describe_security_groups(environment: Environment, params: dict, db: Session):
    """Describe Security Groups"""
    sgs = db.query(MockSecurityGroup).filter(
        MockSecurityGroup.environment_id == environment.id
    ).all()

    sgs_xml = ""
    for sg in sgs:
        sgs_xml += f"""
        <item>
            <groupId>{sg.id}</groupId>
            <groupName>{sg.group_name}</groupName>
            <groupDescription>{sg.description}</groupDescription>
            <vpcId>{sg.vpc_id}</vpcId>
            <ociNsgId>{sg.oci_nsg_id}</ociNsgId>
        </item>
        """

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DescribeSecurityGroupsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <securityGroupInfo>
        {sgs_xml}
    </securityGroupInfo>
</DescribeSecurityGroupsResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def authorize_security_group_ingress(environment: Environment, params: dict, db: Session):
    """
    Add ingress rule to Security Group - creates REAL OCI NSG rule
    """
    sg_id = params.get('GroupId')
    ip_protocol = params.get('IpProtocol', 'tcp')
    from_port = params.get('FromPort')
    to_port = params.get('ToPort')
    cidr_ip = params.get('CidrIp', '0.0.0.0/0')

    sg = db.query(MockSecurityGroup).filter(
        MockSecurityGroup.environment_id == environment.id,
        MockSecurityGroup.id == sg_id
    ).first()

    if not sg:
        raise HTTPException(status_code=404, detail="Security group not found")

    try:
        # Add REAL rule to OCI NSG
        if sg.oci_nsg_id:
            oci_service = get_oci_network_service()

            tcp_options = None
            if ip_protocol == 'tcp' and from_port and to_port:
                tcp_options = {
                    "destination_port_range": {
                        "min": int(from_port),
                        "max": int(to_port)
                    }
                }

            oci_service.add_nsg_rule(
                nsg_id=sg.oci_nsg_id,
                direction="INGRESS",
                protocol=ip_protocol,
                source_cidr=cidr_ip,
                tcp_options=tcp_options
            )

        # Store rule in database
        rule = MockSecurityGroupRule(
            security_group_id=sg_id,
            rule_type="ingress",
            ip_protocol=ip_protocol,
            from_port=int(from_port) if from_port else None,
            to_port=int(to_port) if to_port else None,
            cidr_ipv4=cidr_ip
        )

        db.add(rule)
        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<AuthorizeSecurityGroupIngressResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <return>true</return>
</AuthorizeSecurityGroupIngressResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding security group rule: {str(e)}")


# ============================================================================
# Internet Gateway Operations
# ============================================================================

async def create_internet_gateway(environment: Environment, params: dict, db: Session):
    """Create Internet Gateway"""
    igw_id = f"igw-{uuid.uuid4().hex[:17]}"

    igw = MockInternetGateway(
        id=igw_id,
        environment_id=environment.id,
        state="available"
    )

    db.add(igw)
    db.commit()

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<CreateInternetGatewayResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <internetGateway>
        <internetGatewayId>{igw_id}</internetGatewayId>
        <attachmentSet/>
        <tagSet/>
    </internetGateway>
</CreateInternetGatewayResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def attach_internet_gateway(environment: Environment, params: dict, db: Session):
    """Attach Internet Gateway to VPC - creates REAL OCI IGW"""
    igw_id = params.get('InternetGatewayId')
    vpc_id = params.get('VpcId')

    igw = db.query(MockInternetGateway).filter(
        MockInternetGateway.environment_id == environment.id,
        MockInternetGateway.id == igw_id
    ).first()

    vpc = db.query(MockVPC).filter(
        MockVPC.environment_id == environment.id,
        MockVPC.id == vpc_id
    ).first()

    if not igw or not vpc:
        raise HTTPException(status_code=404, detail="IGW or VPC not found")

    try:
        # Create REAL OCI Internet Gateway
        oci_service = get_oci_network_service()
        oci_igw = oci_service.create_internet_gateway(
            vcn_id=vpc.oci_vcn_id,
            display_name=f"mock-aws-igw-{igw_id}"
        )

        # Update database
        igw.vpc_id = vpc_id
        igw.state = "attached"
        igw.oci_internet_gateway_id = oci_igw["igw_id"]

        vpc.oci_internet_gateway_id = oci_igw["igw_id"]

        db.commit()

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachInternetGatewayResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <return>true</return>
</AttachInternetGatewayResponse>"""

        return Response(content=xml_response, media_type="application/xml")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error attaching IGW: {str(e)}")
