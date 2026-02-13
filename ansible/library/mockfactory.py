#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for managing MockFactory.io resources via API

EXAMPLES:
    - name: Create mock AWS VPC
      mockfactory:
        api_key: "{{ mockfactory_api_key }}"
        api_url: "https://mockfactory.io/api/v1"
        resource_type: vpc
        action: create
        environment_id: "env-123"
        params:
          cidr_block: "10.0.0.0/16"
          enable_dns_hostnames: true

    - name: Create mock Lambda function
      mockfactory:
        api_key: "{{ mockfactory_api_key }}"
        resource_type: lambda
        action: create
        environment_id: "env-123"
        params:
          function_name: "my-function"
          runtime: "python3.9"
          memory_mb: 128
          code_zip_base64: "{{ lookup('file', 'lambda.zip') | b64encode }}"

    - name: Create DynamoDB table
      mockfactory:
        api_key: "{{ mockfactory_api_key }}"
        resource_type: dynamodb
        action: create
        environment_id: "env-123"
        params:
          table_name: "users"
          partition_key: "user_id"
          partition_key_type: "S"

    - name: Delete VPC
      mockfactory:
        api_key: "{{ mockfactory_api_key }}"
        resource_type: vpc
        action: delete
        resource_id: "vpc-abc123"
"""

from ansible.module_utils.basic import AnsibleModule
import json

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class MockFactoryAPI:
    """MockFactory.io API client"""

    def __init__(self, api_key, api_url="https://mockfactory.io/api/v1"):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def create_vpc(self, environment_id, params):
        """Create mock VPC"""
        url = f"{self.api_url}/aws/vpc"
        data = {
            "Action": "CreateVpc",
            "Version": "2016-11-15",
            **params
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def delete_vpc(self, vpc_id):
        """Delete mock VPC"""
        url = f"{self.api_url}/aws/vpc"
        data = {
            "Action": "DeleteVpc",
            "VpcId": vpc_id
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def create_lambda(self, environment_id, params):
        """Create mock Lambda function"""
        url = f"{self.api_url}/aws/lambda"
        data = {
            "Action": "CreateFunction",
            **params
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def delete_lambda(self, function_name):
        """Delete mock Lambda function"""
        url = f"{self.api_url}/aws/lambda"
        data = {
            "Action": "DeleteFunction",
            "FunctionName": function_name
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def create_dynamodb_table(self, environment_id, params):
        """Create mock DynamoDB table"""
        url = f"{self.api_url}/aws/dynamodb"
        data = {
            "Action": "CreateTable",
            **params
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def delete_dynamodb_table(self, table_name):
        """Delete mock DynamoDB table"""
        url = f"{self.api_url}/aws/dynamodb"
        data = {
            "Action": "DeleteTable",
            "TableName": table_name
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def create_sqs_queue(self, environment_id, params):
        """Create mock SQS queue"""
        url = f"{self.api_url}/aws/sqs"
        data = {
            "Action": "CreateQueue",
            **params
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def delete_sqs_queue(self, queue_url):
        """Delete mock SQS queue"""
        url = f"{self.api_url}/aws/sqs"
        data = {
            "Action": "DeleteQueue",
            "QueueUrl": queue_url
        }
        resp = requests.post(url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            api_key=dict(type='str', required=True, no_log=True),
            api_url=dict(type='str', default='https://mockfactory.io/api/v1'),
            resource_type=dict(
                type='str',
                required=True,
                choices=['vpc', 'lambda', 'dynamodb', 'sqs', 'subnet', 'security_group']
            ),
            action=dict(type='str', required=True, choices=['create', 'delete', 'update']),
            environment_id=dict(type='str', required=False),
            resource_id=dict(type='str', required=False),
            params=dict(type='dict', default={}),
        ),
        supports_check_mode=True
    )

    if not HAS_REQUESTS:
        module.fail_json(msg='requests library is required for this module')

    api_key = module.params['api_key']
    api_url = module.params['api_url']
    resource_type = module.params['resource_type']
    action = module.params['action']
    environment_id = module.params['environment_id']
    resource_id = module.params['resource_id']
    params = module.params['params']

    client = MockFactoryAPI(api_key, api_url)

    changed = False
    result = {}

    try:
        # CREATE actions
        if action == 'create':
            if module.check_mode:
                module.exit_json(changed=True, msg='Would create resource (check mode)')

            if resource_type == 'vpc':
                result = client.create_vpc(environment_id, params)
                changed = True

            elif resource_type == 'lambda':
                result = client.create_lambda(environment_id, params)
                changed = True

            elif resource_type == 'dynamodb':
                result = client.create_dynamodb_table(environment_id, params)
                changed = True

            elif resource_type == 'sqs':
                result = client.create_sqs_queue(environment_id, params)
                changed = True

        # DELETE actions
        elif action == 'delete':
            if not resource_id:
                module.fail_json(msg='resource_id required for delete action')

            if module.check_mode:
                module.exit_json(changed=True, msg='Would delete resource (check mode)')

            if resource_type == 'vpc':
                result = client.delete_vpc(resource_id)
                changed = True

            elif resource_type == 'lambda':
                result = client.delete_lambda(resource_id)
                changed = True

            elif resource_type == 'dynamodb':
                result = client.delete_dynamodb_table(resource_id)
                changed = True

            elif resource_type == 'sqs':
                result = client.delete_sqs_queue(resource_id)
                changed = True

        module.exit_json(changed=changed, resource=result)

    except requests.exceptions.HTTPError as e:
        module.fail_json(msg=f'API error: {str(e)}', status_code=e.response.status_code)
    except Exception as e:
        module.fail_json(msg=f'Error: {str(e)}')


if __name__ == '__main__':
    main()
