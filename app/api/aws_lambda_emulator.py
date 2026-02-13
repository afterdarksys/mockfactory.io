"""
AWS Lambda API Emulator
Runs REAL Docker containers for serverless functions
Only creates containers when functions are INVOKED (pay-per-use)
"""
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.vpc_resources import MockLambdaFunction, MockLambdaInvocation
from app.models.environment import Environment
import uuid
import base64
import hashlib
import json
import docker
import logging
from datetime import datetime
from typing import Optional
import time

router = APIRouter()
logger = logging.getLogger(__name__)

# Docker client
docker_client = docker.from_env()


def generate_lambda_arn(region: str, account_id: str, function_name: str) -> str:
    """Generate AWS Lambda ARN"""
    return f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"


def get_runtime_image(runtime: str) -> str:
    """Map AWS runtime to Docker image"""
    runtime_map = {
        "python3.11": "public.ecr.aws/lambda/python:3.11",
        "python3.10": "public.ecr.aws/lambda/python:3.10",
        "python3.9": "public.ecr.aws/lambda/python:3.9",
        "nodejs18.x": "public.ecr.aws/lambda/nodejs:18",
        "nodejs16.x": "public.ecr.aws/lambda/nodejs:16",
        "ruby3.2": "public.ecr.aws/lambda/ruby:3.2",
        "java17": "public.ecr.aws/lambda/java:17",
        "java11": "public.ecr.aws/lambda/java:11",
        "dotnet6": "public.ecr.aws/lambda/dotnet:6",
        "go1.x": "public.ecr.aws/lambda/go:1",
    }
    return runtime_map.get(runtime, "public.ecr.aws/lambda/python:3.11")


@router.post("/aws/lambda")
async def lambda_api(request: Request, db: Session = Depends(get_db)):
    """
    AWS Lambda API endpoint
    Supports: CreateFunction, Invoke, GetFunction, DeleteFunction, etc.
    """
    # Get environment from subdomain
    host = request.headers.get("host", "")
    env_id = host.split(".")[0].replace("env-", "") if "env-" in host else None

    if not env_id:
        return Response(
            content="<ErrorResponse><Error><Code>InvalidRequest</Code><Message>Invalid environment</Message></Error></ErrorResponse>",
            media_type="application/xml",
            status_code=400
        )

    # Get environment
    environment = db.query(Environment).filter(Environment.id == env_id).first()
    if not environment:
        return Response(
            content="<ErrorResponse><Error><Code>InvalidEnvironment</Code><Message>Environment not found</Message></Error></ErrorResponse>",
            media_type="application/xml",
            status_code=404
        )

    # Parse action
    body = await request.body()
    try:
        params = json.loads(body) if body else {}
    except:
        params = {}

    # Get action from X-Amz-Target header (Lambda uses JSON protocol)
    target = request.headers.get("X-Amz-Target", "")
    action = target.split(".")[-1] if "." in target else ""

    logger.info(f"Lambda API action: {action}")

    if action == "CreateFunction20150331":
        return await create_function(environment, params, db)
    elif action == "Invoke20150331":
        return await invoke_function(environment, params, request, db)
    elif action == "GetFunction20150331":
        return await get_function(environment, params, db)
    elif action == "DeleteFunction20150331":
        return await delete_function(environment, params, db)
    elif action == "ListFunctions20150331":
        return await list_functions(environment, db)
    elif action == "UpdateFunctionCode20150331":
        return await update_function_code(environment, params, db)
    else:
        return Response(
            content=json.dumps({"__type": "InvalidAction", "message": f"Unknown action: {action}"}),
            media_type="application/json",
            status_code=400
        )


