"""
AWS DynamoDB API Emulator
Backed by PostgreSQL JSONB for fast NoSQL operations
Table creation is FREE, but reads/writes consume user credits
"""
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.vpc_resources import MockDynamoDBTable, MockDynamoDBItem
from app.models.environment import Environment
import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

router = APIRouter()
logger = logging.getLogger(__name__)


def generate_table_arn(region: str, account_id: str, table_name: str) -> str:
    """Generate DynamoDB table ARN"""
    return f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}"


def extract_key_value(item: Dict, key_name: str) -> str:
    """Extract value from DynamoDB typed format"""
    key_data = item.get(key_name, {})
    # DynamoDB format: {"S": "value"} or {"N": "123"}
    if "S" in key_data:
        return key_data["S"]
    elif "N" in key_data:
        return key_data["N"]
    elif "B" in key_data:
        return key_data["B"]
    return ""


@router.post("/aws/dynamodb")
async def dynamodb_api(request: Request, db: Session = Depends(get_db)):
    """
    AWS DynamoDB API endpoint
    Uses JSON protocol with X-Amz-Target header
    """
    # Get environment from subdomain
    host = request.headers.get("host", "")
    env_id = host.split(".")[0].replace("env-", "") if "env-" in host else None

    if not env_id:
        return Response(
            content=json.dumps({"__type": "ValidationException", "message": "Invalid environment"}),
            media_type="application/json",
            status_code=400
        )

    # Get environment
    environment = db.query(Environment).filter(Environment.id == env_id).first()
    if not environment:
        return Response(
            content=json.dumps({"__type": "ResourceNotFoundException", "message": "Environment not found"}),
            media_type="application/json",
            status_code=404
        )

    # Parse action from X-Amz-Target header
    # Example: "DynamoDB_20120810.CreateTable"
    target = request.headers.get("X-Amz-Target", "")
    action = target.split(".")[-1] if "." in target else ""

    # Parse JSON body
    body = await request.body()
    try:
        params = json.loads(body) if body else {}
    except:
        return Response(
            content=json.dumps({"__type": "ValidationException", "message": "Invalid JSON"}),
            media_type="application/json",
            status_code=400
        )

    logger.info(f"DynamoDB action: {action}")

    # Route to handlers
    if action == "CreateTable":
        return await create_table(environment, params, db)
    elif action == "DescribeTable":
        return await describe_table(environment, params, db)
    elif action == "ListTables":
        return await list_tables(environment, db)
    elif action == "DeleteTable":
        return await delete_table(environment, params, db)
    elif action == "PutItem":
        return await put_item(environment, params, db)
    elif action == "GetItem":
        return await get_item(environment, params, db)
    elif action == "DeleteItem":
        return await delete_item(environment, params, db)
    elif action == "Query":
        return await query_items(environment, params, db)
    elif action == "Scan":
        return await scan_items(environment, params, db)
    elif action == "UpdateItem":
        return await update_item(environment, params, db)
    elif action == "BatchGetItem":
        return await batch_get_item(environment, params, db)
    elif action == "BatchWriteItem":
        return await batch_write_item(environment, params, db)
    else:
        return Response(
            content=json.dumps({"__type": "InvalidAction", "message": f"Unknown action: {action}"}),
            media_type="application/json",
            status_code=400
        )


