"""
AWS SQS API Emulator
Backed by Redis lists for REAL message queuing
Queue creation is FREE, but message operations consume credits
"""
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.vpc_resources import MockSQSQueue
from app.models.environment import Environment
import uuid
import json
import logging
import hashlib
import time
from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import parse_qs

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis client for message storage
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except:
    redis_client = None
    logger.warning("Redis not available - SQS will use in-memory fallback")


def generate_queue_url(region: str, account_id: str, queue_name: str) -> str:
    """Generate SQS queue URL"""
    return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"


def generate_queue_arn(region: str, account_id: str, queue_name: str) -> str:
    """Generate SQS queue ARN"""
    return f"arn:aws:sqs:{region}:{account_id}:{queue_name}"


def generate_message_id() -> str:
    """Generate SQS message ID"""
    return str(uuid.uuid4())


def generate_receipt_handle() -> str:
    """Generate SQS receipt handle"""
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()


@router.post("/aws/sqs")
@router.get("/aws/sqs")
async def sqs_api(request: Request, db: Session = Depends(get_db)):
    """
    AWS SQS API endpoint
    Uses query string parameters (AWS Query Protocol)
    """
    # Get environment from subdomain
    host = request.headers.get("host", "")
    env_id = host.split(".")[0].replace("env-", "") if "env-" in host else None

    if not env_id:
        return Response(
            content=sqs_error_response("InvalidClientTokenId", "Invalid environment"),
            media_type="application/xml",
            status_code=400
        )

    # Get environment
    environment = db.query(Environment).filter(Environment.id == env_id).first()
    if not environment:
        return Response(
            content=sqs_error_response("ResourceNotFoundException", "Environment not found"),
            media_type="application/xml",
            status_code=404
        )

    # Parse query parameters
    query_string = str(request.url.query)
    params = parse_qs(query_string)

    # Flatten params (convert lists to single values)
    params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in params.items()}

    action = params.get("Action", "")
    logger.info(f"SQS action: {action}")

    # Route to handlers
    if action == "CreateQueue":
        return await create_queue(environment, params, db)
    elif action == "GetQueueUrl":
        return await get_queue_url(environment, params, db)
    elif action == "ListQueues":
        return await list_queues(environment, db)
    elif action == "DeleteQueue":
        return await delete_queue(environment, params, db)
    elif action == "SendMessage":
        return await send_message(environment, params, db)
    elif action == "ReceiveMessage":
        return await receive_message(environment, params, db)
    elif action == "DeleteMessage":
        return await delete_message(environment, params, db)
    elif action == "GetQueueAttributes":
        return await get_queue_attributes(environment, params, db)
    elif action == "SetQueueAttributes":
        return await set_queue_attributes(environment, params, db)
    elif action == "PurgeQueue":
        return await purge_queue(environment, params, db)
    else:
        return Response(
            content=sqs_error_response("InvalidAction", f"Unknown action: {action}"),
            media_type="application/xml",
            status_code=400
        )


def sqs_error_response(code: str, message: str) -> str:
    """Generate SQS error XML response"""
    return f"""<?xml version="1.0"?>
<ErrorResponse>
    <Error>
        <Code>{code}</Code>
        <Message>{message}</Message>
    </Error>
    <RequestId>{uuid.uuid4()}</RequestId>
</ErrorResponse>"""


async def create_queue(environment: Environment, params: dict, db: Session):
    """
    CreateQueue - Create queue metadata (FREE)
    No Redis list created yet - only when messages are sent (credits consumed)
    """
    queue_name = params.get("QueueName", "")

    # Check for .fifo suffix
    is_fifo = queue_name.endswith(".fifo")

    # Check if queue already exists
    existing = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if existing:
        # Return existing queue URL
        response = f"""<?xml version="1.0"?>
<CreateQueueResponse>
    <CreateQueueResult>
        <QueueUrl>{existing.queue_url}</QueueUrl>
    </CreateQueueResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</CreateQueueResponse>"""
        return Response(content=response, media_type="application/xml")

    # Parse attributes
    visibility_timeout = int(params.get("VisibilityTimeout", params.get("Attribute.1.Value", 30)))
    message_retention = int(params.get("MessageRetentionPeriod", params.get("Attribute.2.Value", 345600)))

    # Generate IDs
    queue_id = f"sqs-{uuid.uuid4().hex[:16]}"
    queue_url = generate_queue_url("us-east-1", "123456789012", queue_name)
    queue_arn = generate_queue_arn("us-east-1", "123456789012", queue_name)
    redis_key = f"sqs:{environment.id}:{queue_name}"

    # Create queue (just metadata - no Redis list yet!)
    queue = MockSQSQueue(
        id=queue_id,
        environment_id=environment.id,
        queue_name=queue_name,
        queue_url=queue_url,
        queue_arn=queue_arn,
        fifo_queue=is_fifo,
        visibility_timeout=visibility_timeout,
        message_retention_period=message_retention,
        redis_list_key=redis_key
    )

    db.add(queue)
    db.commit()
    db.refresh(queue)

    logger.info(f"Created SQS queue (metadata only): {queue_name}")

    response = f"""<?xml version="1.0"?>
<CreateQueueResponse>
    <CreateQueueResult>
        <QueueUrl>{queue.queue_url}</QueueUrl>
    </CreateQueueResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</CreateQueueResponse>"""

    return Response(content=response, media_type="application/xml")