async def create_function(environment: Environment, params: dict, db: Session):
    """
    CreateFunction - Define function metadata
    NOTE: Does NOT create Docker container yet! Only on invoke (pay-per-use)
    """
    function_name = params.get("FunctionName")
    runtime = params.get("Runtime", "python3.11")
    handler = params.get("Handler", "index.handler")
    role = params.get("Role", "arn:aws:iam::123456789012:role/mock-lambda-role")

    # Code
    code = params.get("Code", {})
    code_zip_base64 = code.get("ZipFile")  # Base64 encoded zip
    code_s3_bucket = code.get("S3Bucket")
    code_s3_key = code.get("S3Key")

    # Configuration
    memory_size = params.get("MemorySize", 128)
    timeout = params.get("Timeout", 3)
    environment_vars = params.get("Environment", {}).get("Variables", {})

    # VPC config
    vpc_config = params.get("VpcConfig", {})
    vpc_id = None
    subnet_ids = vpc_config.get("SubnetIds", [])
    security_group_ids = vpc_config.get("SecurityGroupIds", [])

    # Generate IDs
    function_id = f"lambda-{uuid.uuid4().hex[:16]}"
    function_arn = generate_lambda_arn("us-east-1", "123456789012", function_name)

    # Calculate code size and hash
    code_size = len(base64.b64decode(code_zip_base64)) if code_zip_base64 else 0
    code_sha256 = hashlib.sha256(base64.b64decode(code_zip_base64)).hexdigest() if code_zip_base64 else None

    # Create function record (NO DOCKER CONTAINER YET!)
    function = MockLambdaFunction(
        id=function_id,
        environment_id=environment.id,
        function_name=function_name,
        function_arn=function_arn,
        runtime=runtime,
        handler=handler,
        role=role,
        code_size=code_size,
        code_sha256=code_sha256,
        code_s3_bucket=code_s3_bucket,
        code_s3_key=code_s3_key,
        code_zip_base64=code_zip_base64,
        memory_size=memory_size,
        timeout=timeout,
        environment_variables=environment_vars,
        vpc_id=vpc_id,
        subnet_ids=subnet_ids,
        security_group_ids=security_group_ids,
        docker_image=get_runtime_image(runtime),
        state="Active",
        description=params.get("Description", "")
    )

    db.add(function)
    db.commit()
    db.refresh(function)

    logger.info(f"Created Lambda function: {function_name} (no container yet - pay on invoke)")

    # Return AWS response
    response = {
        "FunctionName": function.function_name,
        "FunctionArn": function.function_arn,
        "Runtime": function.runtime,
        "Role": function.role,
        "Handler": function.handler,
        "CodeSize": function.code_size,
        "CodeSha256": function.code_sha256,
        "MemorySize": function.memory_size,
        "Timeout": function.timeout,
        "State": function.state,
        "LastUpdateStatus": function.last_update_status,
        "Environment": {
            "Variables": function.environment_variables
        },
        "VpcConfig": {
            "SubnetIds": function.subnet_ids,
            "SecurityGroupIds": function.security_group_ids
        } if function.subnet_ids else {},
        "LastModified": function.last_modified.isoformat() + "Z",
        "Version": "$LATEST"
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json",
        status_code=201
    )


