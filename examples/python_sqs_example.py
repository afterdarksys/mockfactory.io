"""
MockFactory.io - Python SQS Example
Using boto3 to interact with MockFactory's AWS SQS emulation (ElasticMQ backend)
"""
import boto3
import json
from botocore.client import Config

# Your MockFactory environment endpoint
# Get this from the environments API after creating your environment
ENVIRONMENT_ID = "env-abc123"  # Replace with your actual environment ID

# ElasticMQ endpoint (from environment.endpoints.aws_sqs)
SQS_ENDPOINT = "http://localhost:30147"  # Replace with actual port from your environment

# MockFactory credentials (dummy credentials - not validated with ElasticMQ)
AWS_ACCESS_KEY_ID = "mockfactory"
AWS_SECRET_ACCESS_KEY = "mockfactory"


def create_sqs_client():
    """
    Create an SQS client pointed at MockFactory ElasticMQ
    """
    return boto3.client(
        'sqs',
        endpoint_url=SQS_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='elasticmq',  # ElasticMQ special region
        config=Config(signature_version='v4')
    )


def example_create_queue():
    """Create a new SQS queue"""
    sqs = create_sqs_client()

    response = sqs.create_queue(
        QueueName='test-queue',
        Attributes={
            'DelaySeconds': '0',
            'MessageRetentionPeriod': '86400'  # 1 day
        }
    )

    queue_url = response['QueueUrl']
    print(f"✓ Created queue: {queue_url}")
    return queue_url


def example_send_message(queue_url):
    """Send a message to SQS queue"""
    sqs = create_sqs_client()

    message_body = {
        "order_id": "12345",
        "customer": "Alice",
        "total": 99.99
    }

    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message_body),
        MessageAttributes={
            'OrderType': {
                'StringValue': 'premium',
                'DataType': 'String'
            }
        }
    )

    print(f"✓ Sent message: {response['MessageId']}")
    return response['MessageId']


def example_send_batch(queue_url):
    """Send multiple messages in one call"""
    sqs = create_sqs_client()

    entries = []
    for i in range(5):
        entries.append({
            'Id': f'msg-{i}',
            'MessageBody': json.dumps({
                'order_id': f'ORD-{i}',
                'amount': i * 10
            })
        })

    response = sqs.send_message_batch(
        QueueUrl=queue_url,
        Entries=entries
    )

    print(f"✓ Sent {len(response['Successful'])} messages in batch")


def example_receive_messages(queue_url):
    """Receive messages from SQS queue"""
    sqs = create_sqs_client()

    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=2,  # Long polling
        MessageAttributeNames=['All']
    )

    messages = response.get('Messages', [])
    print(f"\n✓ Received {len(messages)} messages:")

    for msg in messages:
        print(f"  - ID: {msg['MessageId']}")
        print(f"    Body: {msg['Body']}")

        # Delete message after processing
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=msg['ReceiptHandle']
        )
        print(f"    ✓ Deleted")

    return messages


def example_get_queue_attributes(queue_url):
    """Get queue attributes and stats"""
    sqs = create_sqs_client()

    response = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['All']
    )

    attrs = response['Attributes']
    print(f"\nQueue Attributes:")
    print(f"  - Messages Available: {attrs.get('ApproximateNumberOfMessages', 0)}")
    print(f"  - Messages In Flight: {attrs.get('ApproximateNumberOfMessagesNotVisible', 0)}")
    print(f"  - Retention Period: {attrs.get('MessageRetentionPeriod', 0)} seconds")


def example_list_queues():
    """List all queues"""
    sqs = create_sqs_client()

    response = sqs.list_queues()

    print(f"\nAll Queues:")
    for url in response.get('QueueUrls', []):
        print(f"  - {url}")


def example_delete_queue(queue_url):
    """Delete a queue"""
    sqs = create_sqs_client()

    sqs.delete_queue(QueueUrl=queue_url)
    print(f"\n✓ Deleted queue: {queue_url}")


if __name__ == "__main__":
    print("MockFactory.io - Python SQS (ElasticMQ) Example")
    print(f"Environment: {ENVIRONMENT_ID}")
    print(f"Endpoint: {SQS_ENDPOINT}\n")

    # Create queue
    queue_url = example_create_queue()

    # Send single message
    example_send_message(queue_url)

    # Send batch
    example_send_batch(queue_url)

    # Check queue stats
    example_get_queue_attributes(queue_url)

    # Receive and process messages
    example_receive_messages(queue_url)

    # List all queues
    example_list_queues()

    # Clean up
    example_delete_queue(queue_url)

    print("\n✓ All SQS operations completed successfully!")
    print(f"\nCost: $0.03/hour for SQS service")
    print("Remember to destroy your environment when done testing!")