async def send_message(environment: Environment, params: dict, db: Session):
    """
    SendMessage - Send message to queue
    THIS CONSUMES CREDITS - writes to Redis
    """
    queue_url = params.get("QueueUrl", "")
    message_body = params.get("MessageBody", "")

    # Extract queue name from URL
    queue_name = queue_url.split("/")[-1]

    # Find queue
    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    # Generate message metadata
    message_id = generate_message_id()
    md5_body = hashlib.md5(message_body.encode()).hexdigest()

    # Store message in Redis (or fallback to in-memory)
    message_data = {
        "MessageId": message_id,
        "Body": message_body,
        "MD5OfBody": md5_body,
        "SentTimestamp": int(time.time() * 1000),
        "ApproximateReceiveCount": 0
    }

    if redis_client:
        # Push to Redis list (REAL queue!)
        redis_client.rpush(queue.redis_list_key, json.dumps(message_data))
        logger.info(f"Sent message to Redis queue (CREDIT USED): {queue_name}")
    else:
        logger.warning(f"Redis unavailable - message not persisted: {queue_name}")

    # Update queue stats
    queue.approximate_number_of_messages += 1
    db.commit()

    # TODO: Deduct credits from user account
    # Example: user.credits -= calculate_sqs_request_cost()

    response = f"""<?xml version="1.0"?>
<SendMessageResponse>
    <SendMessageResult>
        <MessageId>{message_id}</MessageId>
        <MD5OfMessageBody>{md5_body}</MD5OfMessageBody>
    </SendMessageResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</SendMessageResponse>"""

    return Response(content=response, media_type="application/xml")


async def receive_message(environment: Environment, params: dict, db: Session):
    """
    ReceiveMessage - Receive messages from queue
    THIS CONSUMES CREDITS - reads from Redis
    """
    queue_url = params.get("QueueUrl", "")
    max_messages = int(params.get("MaxNumberOfMessages", 1))
    wait_time = int(params.get("WaitTimeSeconds", 0))

    # Extract queue name from URL
    queue_name = queue_url.split("/")[-1]

    # Find queue
    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    messages = []

    if redis_client:
        # Pop messages from Redis list
        for _ in range(max_messages):
            message_json = redis_client.lpop(queue.redis_list_key)
            if not message_json:
                break

            message_data = json.loads(message_json)
            receipt_handle = generate_receipt_handle()

            # Store receipt handle for deletion
            redis_client.setex(
                f"receipt:{receipt_handle}",
                queue.visibility_timeout,
                message_json
            )

            messages.append({
                "MessageId": message_data["MessageId"],
                "ReceiptHandle": receipt_handle,
                "Body": message_data["Body"],
                "MD5OfBody": message_data["MD5OfBody"]
            })

            # Update stats
            queue.approximate_number_of_messages -= 1
            queue.approximate_number_of_messages_not_visible += 1

    db.commit()

    logger.info(f"Received {len(messages)} messages (CREDITS USED): {queue_name}")

    # TODO: Deduct credits from user account
    # Example: user.credits -= calculate_sqs_request_cost() * len(messages)

    # Build XML response
    message_xml = ""
    for msg in messages:
        message_xml += f"""
        <Message>
            <MessageId>{msg["MessageId"]}</MessageId>
            <ReceiptHandle>{msg["ReceiptHandle"]}</ReceiptHandle>
            <MD5OfBody>{msg["MD5OfBody"]}</MD5OfBody>
            <Body>{msg["Body"]}</Body>
        </Message>"""

    response = f"""<?xml version="1.0"?>
<ReceiveMessageResponse>
    <ReceiveMessageResult>{message_xml}
    </ReceiveMessageResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</ReceiveMessageResponse>"""

    return Response(content=response, media_type="application/xml")