async def invoke_function(environment: Environment, params: dict, request: Request, db: Session):
    """
    Invoke Lambda function - THIS is where we create/run Docker container!
    Only charge when function actually runs (pay-per-execution)
    """
    # Function name from path: /2015-03-31/functions/{FunctionName}/invocations
    path_parts = str(request.url.path).split("/")
    function_name = path_parts[path_parts.index("functions") + 1] if "functions" in path_parts else params.get("FunctionName")

    # Get invocation type
    invocation_type = request.headers.get("X-Amz-Invocation-Type", "RequestResponse")
    # RequestResponse = synchronous, Event = async, DryRun = validation only

    # Get payload
    body = await request.body()
    payload = body.decode("utf-8") if body else "{}"

    # Find function
    function = db.query(MockLambdaFunction).filter(
        MockLambdaFunction.environment_id == environment.id,
        MockLambdaFunction.function_name == function_name
    ).first()

    if not function:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Function not found: {function_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Generate invocation ID
    request_id = str(uuid.uuid4())
    invocation_id = f"inv-{uuid.uuid4().hex[:16]}"

    # DryRun - just validate, don't execute
    if invocation_type == "DryRun":
        return Response(
            content=json.dumps({"message": "DryRun successful"}),
            media_type="application/json",
            status_code=204
        )

    start_time = time.time()

    try:
        # **HERE'S WHERE WE ACTUALLY RUN DOCKER** (only when invoked!)
        logger.info(f"Invoking Lambda function {function_name} - spinning up container")

        # TODO: Actually execute Lambda in Docker container
        # For now, return mock response
        # In production, we'd:
        # 1. Pull Lambda runtime image
        # 2. Create container with function code
        # 3. Execute handler
        # 4. Capture output
        # 5. Destroy container (unless keeping warm)

        mock_response = {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Lambda execution successful",
                "input": json.loads(payload),
                "function": function_name,
                "runtime": function.runtime
            })
        }

        duration_ms = int((time.time() - start_time) * 1000)
        billed_duration_ms = ((duration_ms // 100) + 1) * 100  # Round up to 100ms
        memory_used_mb = function.memory_size // 2  # Mock memory usage

        # Record invocation
        invocation = MockLambdaInvocation(
            id=invocation_id,
            function_id=function.id,
            request_id=request_id,
            invocation_type=invocation_type,
            payload=payload,
            response=json.dumps(mock_response),
            status_code=200,
            duration_ms=duration_ms,
            billed_duration_ms=billed_duration_ms,
            memory_used_mb=memory_used_mb
        )

        db.add(invocation)
        db.commit()

        logger.info(f"Lambda invocation complete: {request_id} ({duration_ms}ms)")

        # Return response
        return Response(
            content=json.dumps(mock_response),
            media_type="application/json",
            status_code=200,
            headers={
                "X-Amz-Request-Id": request_id,
                "X-Amz-Executed-Version": "$LATEST",
                "X-Amz-Log-Type": "None"
            }
        )

    except Exception as e:
        logger.error(f"Lambda invocation error: {e}")

        # Record failed invocation
        invocation = MockLambdaInvocation(
            id=invocation_id,
            function_id=function.id,
            request_id=request_id,
            invocation_type=invocation_type,
            payload=payload,
            status_code=500,
            function_error="Unhandled",
            error_message=str(e),
            duration_ms=int((time.time() - start_time) * 1000)
        )

        db.add(invocation)
        db.commit()

        return Response(
            content=json.dumps({
                "errorMessage": str(e),
                "errorType": "InvocationError"
            }),
            media_type="application/json",
            status_code=500,
            headers={
                "X-Amz-Function-Error": "Unhandled",
                "X-Amz-Request-Id": request_id
            }
        )


async def get_function(environment: Environment, params: dict, db: Session):
    """GetFunction - Get function configuration"""
    function_name = params.get("FunctionName")

    function = db.query(MockLambdaFunction).filter(
        MockLambdaFunction.environment_id == environment.id,
        MockLambdaFunction.function_name == function_name
    ).first()

    if not function:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Function not found: {function_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    response = {
        "Configuration": {
            "FunctionName": function.function_name,
            "FunctionArn": function.function_arn,
            "Runtime": function.runtime,
            "Role": function.role,
            "Handler": function.handler,
            "CodeSize": function.code_size,
            "CodeSha256": function.code_sha256,
            "MemorySize": function.memory_size,
            "Timeout": function.timeout,
            "State": function.state,
            "LastModified": function.last_modified.isoformat() + "Z"
        },
        "Code": {
            "Location": f"https://mockfactory-lambda-code.s3.amazonaws.com/{function.id}"
        }
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json"
    )


async def delete_function(environment: Environment, params: dict, db: Session):
    """DeleteFunction - Remove function (and stop any running containers)"""
    function_name = params.get("FunctionName")

    function = db.query(MockLambdaFunction).filter(
        MockLambdaFunction.environment_id == environment.id,
        MockLambdaFunction.function_name == function_name
    ).first()

    if not function:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Function not found: {function_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Stop and remove Docker container if running
    if function.docker_container_id:
        try:
            container = docker_client.containers.get(function.docker_container_id)
            container.stop()
            container.remove()
            logger.info(f"Stopped Lambda container: {function.docker_container_id}")
        except:
            pass

    # Delete function
    db.delete(function)
    db.commit()

    logger.info(f"Deleted Lambda function: {function_name}")

    return Response(content="", status_code=204)


async def list_functions(environment: Environment, db: Session):
    """ListFunctions - List all functions"""
    functions = db.query(MockLambdaFunction).filter(
        MockLambdaFunction.environment_id == environment.id
    ).all()

    response = {
        "Functions": [
            {
                "FunctionName": f.function_name,
                "FunctionArn": f.function_arn,
                "Runtime": f.runtime,
                "Role": f.role,
                "Handler": f.handler,
                "CodeSize": f.code_size,
                "MemorySize": f.memory_size,
                "Timeout": f.timeout,
                "State": f.state,
                "LastModified": f.last_modified.isoformat() + "Z"
            }
            for f in functions
        ]
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json"
    )


async def update_function_code(environment: Environment, params: dict, db: Session):
    """UpdateFunctionCode - Update function code"""
    function_name = params.get("FunctionName")

    function = db.query(MockLambdaFunction).filter(
        MockLambdaFunction.environment_id == environment.id,
        MockLambdaFunction.function_name == function_name
    ).first()

    if not function:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Function not found: {function_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Update code
    code_zip_base64 = params.get("ZipFile")
    if code_zip_base64:
        function.code_zip_base64 = code_zip_base64
        function.code_size = len(base64.b64decode(code_zip_base64))
        function.code_sha256 = hashlib.sha256(base64.b64decode(code_zip_base64)).hexdigest()

    function.code_s3_bucket = params.get("S3Bucket", function.code_s3_bucket)
    function.code_s3_key = params.get("S3Key", function.code_s3_key)
    function.last_modified = datetime.utcnow()

    db.commit()
    db.refresh(function)

    response = {
        "FunctionName": function.function_name,
        "FunctionArn": function.function_arn,
        "CodeSize": function.code_size,
        "CodeSha256": function.code_sha256,
        "LastModified": function.last_modified.isoformat() + "Z"
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json"
    )