async def create_table(environment: Environment, params: dict, db: Session):
    """
    CreateTable - Define table schema (FREE - just metadata)
    No actual storage created yet - only when items are written (credits consumed)
    """
    table_name = params.get("TableName")

    # Check if table already exists
    existing = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if existing:
        return Response(
            content=json.dumps({
                "__type": "ResourceInUseException",
                "message": f"Table already exists: {table_name}"
            }),
            media_type="application/json",
            status_code=400
        )

    # Parse key schema
    key_schema = params.get("KeySchema", [])
    attribute_definitions = params.get("AttributeDefinitions", [])

    partition_key = next((k for k in key_schema if k["KeyType"] == "HASH"), None)
    sort_key = next((k for k in key_schema if k["KeyType"] == "RANGE"), None)

    partition_key_name = partition_key["AttributeName"] if partition_key else None
    sort_key_name = sort_key["AttributeName"] if sort_key else None

    # Get attribute types
    partition_key_type = next(
        (a["AttributeType"] for a in attribute_definitions if a["AttributeName"] == partition_key_name),
        "S"
    )
    sort_key_type = next(
        (a["AttributeType"] for a in attribute_definitions if a["AttributeName"] == sort_key_name),
        None
    ) if sort_key_name else None

    # Billing mode
    billing_mode = params.get("BillingMode", "PAY_PER_REQUEST")
    provisioned_throughput = params.get("ProvisionedThroughput", {})

    # Generate IDs
    table_id = f"ddb-{uuid.uuid4().hex[:16]}"
    table_arn = generate_table_arn("us-east-1", "123456789012", table_name)

    # Create table (just metadata - no storage yet!)
    table = MockDynamoDBTable(
        id=table_id,
        environment_id=environment.id,
        table_name=table_name,
        table_arn=table_arn,
        table_status="CREATING",
        partition_key_name=partition_key_name,
        partition_key_type=partition_key_type,
        sort_key_name=sort_key_name,
        sort_key_type=sort_key_type,
        billing_mode=billing_mode,
        read_capacity_units=provisioned_throughput.get("ReadCapacityUnits"),
        write_capacity_units=provisioned_throughput.get("WriteCapacityUnits"),
        item_count=0,
        table_size_bytes=0
    )

    db.add(table)
    db.commit()

    # Mark as ACTIVE immediately (mock)
    table.table_status = "ACTIVE"
    db.commit()
    db.refresh(table)

    logger.info(f"Created DynamoDB table (metadata only): {table_name}")

    # Return AWS response
    response = {
        "TableDescription": {
            "TableName": table.table_name,
            "TableArn": table.table_arn,
            "TableStatus": table.table_status,
            "CreationDateTime": table.created_at.timestamp(),
            "KeySchema": [
                {"AttributeName": table.partition_key_name, "KeyType": "HASH"}
            ] + ([{"AttributeName": table.sort_key_name, "KeyType": "RANGE"}] if table.sort_key_name else []),
            "AttributeDefinitions": [
                {"AttributeName": table.partition_key_name, "AttributeType": table.partition_key_type}
            ] + ([{"AttributeName": table.sort_key_name, "AttributeType": table.sort_key_type}] if table.sort_key_name else []),
            "ItemCount": table.item_count,
            "TableSizeBytes": table.table_size_bytes,
            "BillingModeSummary": {
                "BillingMode": table.billing_mode
            }
        }
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json"
    )


async def put_item(environment: Environment, params: dict, db: Session):
    """
    PutItem - Write item to table
    THIS CONSUMES CREDITS - actual storage operation
    """
    table_name = params.get("TableName")
    item = params.get("Item")

    # Find table
    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Extract key values
    partition_key_value = extract_key_value(item, table.partition_key_name)
    sort_key_value = extract_key_value(item, table.sort_key_name) if table.sort_key_name else None

    # Check if item exists (for update)
    existing_item = db.query(MockDynamoDBItem).filter(
        MockDynamoDBItem.table_id == table.id,
        MockDynamoDBItem.partition_key_value == partition_key_value,
        MockDynamoDBItem.sort_key_value == sort_key_value
    ).first()

    if existing_item:
        # Update existing item
        existing_item.item_data = item
        existing_item.updated_at = datetime.utcnow()
        logger.info(f"Updated DynamoDB item: {table_name} / {partition_key_value}")
    else:
        # Create new item
        new_item = MockDynamoDBItem(
            table_id=table.id,
            partition_key_value=partition_key_value,
            sort_key_value=sort_key_value,
            item_data=item
        )
        db.add(new_item)

        # Update table stats
        table.item_count += 1
        table.table_size_bytes += len(json.dumps(item))

        logger.info(f"Created DynamoDB item (CREDIT USED): {table_name} / {partition_key_value}")

    db.commit()

    # TODO: Deduct credits from user account here
    # Example: user.credits -= calculate_write_cost(table, item)

    return Response(
        content=json.dumps({}),
        media_type="application/json"
    )


async def get_item(environment: Environment, params: dict, db: Session):
    """
    GetItem - Read item from table
    THIS CONSUMES CREDITS - actual read operation
    """
    table_name = params.get("TableName")
    key = params.get("Key")

    # Find table
    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Extract key values
    partition_key_value = extract_key_value(key, table.partition_key_name)
    sort_key_value = extract_key_value(key, table.sort_key_name) if table.sort_key_name else None

    # Find item
    item = db.query(MockDynamoDBItem).filter(
        MockDynamoDBItem.table_id == table.id,
        MockDynamoDBItem.partition_key_value == partition_key_value,
        MockDynamoDBItem.sort_key_value == sort_key_value
    ).first()

    if not item:
        # Item not found - return empty response
        return Response(
            content=json.dumps({}),
            media_type="application/json"
        )

    logger.info(f"Retrieved DynamoDB item (CREDIT USED): {table_name} / {partition_key_value}")

    # TODO: Deduct credits from user account
    # Example: user.credits -= calculate_read_cost(table, item)

    return Response(
        content=json.dumps({"Item": item.item_data}),
        media_type="application/json"
    )


