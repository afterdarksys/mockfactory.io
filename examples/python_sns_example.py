"""
MockFactory.io - Python SNS Example
Using boto3 to interact with MockFactory's AWS SNS emulation (ElasticMQ backend)
"""
import boto3
import json
from botocore.client import Config

# Your MockFactory environment endpoint
# Get this from the environments API after creating your environment
ENVIRONMENT_ID = "env-abc123"  # Replace with your actual environment ID

# ElasticMQ endpoint (SNS and SQS share same endpoint)
SNS_ENDPOINT = "http://localhost:30147"  # Replace with actual port from your environment

# MockFactory credentials (dummy credentials - not validated with ElasticMQ)
AWS_ACCESS_KEY_ID = "mockfactory"
AWS_SECRET_ACCESS_KEY = "mockfactory"


def create_sns_client():
    """
    Create an SNS client pointed at MockFactory ElasticMQ
    """
    return boto3.client(
        'sns',
        endpoint_url=SNS_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='elasticmq',
        config=Config(signature_version='v4')
    )


def create_sqs_client():
    """Create SQS client for subscriptions"""
    return boto3.client(
        'sqs',
        endpoint_url=SNS_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='elasticmq',
        config=Config(signature_version='v4')
    )


def example_create_topic():
    """Create an SNS topic"""
    sns = create_sns_client()

    response = sns.create_topic(Name='test-notifications')

    topic_arn = response['TopicArn']
    print(f"✓ Created topic: {topic_arn}")
    return topic_arn


def example_publish_message(topic_arn):
    """Publish a message to SNS topic"""
    sns = create_sns_client()

    message = {
        "event": "user_signup",
        "user_id": "12345",
        "email": "alice@example.com",
        "timestamp": "2026-02-11T10:30:00Z"
    }

    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        Subject='New User Signup',
        MessageAttributes={
            'event_type': {
                'StringValue': 'signup',
                'DataType': 'String'
            },
            'priority': {
                'StringValue': 'high',
                'DataType': 'String'
            }
        }
    )

    print(f"✓ Published message: {response['MessageId']}")
    return response['MessageId']


def example_subscribe_sqs_to_topic(topic_arn, queue_url):
    """Subscribe an SQS queue to SNS topic"""
    sns = create_sns_client()

    # In real AWS, you'd use queue ARN
    # ElasticMQ accepts queue URL
    response = sns.subscribe(
        TopicArn=topic_arn,
        Protocol='sqs',
        Endpoint=queue_url
    )

    subscription_arn = response['SubscriptionArn']
    print(f"✓ Subscribed SQS queue to topic: {subscription_arn}")
    return subscription_arn


def example_list_topics():
    """List all SNS topics"""
    sns = create_sns_client()

    response = sns.list_topics()

    print(f"\nAll Topics:")
    for topic in response.get('Topics', []):
        print(f"  - {topic['TopicArn']}")


def example_list_subscriptions():
    """List all subscriptions"""
    sns = create_sns_client()

    response = sns.list_subscriptions()

    print(f"\nAll Subscriptions:")
    for sub in response.get('Subscriptions', []):
        print(f"  - Protocol: {sub['Protocol']}")
        print(f"    Endpoint: {sub['Endpoint']}")
        print(f"    Topic: {sub['TopicArn']}")


def example_get_topic_attributes(topic_arn):
    """Get topic attributes"""
    sns = create_sns_client()

    response = sns.get_topic_attributes(TopicArn=topic_arn)

    print(f"\nTopic Attributes:")
    for key, value in response['Attributes'].items():
        print(f"  - {key}: {value}")


def example_unsubscribe(subscription_arn):
    """Unsubscribe from topic"""
    sns = create_sns_client()

    sns.unsubscribe(SubscriptionArn=subscription_arn)
    print(f"✓ Unsubscribed: {subscription_arn}")


def example_delete_topic(topic_arn):
    """Delete SNS topic"""
    sns = create_sns_client()

    sns.delete_topic(TopicArn=topic_arn)
    print(f"✓ Deleted topic: {topic_arn}")


def example_sns_to_sqs_workflow():
    """
    Complete workflow: Create topic, subscribe queue, publish, receive
    """
    print("\n=== SNS → SQS Workflow ===\n")

    sns = create_sns_client()
    sqs = create_sqs_client()

    # 1. Create SNS topic
    topic_arn = example_create_topic()

    # 2. Create SQS queue
    queue_response = sqs.create_queue(QueueName='notifications-queue')
    queue_url = queue_response['QueueUrl']
    print(f"✓ Created queue: {queue_url}")

    # 3. Subscribe queue to topic
    subscription_arn = example_subscribe_sqs_to_topic(topic_arn, queue_url)

    # 4. Publish message to topic
    example_publish_message(topic_arn)

    # 5. Receive message from queue
    print("\nWaiting for message in queue...")
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=2
    )

    messages = response.get('Messages', [])
    if messages:
        print(f"✓ Received message in queue:")
        body = json.loads(messages[0]['Body'])
        print(f"  Message: {body}")

        # Delete message
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=messages[0]['ReceiptHandle']
        )
    else:
        print("  (No messages - ElasticMQ may need SNS config)")

    # 6. Clean up
    example_unsubscribe(subscription_arn)
    sqs.delete_queue(QueueUrl=queue_url)
    example_delete_topic(topic_arn)


if __name__ == "__main__":
    print("MockFactory.io - Python SNS (ElasticMQ) Example")
    print(f"Environment: {ENVIRONMENT_ID}")
    print(f"Endpoint: {SNS_ENDPOINT}\n")

    # Basic SNS operations
    topic_arn = example_create_topic()
    example_publish_message(topic_arn)
    example_list_topics()
    example_get_topic_attributes(topic_arn)
    example_delete_topic(topic_arn)

    # SNS to SQS workflow
    example_sns_to_sqs_workflow()

    print("\n✓ All SNS operations completed successfully!")
    print(f"\nCost: $0.03/hour for SNS service (shares ElasticMQ with SQS)")
    print("Remember to destroy your environment when done testing!")
