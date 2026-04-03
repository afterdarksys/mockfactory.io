import os
import logging
import uuid
from typing import Dict, List
import pika
from app.services.provisioning_manager import provisioning_manager

logger = logging.getLogger(__name__)

def _get_connection_params(tenant_id: str) -> pika.ConnectionParameters:
    """Retrieve RabbitMQ connection details for a tenant.
    Uses provisioning_manager.status to get host and port.
    """
    status = provisioning_manager.status(tenant_id)
    rabbit = status.get('rabbitmq')
    if not rabbit or rabbit.get('status') != 'running':
        raise RuntimeError('RabbitMQ not provisioned for tenant')
    host = rabbit.get('host')
    port = rabbit.get('ports', {}).get('5672')
    return pika.ConnectionParameters(host=host, port=int(port), credentials=pika.PlainCredentials('guest', 'guest'))

def create_queue(tenant_id: str, queue_name: str) -> Dict:
    try:
        params = _get_connection_params(tenant_id)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        connection.close()
        url = f"http://{params.host}:{params.port}/{queue_name}"
        return {'success': True, 'url': url}
    except Exception as e:
        logger.error(f"Failed to create queue {queue_name} for tenant {tenant_id}: {e}")
        return {'success': False, 'error': str(e)}

def send_message(tenant_id: str, queue_url: str, body: str) -> Dict:
    try:
        params = _get_connection_params(tenant_id)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        # Extract queue name from URL
        queue_name = queue_url.rstrip('/').split('/')[-1]
        result = channel.basic_publish(exchange='', routing_key=queue_name, body=body)
        connection.close()
        message_id = str(uuid.uuid4())
        return {'success': True, 'message_id': message_id}
    except Exception as e:
        logger.error(f"Failed to send message to {queue_url} for tenant {tenant_id}: {e}")
        return {'success': False, 'error': str(e)}

def receive_message(tenant_id: str, queue_url: str, max_number: int = 1) -> Dict:
    try:
        params = _get_connection_params(tenant_id)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        queue_name = queue_url.rstrip('/').split('/')[-1]
        messages: List[Dict] = []
        for _ in range(max_number):
            method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=True)
            if method_frame:
                messages.append({'id': str(method_frame.delivery_tag), 'body': body.decode()})
            else:
                break
        connection.close()
        return {'success': True, 'messages': messages}
    except Exception as e:
        logger.error(f"Failed to receive messages from {queue_url} for tenant {tenant_id}: {e}")
        return {'success': False, 'error': str(e)}

def delete_queue(tenant_id: str, queue_url: str) -> Dict:
    try:
        params = _get_connection_params(tenant_id)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        queue_name = queue_url.rstrip('/').split('/')[-1]
        channel.queue_delete(queue=queue_name)
        connection.close()
        return {'success': True}
    except Exception as e:
        logger.error(f"Failed to delete queue {queue_url} for tenant {tenant_id}: {e}")
        return {'success': False, 'error': str(e)}
