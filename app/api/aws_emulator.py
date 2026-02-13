"""
AWS API Emulator
Emulates AWS EC2, S3, Lambda, RDS APIs
Translates requests to MockFactory infrastructure
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Response
from sqlalchemy.orm import Session
from typing import Optional
import json
import uuid
import hashlib
from datetime import datetime

from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.models.cloud_resources import (
    MockEC2Instance, MockS3Bucket, MockS3Object,
    MockLambdaFunction, MockRDSInstance, ResourceStatus
)

router = APIRouter()


def get_environment_from_request(request: Request, db: Session) -> Environment:
    """
    Extract environment from request
    Supports subdomain (env-123.mockfactory.io) or header (X-Mock-Environment-ID)
    """
    # Try subdomain first
    host = request.headers.get("host", "")
    if "env-" in host:
        env_id = host.split(".")[0]
    else:
        # Try header
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
# AWS EC2 Emulation
# ============================================================================

@router.post("/aws/ec2")
async def aws_ec2_api(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    AWS EC2 API Endpoint
    Handles RunInstances, DescribeInstances, TerminateInstances, etc.
    """
    environment = get_environment_from_request(request, db)
    body = await request.body()

    # Parse AWS query string format
    params = {}
    if body:
        params = dict(x.split('=') for x in body.decode().split('&'))

    action = params.get('Action', request.query_params.get('Action'))

    if action == 'RunInstances':
        return await ec2_run_instances(environment, params, db)
    elif action == 'DescribeInstances':
        return await ec2_describe_instances(environment, params, db)
    elif action == 'TerminateInstances':
        return await ec2_terminate_instances(environment, params, db)
    elif action == 'StopInstances':
        return await ec2_stop_instances(environment, params, db)
    elif action == 'StartInstances':
        return await ec2_start_instances(environment, params, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")


async def ec2_run_instances(environment: Environment, params: dict, db: Session):
    """Launch new EC2 instance(s)"""
    instance_type = params.get('InstanceType', 't2.micro')
    ami_id = params.get('ImageId', 'ami-mock-ubuntu')
    min_count = int(params.get('MinCount', 1))
    max_count = int(params.get('MaxCount', 1))

    instances = []
    for _ in range(min_count):
        instance_id = f"i-{uuid.uuid4().hex[:17]}"
        private_ip = f"10.0.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"

        instance = MockEC2Instance(
            id=instance_id,
            environment_id=environment.id,
            instance_type=instance_type,
            ami_id=ami_id,
            state=ResourceStatus.RUNNING,
            private_ip=private_ip,
            public_ip=f"54.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"
        )

        db.add(instance)
        instances.append(instance)

    db.commit()

    # Return AWS-style XML response
    instances_xml = ""
    for inst in instances:
        instances_xml += f"""
        <item>
            <instanceId>{inst.id}</instanceId>
            <imageId>{inst.ami_id}</imageId>
            <instanceState>
                <code>16</code>
                <name>running</name>
            </instanceState>
            <privateDnsName>ip-{inst.private_ip.replace('.', '-')}.ec2.internal</privateDnsName>
            <dnsName>{inst.public_ip}</dnsName>
            <privateIpAddress>{inst.private_ip}</privateIpAddress>
            <ipAddress>{inst.public_ip}</ipAddress>
            <instanceType>{inst.instance_type}</instanceType>
            <launchTime>{inst.launch_time.isoformat()}Z</launchTime>
        </item>
        """

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<RunInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <reservationId>r-{uuid.uuid4().hex[:17]}</reservationId>
    <ownerId>123456789012</ownerId>
    <instancesSet>
        {instances_xml}
    </instancesSet>
</RunInstancesResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def ec2_describe_instances(environment: Environment, params: dict, db: Session):
    """Describe EC2 instances"""
    instances = db.query(MockEC2Instance).filter(
        MockEC2Instance.environment_id == environment.id
    ).all()

    instances_xml = ""
    for inst in instances:
        state_name = inst.state.value if inst.state != ResourceStatus.TERMINATED else "terminated"
        instances_xml += f"""
        <item>
            <instanceId>{inst.id}</instanceId>
            <imageId>{inst.ami_id}</imageId>
            <instanceState>
                <name>{state_name}</name>
            </instanceState>
            <privateDnsName>ip-{inst.private_ip.replace('.', '-')}.ec2.internal</privateDnsName>
            <privateIpAddress>{inst.private_ip}</privateIpAddress>
            <ipAddress>{inst.public_ip}</ipAddress>
            <instanceType>{inst.instance_type}</instanceType>
            <launchTime>{inst.launch_time.isoformat()}Z</launchTime>
        </item>
        """

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<DescribeInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <reservationSet>
        <item>
            <reservationId>r-{uuid.uuid4().hex[:17]}</reservationId>
            <ownerId>123456789012</ownerId>
            <instancesSet>
                {instances_xml}
            </instancesSet>
        </item>
    </reservationSet>
</DescribeInstancesResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def ec2_terminate_instances(environment: Environment, params: dict, db: Session):
    """Terminate EC2 instances"""
    # Parse instance IDs from params
    instance_ids = [v for k, v in params.items() if k.startswith('InstanceId.')]

    instances = db.query(MockEC2Instance).filter(
        MockEC2Instance.environment_id == environment.id,
        MockEC2Instance.id.in_(instance_ids)
    ).all()

    for inst in instances:
        inst.state = ResourceStatus.TERMINATED
        inst.terminated_time = datetime.utcnow()

    db.commit()

    instances_xml = "".join([
        f'<item><instanceId>{inst.id}</instanceId><currentState><name>terminated</name></currentState></item>'
        for inst in instances
    ])

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<TerminateInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <instancesSet>{instances_xml}</instancesSet>
</TerminateInstancesResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def ec2_stop_instances(environment: Environment, params: dict, db: Session):
    """Stop EC2 instances"""
    instance_ids = [v for k, v in params.items() if k.startswith('InstanceId.')]

    instances = db.query(MockEC2Instance).filter(
        MockEC2Instance.environment_id == environment.id,
        MockEC2Instance.id.in_(instance_ids)
    ).all()

    for inst in instances:
        inst.state = ResourceStatus.STOPPED

    db.commit()

    instances_xml = "".join([
        f'<item><instanceId>{inst.id}</instanceId><currentState><name>stopped</name></currentState></item>'
        for inst in instances
    ])

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<StopInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <instancesSet>{instances_xml}</instancesSet>
</StopInstancesResponse>"""

    return Response(content=xml_response, media_type="application/xml")


async def ec2_start_instances(environment: Environment, params: dict, db: Session):
    """Start stopped EC2 instances"""
    instance_ids = [v for k, v in params.items() if k.startswith('InstanceId.')]

    instances = db.query(MockEC2Instance).filter(
        MockEC2Instance.environment_id == environment.id,
        MockEC2Instance.id.in_(instance_ids),
        MockEC2Instance.state == ResourceStatus.STOPPED
    ).all()

    for inst in instances:
        inst.state = ResourceStatus.RUNNING

    db.commit()

    instances_xml = "".join([
        f'<item><instanceId>{inst.id}</instanceId><currentState><name>running</name></currentState></item>'
        for inst in instances
    ])

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<StartInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>{uuid.uuid4()}</requestId>
    <instancesSet>{instances_xml}</instancesSet>
</StartInstancesResponse>"""

    return Response(content=xml_response, media_type="application/xml")


# ============================================================================
# AWS S3 Emulation
# ============================================================================

@router.api_route("/aws/s3/{bucket_name}/{path:path}", methods=["GET", "PUT", "DELETE", "HEAD"])
@router.api_route("/aws/s3/{bucket_name}", methods=["GET", "PUT", "DELETE", "HEAD"])
@router.api_route("/aws/s3/", methods=["GET"])
async def aws_s3_api(
    request: Request,
    bucket_name: Optional[str] = None,
    path: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    AWS S3 API Endpoint
    Handles bucket and object operations
    """
    environment = get_environment_from_request(request, db)

    if request.method == "GET" and not bucket_name:
        # List buckets
        return await s3_list_buckets(environment, db)
    elif request.method == "PUT" and bucket_name and not path:
        # Create bucket
        return await s3_create_bucket(environment, bucket_name, db)
    elif request.method == "PUT" and bucket_name and path:
        # Put object
        return await s3_put_object(environment, bucket_name, path, request, db)
    elif request.method == "GET" and bucket_name and path:
        # Get object
        return await s3_get_object(environment, bucket_name, path, db)
    elif request.method == "DELETE" and bucket_name and path:
        # Delete object
        return await s3_delete_object(environment, bucket_name, path, db)
    elif request.method == "GET" and bucket_name:
        # List objects
        return await s3_list_objects(environment, bucket_name, db)
    else:
        raise HTTPException(status_code=400, detail="Unsupported S3 operation")


async def s3_list_buckets(environment: Environment, db: Session):
    """List all S3 buckets"""
    buckets = db.query(MockS3Bucket).filter(
        MockS3Bucket.environment_id == environment.id
    ).all()

    buckets_xml = "".join([
        f'<Bucket><Name>{b.bucket_name}</Name><CreationDate>{b.created_at.isoformat()}Z</CreationDate></Bucket>'
        for b in buckets
    ])

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
    <Owner><ID>123456789012</ID><DisplayName>mock-user</DisplayName></Owner>
    <Buckets>{buckets_xml}</Buckets>
</ListAllMyBucketsResult>"""

    return Response(content=xml_response, media_type="application/xml")


async def s3_create_bucket(environment: Environment, bucket_name: str, db: Session):
    """Create S3 bucket"""
    # Check if bucket exists
    existing = db.query(MockS3Bucket).filter(
        MockS3Bucket.bucket_name == bucket_name
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="BucketAlreadyExists")

    bucket = MockS3Bucket(
        environment_id=environment.id,
        bucket_name=bucket_name
    )

    db.add(bucket)
    db.commit()

    return Response(status_code=200)


async def s3_put_object(environment: Environment, bucket_name: str, key: str, request: Request, db: Session):
    """Upload object to S3"""
    bucket = db.query(MockS3Bucket).filter(
        MockS3Bucket.environment_id == environment.id,
        MockS3Bucket.bucket_name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    # Read object data
    data = await request.body()
    etag = hashlib.md5(data).hexdigest()

    # Check if object exists (update)
    obj = db.query(MockS3Object).filter(
        MockS3Object.bucket_id == bucket.id,
        MockS3Object.key == key
    ).first()

    if obj:
        obj.size_bytes = len(data)
        obj.etag = etag
        obj.last_modified = datetime.utcnow()
    else:
        obj = MockS3Object(
            bucket_id=bucket.id,
            key=key,
            size_bytes=len(data),
            etag=etag,
            content_type=request.headers.get("Content-Type", "application/octet-stream")
        )
        db.add(obj)
        bucket.total_objects += 1

    bucket.total_size_bytes += len(data)
    db.commit()

    return Response(status_code=200, headers={"ETag": f'"{etag}"'})


async def s3_get_object(environment: Environment, bucket_name: str, key: str, db: Session):
    """Get object from S3"""
    bucket = db.query(MockS3Bucket).filter(
        MockS3Bucket.environment_id == environment.id,
        MockS3Bucket.bucket_name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    obj = db.query(MockS3Object).filter(
        MockS3Object.bucket_id == bucket.id,
        MockS3Object.key == key
    ).first()

    if not obj:
        raise HTTPException(status_code=404, detail="NoSuchKey")

    # Return mock data
    mock_data = b"Mock S3 object data"

    return Response(
        content=mock_data,
        media_type=obj.content_type or "application/octet-stream",
        headers={"ETag": f'"{obj.etag}"'}
    )


async def s3_delete_object(environment: Environment, bucket_name: str, key: str, db: Session):
    """Delete object from S3"""
    bucket = db.query(MockS3Bucket).filter(
        MockS3Bucket.environment_id == environment.id,
        MockS3Bucket.bucket_name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    obj = db.query(MockS3Object).filter(
        MockS3Object.bucket_id == bucket.id,
        MockS3Object.key == key
    ).first()

    if obj:
        bucket.total_objects -= 1
        bucket.total_size_bytes -= obj.size_bytes
        db.delete(obj)
        db.commit()

    return Response(status_code=204)


async def s3_list_objects(environment: Environment, bucket_name: str, db: Session):
    """List objects in bucket"""
    bucket = db.query(MockS3Bucket).filter(
        MockS3Bucket.environment_id == environment.id,
        MockS3Bucket.bucket_name == bucket_name
    ).first()

    if not bucket:
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    objects = db.query(MockS3Object).filter(
        MockS3Object.bucket_id == bucket.id
    ).all()

    objects_xml = "".join([
        f'''<Contents>
            <Key>{obj.key}</Key>
            <LastModified>{obj.last_modified.isoformat()}Z</LastModified>
            <ETag>"{obj.etag}"</ETag>
            <Size>{obj.size_bytes}</Size>
            <StorageClass>STANDARD</StorageClass>
        </Contents>'''
        for obj in objects
    ])

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
    <Name>{bucket_name}</Name>
    <MaxKeys>1000</MaxKeys>
    <IsTruncated>false</IsTruncated>
    {objects_xml}
</ListBucketResult>"""

    return Response(content=xml_response, media_type="application/xml")
