#!/usr/bin/env python3
"""
Test Cloud Emulation Features
Validates that all cloud emulation endpoints are working correctly
"""
import requests
import json
import sys
from typing import Dict, Optional

BASE_URL = "http://localhost:8000"
API_KEY = None  # Will be created during test


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def print_test(message: str):
    print(f"{Colors.BLUE}🧪 {message}{Colors.END}")


def print_success(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")


def print_error(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.END}")


def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")


def test_health() -> bool:
    """Test basic health endpoint"""
    print_test("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "healthy":
                print_success("Health check passed")
                return True
        print_error(f"Health check failed: {response.status_code}")
        return False
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False


def test_api_docs() -> bool:
    """Test API documentation is accessible"""
    print_test("Testing API docs...")
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=10, allow_redirects=True)
        if response.status_code == 200:
            print_success("API docs accessible")
            return True
        print_error(f"API docs failed: {response.status_code}")
        return False
    except Exception as e:
        print_error(f"API docs failed: {e}")
        return False


def create_test_user() -> Optional[Dict]:
    """Create a test user and get auth token"""
    print_test("Creating test user...")

    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"test_{random_suffix}@example.com"
    password = "testpassword123"

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/signup",
            json={"email": email, "password": password},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print_success(f"Test user created: {email}")
            return {
                "email": email,
                "password": password,
                "token": data.get("access_token"),
                "user": data.get("user")
            }
        else:
            print_error(f"User creation failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_error(f"User creation failed: {e}")
        return None


def create_api_key(token: str) -> Optional[str]:
    """Create an API key for testing"""
    print_test("Creating API key...")

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/api-keys/",
            json={"name": "Test Key"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )

        if response.status_code == 201:
            data = response.json()
            api_key = data.get("api_key")
            print_success(f"API key created: {api_key[:20]}...")
            return api_key
        else:
            print_error(f"API key creation failed: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"API key creation failed: {e}")
        return None


def test_vpc_emulation(api_key: str) -> bool:
    """Test AWS VPC emulation endpoint"""
    print_test("Testing AWS VPC emulation...")

    try:
        # Test CreateVpc action
        response = requests.post(
            f"{BASE_URL}/aws/vpc",
            json={
                "Action": "CreateVpc",
                "CidrBlock": "10.0.0.0/16"
            },
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if "VpcId" in data:
                print_success(f"VPC created: {data['VpcId']}")
                return True
            else:
                print_error(f"VPC response missing VpcId: {data}")
                return False
        else:
            print_error(f"VPC creation failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print_error(f"VPC test failed: {e}")
        return False


def test_lambda_emulation(api_key: str) -> bool:
    """Test AWS Lambda emulation endpoint"""
    print_test("Testing AWS Lambda emulation...")

    try:
        # Test CreateFunction
        response = requests.post(
            f"{BASE_URL}/aws/lambda",
            json={
                "Action": "CreateFunction",
                "FunctionName": "test-function",
                "Runtime": "python3.9",
                "Handler": "lambda_function.lambda_handler",
                "Code": {
                    "ZipFile": "def lambda_handler(event, context): return {'statusCode': 200}"
                }
            },
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if "FunctionArn" in data or "FunctionName" in data:
                print_success("Lambda function created")
                return True
            else:
                print_error(f"Lambda response unexpected: {data}")
                return False
        else:
            print_error(f"Lambda creation failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print_error(f"Lambda test failed: {e}")
        return False


def test_dynamodb_emulation(api_key: str) -> bool:
    """Test AWS DynamoDB emulation endpoint"""
    print_test("Testing AWS DynamoDB emulation...")

    try:
        # Test CreateTable
        response = requests.post(
            f"{BASE_URL}/aws/dynamodb",
            json={
                "Action": "CreateTable",
                "TableName": "test-table",
                "KeySchema": [
                    {"AttributeName": "id", "KeyType": "HASH"}
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "id", "AttributeType": "S"}
                ],
                "BillingMode": "PAY_PER_REQUEST"
            },
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if "TableDescription" in data or "TableName" in data:
                print_success("DynamoDB table created")
                return True
            else:
                print_error(f"DynamoDB response unexpected: {data}")
                return False
        else:
            print_error(f"DynamoDB creation failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print_error(f"DynamoDB test failed: {e}")
        return False


def test_sqs_emulation(api_key: str) -> bool:
    """Test AWS SQS emulation endpoint"""
    print_test("Testing AWS SQS emulation...")

    try:
        # Test CreateQueue
        response = requests.post(
            f"{BASE_URL}/aws/sqs",
            json={
                "Action": "CreateQueue",
                "QueueName": "test-queue"
            },
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if "QueueUrl" in data:
                print_success(f"SQS queue created: {data['QueueUrl']}")
                return True
            else:
                print_error(f"SQS response unexpected: {data}")
                return False
        else:
            print_error(f"SQS creation failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print_error(f"SQS test failed: {e}")
        return False


def test_oci_credentials() -> bool:
    """Test if OCI credentials are configured on the server"""
    print_test("Testing OCI configuration...")

    # This is a passive test - we'll check if the API can initialize OCI clients
    # by attempting a VPC creation which requires OCI credentials
    print_warning("OCI credential check requires VPC test to pass")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MockFactory Cloud Emulation Test Suite")
    print("="*80 + "\n")

    results = {
        "passed": [],
        "failed": []
    }

    # Basic tests
    if test_health():
        results["passed"].append("Health Check")
    else:
        results["failed"].append("Health Check")
        print_error("Basic health check failed - aborting tests")
        sys.exit(1)

    if test_api_docs():
        results["passed"].append("API Docs")
    else:
        results["failed"].append("API Docs")

    # Create test user and API key
    user_data = create_test_user()
    if not user_data:
        print_error("Cannot proceed without test user")
        sys.exit(1)
    results["passed"].append("User Creation")

    api_key = create_api_key(user_data["token"])
    if not api_key:
        print_error("Cannot proceed without API key")
        sys.exit(1)
    results["passed"].append("API Key Creation")

    # Test cloud emulation endpoints
    print("\n" + "-"*80)
    print("Testing Cloud Emulation Features")
    print("-"*80 + "\n")

    if test_vpc_emulation(api_key):
        results["passed"].append("VPC Emulation")
    else:
        results["failed"].append("VPC Emulation")

    if test_lambda_emulation(api_key):
        results["passed"].append("Lambda Emulation")
    else:
        results["failed"].append("Lambda Emulation")

    if test_dynamodb_emulation(api_key):
        results["passed"].append("DynamoDB Emulation")
    else:
        results["failed"].append("DynamoDB Emulation")

    if test_sqs_emulation(api_key):
        results["passed"].append("SQS Emulation")
    else:
        results["failed"].append("SQS Emulation")

    # Summary
    print("\n" + "="*80)
    print("Test Summary")
    print("="*80 + "\n")

    print(f"{Colors.GREEN}✅ Passed: {len(results['passed'])}{Colors.END}")
    for test in results["passed"]:
        print(f"   • {test}")

    if results["failed"]:
        print(f"\n{Colors.RED}❌ Failed: {len(results['failed'])}{Colors.END}")
        for test in results["failed"]:
            print(f"   • {test}")

    print("\n" + "="*80 + "\n")

    # Exit with appropriate code
    if results["failed"]:
        print_error(f"Some tests failed ({len(results['failed'])}/{len(results['passed']) + len(results['failed'])})")
        sys.exit(1)
    else:
        print_success(f"All tests passed! ({len(results['passed'])}/{len(results['passed'])})")
        sys.exit(0)


if __name__ == "__main__":
    main()