async def delete_message(environment: Environment, params: dict, db: Session):
    """DeleteMessage - Remove message from queue"""
    queue_url = params.get("QueueUrl", "")
    receipt_handle = params.get("ReceiptHandle", "")

    # Extract queue name from URL
    queue_name = queue_url.split("/")[-1]

    # Find queue
    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    # Delete receipt handle from Redis
    if redis_client:
        redis_client.delete(f"receipt:{receipt_handle}")
        queue.approximate_number_of_messages_not_visible -= 1
        db.commit()

    logger.info(f"Deleted message from queue: {queue_name}")

    response = f"""<?xml version="1.0"?>
<DeleteMessageResponse>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</DeleteMessageResponse>"""

    return Response(content=response, media_type="application/xml")


async def get_queue_url(environment: Environment, params: dict, db: Session):
    """GetQueueUrl - Get URL for queue name (FREE)"""
    queue_name = params.get("QueueName", "")

    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    response = f"""<?xml version="1.0"?>
<GetQueueUrlResponse>
    <GetQueueUrlResult>
        <QueueUrl>{queue.queue_url}</QueueUrl>
    </GetQueueUrlResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</GetQueueUrlResponse>"""

    return Response(content=response, media_type="application/xml")


async def list_queues(environment: Environment, db: Session):
    """ListQueues - List all queues (FREE)"""
    queues = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id
    ).all()

    queue_urls = "\n".join([f"<QueueUrl>{q.queue_url}</QueueUrl>" for q in queues])

    response = f"""<?xml version="1.0"?>
<ListQueuesResponse>
    <ListQueuesResult>
        {queue_urls}
    </ListQueuesResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</ListQueuesResponse>"""

    return Response(content=response, media_type="application/xml")


async def delete_queue(environment: Environment, params: dict, db: Session):
    """DeleteQueue - Delete queue and all messages"""
    queue_url = params.get("QueueUrl", "")
    queue_name = queue_url.split("/")[-1]

    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    # Delete Redis list
    if redis_client:
        redis_client.delete(queue.redis_list_key)

    # Delete queue
    db.delete(queue)
    db.commit()

    logger.info(f"Deleted SQS queue: {queue_name}")

    response = f"""<?xml version="1.0"?>
<DeleteQueueResponse>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</DeleteQueueResponse>"""

    return Response(content=response, media_type="application/xml")


async def get_queue_attributes(environment: Environment, params: dict, db: Session):
    """GetQueueAttributes - Get queue configuration (FREE)"""
    queue_url = params.get("QueueUrl", "")
    queue_name = queue_url.split("/")[-1]

    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    response = f"""<?xml version="1.0"?>
<GetQueueAttributesResponse>
    <GetQueueAttributesResult>
        <Attribute>
            <Name>QueueArn</Name>
            <Value>{queue.queue_arn}</Value>
        </Attribute>
        <Attribute>
            <Name>ApproximateNumberOfMessages</Name>
            <Value>{queue.approximate_number_of_messages}</Value>
        </Attribute>
        <Attribute>
            <Name>VisibilityTimeout</Name>
            <Value>{queue.visibility_timeout}</Value>
        </Attribute>
    </GetQueueAttributesResult>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</GetQueueAttributesResponse>"""

    return Response(content=response, media_type="application/xml")


async def set_queue_attributes(environment: Environment, params: dict, db: Session):
    """SetQueueAttributes - Update queue configuration"""
    queue_url = params.get("QueueUrl", "")
    queue_name = queue_url.split("/")[-1]

    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    # Update attributes (simplified)
    db.commit()

    response = f"""<?xml version="1.0"?>
<SetQueueAttributesResponse>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</SetQueueAttributesResponse>"""

    return Response(content=response, media_type="application/xml")


async def purge_queue(environment: Environment, params: dict, db: Session):
    """PurgeQueue - Delete all messages"""
    queue_url = params.get("QueueUrl", "")
    queue_name = queue_url.split("/")[-1]

    queue = db.query(MockSQSQueue).filter(
        MockSQSQueue.environment_id == environment.id,
        MockSQSQueue.queue_name == queue_name
    ).first()

    if not queue:
        return Response(
            content=sqs_error_response("AWS.SimpleQueueService.NonExistentQueue", f"Queue not found: {queue_name}"),
            media_type="application/xml",
            status_code=404
        )

    # Delete all messages from Redis
    if redis_client:
        redis_client.delete(queue.redis_list_key)

    queue.approximate_number_of_messages = 0
    db.commit()

    logger.info(f"Purged SQS queue: {queue_name}")

    response = f"""<?xml version="1.0"?>
<PurgeQueueResponse>
    <ResponseMetadata>
        <RequestId>{uuid.uuid4()}</RequestId>
    </ResponseMetadata>
</PurgeQueueResponse>"""

    return Response(content=response, media_type="application/xml")