async def delete_item(environment: Environment, params: dict, db: Session):
    """DeleteItem - Remove item"""
    table_name = params.get("TableName")
    key = params.get("Key")

    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    partition_key_value = extract_key_value(key, table.partition_key_name)
    sort_key_value = extract_key_value(key, table.sort_key_name) if table.sort_key_name else None

    item = db.query(MockDynamoDBItem).filter(
        MockDynamoDBItem.table_id == table.id,
        MockDynamoDBItem.partition_key_value == partition_key_value,
        MockDynamoDBItem.sort_key_value == sort_key_value
    ).first()

    if item:
        table.item_count -= 1
        table.table_size_bytes -= len(json.dumps(item.item_data))
        db.delete(item)
        db.commit()
        logger.info(f"Deleted DynamoDB item: {table_name} / {partition_key_value}")

    return Response(
        content=json.dumps({}),
        media_type="application/json"
    )


async def query_items(environment: Environment, params: dict, db: Session):
    """Query - Find items by partition key (and optional sort key condition)"""
    table_name = params.get("TableName")

    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Parse key conditions
    # For simplicity, we'll do basic partition key equality
    # TODO: Implement full query expression parsing

    key_conditions = params.get("KeyConditionExpression", "")
    expression_values = params.get("ExpressionAttributeValues", {})

    # Simple implementation - query all items for now
    items = db.query(MockDynamoDBItem).filter(
        MockDynamoDBItem.table_id == table.id
    ).limit(100).all()

    logger.info(f"Queried DynamoDB table (CREDITS USED): {table_name} - {len(items)} items")

    return Response(
        content=json.dumps({
            "Items": [item.item_data for item in items],
            "Count": len(items),
            "ScannedCount": len(items)
        }),
        media_type="application/json"
    )


async def scan_items(environment: Environment, params: dict, db: Session):
    """Scan - Read all items (expensive!)"""
    table_name = params.get("TableName")

    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Get all items
    items = db.query(MockDynamoDBItem).filter(
        MockDynamoDBItem.table_id == table.id
    ).all()

    logger.info(f"Scanned DynamoDB table (HIGH CREDIT COST!): {table_name} - {len(items)} items")

    return Response(
        content=json.dumps({
            "Items": [item.item_data for item in items],
            "Count": len(items),
            "ScannedCount": len(items)
        }),
        media_type="application/json"
    )


async def update_item(environment: Environment, params: dict, db: Session):
    """UpdateItem - Update specific attributes"""
    # For now, redirect to PutItem (simplified)
    return await put_item(environment, params, db)


async def batch_get_item(environment: Environment, params: dict, db: Session):
    """BatchGetItem - Get multiple items at once"""
    # Simplified implementation
    return Response(
        content=json.dumps({"Responses": {}}),
        media_type="application/json"
    )


async def batch_write_item(environment: Environment, params: dict, db: Session):
    """BatchWriteItem - Write multiple items at once"""
    # Simplified implementation
    return Response(
        content=json.dumps({"UnprocessedItems": {}}),
        media_type="application/json"
    )


async def describe_table(environment: Environment, params: dict, db: Session):
    """DescribeTable - Get table metadata (FREE)"""
    table_name = params.get("TableName")

    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    response = {
        "Table": {
            "TableName": table.table_name,
            "TableArn": table.table_arn,
            "TableStatus": table.table_status,
            "CreationDateTime": table.created_at.timestamp(),
            "ItemCount": table.item_count,
            "TableSizeBytes": table.table_size_bytes,
            "KeySchema": [
                {"AttributeName": table.partition_key_name, "KeyType": "HASH"}
            ] + ([{"AttributeName": table.sort_key_name, "KeyType": "RANGE"}] if table.sort_key_name else []),
            "AttributeDefinitions": [
                {"AttributeName": table.partition_key_name, "AttributeType": table.partition_key_type}
            ] + ([{"AttributeName": table.sort_key_name, "AttributeType": table.sort_key_type}] if table.sort_key_name else []),
            "BillingModeSummary": {
                "BillingMode": table.billing_mode
            }
        }
    }

    return Response(
        content=json.dumps(response),
        media_type="application/json"
    )


async def list_tables(environment: Environment, db: Session):
    """ListTables - List all tables (FREE)"""
    tables = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id
    ).all()

    return Response(
        content=json.dumps({
            "TableNames": [t.table_name for t in tables]
        }),
        media_type="application/json"
    )


async def delete_table(environment: Environment, params: dict, db: Session):
    """DeleteTable - Remove table and all items"""
    table_name = params.get("TableName")

    table = db.query(MockDynamoDBTable).filter(
        MockDynamoDBTable.environment_id == environment.id,
        MockDynamoDBTable.table_name == table_name
    ).first()

    if not table:
        return Response(
            content=json.dumps({
                "__type": "ResourceNotFoundException",
                "message": f"Table not found: {table_name}"
            }),
            media_type="application/json",
            status_code=404
        )

    # Delete table (cascade deletes items)
    table.table_status = "DELETING"
    db.commit()

    db.delete(table)
    db.commit()

    logger.info(f"Deleted DynamoDB table: {table_name}")

    return Response(
        content=json.dumps({
            "TableDescription": {
                "TableName": table_name,
                "TableStatus": "DELETING"
            }
        }),
        media_type="application/json"
    )
