"""
MockFactory.io - Python S3 Example
Using boto3 to interact with MockFactory's AWS S3 emulation
"""
import boto3
from botocore.client import Config

# Your MockFactory environment endpoint
# Get this from the environments API after creating your environment
ENVIRONMENT_ID = "env-abc123"  # Replace with your actual environment ID
S3_ENDPOINT = f"https://s3.{ENVIRONMENT_ID}.mockfactory.io"

# MockFactory credentials (dummy credentials - not validated in POC)
AWS_ACCESS_KEY_ID = "mockfactory"
AWS_SECRET_ACCESS_KEY = "mockfactory"


def create_s3_client():
    """
    Create an S3 client pointed at MockFactory
    """
    return boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'  # Dummy region
    )


def example_upload_file():
    """Upload a file to MockFactory S3"""
    s3 = create_s3_client()

    bucket_name = "my-test-bucket"
    file_key = "test-file.txt"
    file_content = b"Hello from MockFactory!"

    # Upload
    s3.put_object(
        Bucket=bucket_name,
        Key=file_key,
        Body=file_content
    )
    print(f"✓ Uploaded {file_key} to {bucket_name}")


def example_list_objects():
    """List objects in MockFactory S3 bucket"""
    s3 = create_s3_client()

    bucket_name = "my-test-bucket"

    # List
    response = s3.list_objects_v2(Bucket=bucket_name)

    print(f"\nObjects in {bucket_name}:")
    for obj in response.get('Contents', []):
        print(f"  - {obj['Key']} ({obj['Size']} bytes)")


def example_download_file():
    """Download a file from MockFactory S3"""
    s3 = create_s3_client()

    bucket_name = "my-test-bucket"
    file_key = "test-file.txt"

    # Download
    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    content = response['Body'].read()

    print(f"\nDownloaded {file_key}:")
    print(f"  Content: {content.decode()}")


def example_delete_file():
    """Delete a file from MockFactory S3"""
    s3 = create_s3_client()

    bucket_name = "my-test-bucket"
    file_key = "test-file.txt"

    # Delete
    s3.delete_object(Bucket=bucket_name, Key=file_key)
    print(f"✓ Deleted {file_key}")


if __name__ == "__main__":
    print("MockFactory.io - Python S3 Example")
    print(f"Environment: {ENVIRONMENT_ID}\n")

    # Run examples
    example_upload_file()
    example_list_objects()
    example_download_file()
    example_delete_file()

    print("\n✓ All operations completed successfully!")
    print(f"\nCost: ~$0.05/hour while environment is running")
    print("Remember to destroy your environment when done testing!")
