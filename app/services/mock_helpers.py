"""
MockFactory shared helpers.
ID generators, ETags, timestamps, pagination, and realistic response headers
used by every cloud emulation layer (AWS, GCP, Azure, OCI).
"""
from __future__ import annotations

import base64
import hashlib
import random
import string
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants — realistic-looking account / project IDs
# ---------------------------------------------------------------------------

DEFAULT_AWS_ACCOUNT_ID = "123456789012"
DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_GCP_PROJECT = "mockfactory-dev"
DEFAULT_GCP_PROJECT_NUMBER = "987654321098"
DEFAULT_AZURE_SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
DEFAULT_AZURE_RESOURCE_GROUP = "mockfactory-rg"
DEFAULT_OCI_TENANCY = "ocid1.tenancy.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na"
DEFAULT_OCI_NAMESPACE = "mockfactory"
DEFAULT_OCI_REGION = "us-ashburn-1"
DEFAULT_OCI_COMPARTMENT = "ocid1.compartment.oc1..aaaaaaaa0000000000000000000000000000000000000000000000000001"


# ---------------------------------------------------------------------------
# ID / ARN generators
# ---------------------------------------------------------------------------

def new_uuid() -> str:
    return str(uuid.uuid4())


def new_hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


# --- AWS ---

def aws_account_id() -> str:
    return DEFAULT_AWS_ACCOUNT_ID


def aws_request_id() -> str:
    return str(uuid.uuid4()).upper()


def aws_region() -> str:
    return DEFAULT_AWS_REGION


def ec2_instance_id() -> str:
    return f"i-{uuid.uuid4().hex[:17]}"


def ec2_ami_id() -> str:
    return f"ami-{uuid.uuid4().hex[:8]}"


def ec2_vpc_id() -> str:
    return f"vpc-{uuid.uuid4().hex[:8]}"


def ec2_subnet_id() -> str:
    return f"subnet-{uuid.uuid4().hex[:8]}"


def ec2_sg_id() -> str:
    return f"sg-{uuid.uuid4().hex[:8]}"


def ec2_volume_id() -> str:
    return f"vol-{uuid.uuid4().hex[:17]}"


def ec2_eni_id() -> str:
    return f"eni-{uuid.uuid4().hex[:17]}"


def ec2_igw_id() -> str:
    return f"igw-{uuid.uuid4().hex[:8]}"


def ec2_rtb_id() -> str:
    return f"rtb-{uuid.uuid4().hex[:8]}"


def ec2_snapshot_id() -> str:
    return f"snap-{uuid.uuid4().hex[:8]}"


def iam_user_id() -> str:
    return f"AIDA{uuid.uuid4().hex[:16].upper()}"


def iam_role_id() -> str:
    return f"AROA{uuid.uuid4().hex[:16].upper()}"


def iam_access_key_id() -> str:
    return f"AKIA{uuid.uuid4().hex[:16].upper()}"


def iam_secret_key() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def iam_policy_id() -> str:
    return f"ANPA{uuid.uuid4().hex[:16].upper()}"


def lambda_arn(function_name: str, region: str = DEFAULT_AWS_REGION,
               account: str = DEFAULT_AWS_ACCOUNT_ID) -> str:
    return f"arn:aws:lambda:{region}:{account}:function:{function_name}"


def s3_arn(bucket: str) -> str:
    return f"arn:aws:s3:::{bucket}"


def iam_arn(resource: str, account: str = DEFAULT_AWS_ACCOUNT_ID,
            region: str = "") -> str:
    return f"arn:aws:iam::{account}:{resource}"


def ec2_arn(resource: str, account: str = DEFAULT_AWS_ACCOUNT_ID,
            region: str = DEFAULT_AWS_REGION) -> str:
    return f"arn:aws:ec2:{region}:{account}:{resource}"


def route53_zone_id() -> str:
    return "Z" + uuid.uuid4().hex[:10].upper()


def route53_change_id() -> str:
    return "C" + uuid.uuid4().hex[:14].upper()


def sqs_queue_url(queue_name: str, account: str = DEFAULT_AWS_ACCOUNT_ID,
                  region: str = DEFAULT_AWS_REGION) -> str:
    return f"https://sqs.{region}.amazonaws.com/{account}/{queue_name}"


def sns_topic_arn(topic_name: str, account: str = DEFAULT_AWS_ACCOUNT_ID,
                  region: str = DEFAULT_AWS_REGION) -> str:
    return f"arn:aws:sns:{region}:{account}:{topic_name}"


# --- GCP ---

def gcp_project() -> str:
    return DEFAULT_GCP_PROJECT


def gcp_operation_id() -> str:
    return f"operation-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def gcp_instance_id() -> str:
    return str(random.randint(10 ** 18, 10 ** 19 - 1))


def gcp_disk_id() -> str:
    return str(random.randint(10 ** 18, 10 ** 19 - 1))


def gcp_network_id() -> str:
    return str(random.randint(10 ** 18, 10 ** 19 - 1))


def gcp_self_link(resource_type: str, name: str,
                  project: str = DEFAULT_GCP_PROJECT,
                  zone: str = "us-central1-a") -> str:
    if resource_type in ("networks", "firewalls", "subnetworks"):
        return f"https://www.googleapis.com/compute/v1/projects/{project}/global/{resource_type}/{name}"
    return f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}/{resource_type}/{name}"


def gcp_zone_self_link(zone: str = "us-central1-a",
                       project: str = DEFAULT_GCP_PROJECT) -> str:
    return f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}"


# --- Azure ---

def azure_subscription() -> str:
    return DEFAULT_AZURE_SUBSCRIPTION


def azure_resource_id(resource_type: str, name: str,
                      resource_group: str = DEFAULT_AZURE_RESOURCE_GROUP,
                      subscription: str = DEFAULT_AZURE_SUBSCRIPTION) -> str:
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/{resource_type}/{name}"
    )


def azure_request_id() -> str:
    return str(uuid.uuid4())


def azure_correlation_id() -> str:
    return str(uuid.uuid4())


# --- OCI ---

def ocid(resource_type: str, region_short: str = "iad") -> str:
    """Generate a realistic OCI resource ID (OCID)."""
    return f"ocid1.{resource_type}.oc1.{region_short}..{''.join(random.choices(string.ascii_lowercase + string.digits, k=60))}"


def oci_request_id() -> str:
    return str(uuid.uuid4()).upper().replace("-", "")


def oci_etag() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# ETag / content fingerprint
# ---------------------------------------------------------------------------

def etag_from_content(content: bytes) -> str:
    """MD5-based ETag, same format as real S3."""
    return hashlib.md5(content).hexdigest()


def etag_random() -> str:
    return uuid.uuid4().hex


def version_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """ISO 8601 with milliseconds and Z suffix — used by AWS/OCI/GCP."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def utcnow_rfc1123() -> str:
    """RFC 1123 — used in HTTP Date headers."""
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def utcnow_azure() -> str:
    """Azure-style timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow_epoch() -> int:
    return int(time.time())


def utcnow_gcp() -> str:
    """GCP uses RFC3339 with microseconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# HTTP response headers per cloud
# ---------------------------------------------------------------------------

def aws_headers(region: str = DEFAULT_AWS_REGION,
                request_id: Optional[str] = None,
                extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    rid = request_id or aws_request_id()
    h = {
        "x-amz-request-id": rid,
        "x-amz-id-2": uuid.uuid4().hex + uuid.uuid4().hex,
        "Date": utcnow_rfc1123(),
        "Server": "AmazonS3",
        "x-amzn-RequestId": rid,
    }
    if extra:
        h.update(extra)
    return h


def s3_object_headers(content: bytes, content_type: str = "application/octet-stream",
                       version: Optional[str] = None) -> Dict[str, str]:
    etag = etag_from_content(content)
    h = {
        "ETag": f'"{etag}"',
        "Content-Length": str(len(content)),
        "Content-Type": content_type,
        "Last-Modified": utcnow_rfc1123(),
        "Accept-Ranges": "bytes",
    }
    if version:
        h["x-amz-version-id"] = version
    return h


def oci_headers(request_id: Optional[str] = None,
                etag: Optional[str] = None,
                extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {
        "opc-request-id": request_id or oci_request_id(),
        "Date": utcnow_rfc1123(),
        "Content-Type": "application/json",
    }
    if etag:
        h["ETag"] = etag
    if extra:
        h.update(extra)
    return h


def gcp_headers(request_id: Optional[str] = None) -> Dict[str, str]:
    return {
        "X-GUploader-UploadID": request_id or uuid.uuid4().hex,
        "Date": utcnow_rfc1123(),
        "Server": "UploadServer",
        "x-goog-request-id": uuid.uuid4().hex,
    }


def azure_headers(request_id: Optional[str] = None,
                  version: str = "2020-06-12") -> Dict[str, str]:
    return {
        "x-ms-request-id": request_id or azure_request_id(),
        "x-ms-version": version,
        "Date": utcnow_rfc1123(),
        "Server": "Windows-Azure-Blob/1.0 Microsoft-HTTPAPI/2.0",
    }


# ---------------------------------------------------------------------------
# Pagination (token-based, cloud-agnostic)
# ---------------------------------------------------------------------------

def paginate(items: List[Any], page_token: Optional[str],
             limit: int = 1000) -> Tuple[List[Any], Optional[str]]:
    """
    Simple offset-token pagination.
    Returns (page_items, next_token | None).
    Token encodes the start index of the NEXT page.
    """
    start = 0
    if page_token:
        try:
            start = int(base64.urlsafe_b64decode(
                page_token.encode() + b"==").decode())
        except Exception:
            start = 0

    page = items[start: start + limit]
    next_token: Optional[str] = None
    if start + limit < len(items):
        raw = str(start + limit).encode()
        next_token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return page, next_token


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def random_private_ip(index: int = 0, base: str = "10.0") -> str:
    third = (index // 253) % 254
    fourth = index % 253 + 1
    return f"{base}.{third}.{fourth}"


def random_public_ip() -> str:
    # Avoid reserved ranges
    first = random.choice([52, 54, 18, 35, 44])
    return f"{first}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"


def random_mac() -> str:
    parts = [0x02] + [random.randint(0, 255) for _ in range(5)]
    return ":".join(f"{b:02x}" for b in parts)


def cidr_to_mask(cidr: str) -> str:
    prefix = int(cidr.split("/")[1])
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> (8 * i)) & 0xFF) for i in [3, 2, 1, 0])


# ---------------------------------------------------------------------------
# EC2 / compute state machines
# ---------------------------------------------------------------------------

EC2_STATES = {
    "pending":      {"code": 0,  "name": "pending"},
    "running":      {"code": 16, "name": "running"},
    "shutting-down":{"code": 32, "name": "shutting-down"},
    "terminated":   {"code": 48, "name": "terminated"},
    "stopping":     {"code": 64, "name": "stopping"},
    "stopped":      {"code": 80, "name": "stopped"},
}

OCI_INSTANCE_STATES = [
    "PROVISIONING", "RUNNING", "STARTING", "STOPPING",
    "STOPPED", "TERMINATING", "TERMINATED",
]

GCP_INSTANCE_STATES = ["PROVISIONING", "STAGING", "RUNNING",
                       "STOPPING", "TERMINATED", "SUSPENDED"]

AZURE_VM_STATES = [
    "creating", "running", "stopping", "stopped",
    "deallocating", "deallocated",
]

# Common instance shapes / types
AWS_INSTANCE_TYPES = [
    "t3.nano", "t3.micro", "t3.small", "t3.medium", "t3.large",
    "m5.large", "m5.xlarge", "m5.2xlarge",
    "c5.large", "c5.xlarge",
    "r5.large", "r5.xlarge",
]

OCI_SHAPES = [
    "VM.Standard.E4.Flex", "VM.Standard3.Flex",
    "VM.Standard.E3.Flex", "VM.Standard2.1",
    "BM.Standard3.64", "BM.HPC2.36",
]

GCP_MACHINE_TYPES = [
    "n1-standard-1", "n1-standard-2", "n1-standard-4",
    "e2-micro", "e2-small", "e2-medium",
    "n2-standard-2", "n2-standard-4",
]

AZURE_VM_SIZES = [
    "Standard_B1s", "Standard_B2s", "Standard_D2s_v3",
    "Standard_D4s_v3", "Standard_F2s_v2",
]


# ---------------------------------------------------------------------------
# Realistic error builders
# ---------------------------------------------------------------------------

def aws_error_xml(code: str, message: str, request_id: Optional[str] = None) -> str:
    """AWS-style XML error response body."""
    rid = request_id or aws_request_id()
    return (
        f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<Error>"
        f"<Code>{code}</Code>"
        f"<Message>{message}</Message>"
        f"<RequestId>{rid}</RequestId>"
        f"<HostId>{uuid.uuid4().hex}</HostId>"
        f"</Error>"
    )


def oci_error(code: str, message: str, status: int = 400) -> Dict:
    return {
        "code": code,
        "message": message,
        "status": status,
        "opc-request-id": oci_request_id(),
    }


def gcp_error(code: int, message: str, status_str: str = "INVALID_ARGUMENT") -> Dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "status": status_str,
            "errors": [{"message": message, "domain": "global", "reason": status_str.lower()}],
        }
    }


def azure_error(code: str, message: str) -> Dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "target": None,
            "details": [],
        }
    }


# ---------------------------------------------------------------------------
# Env resource helpers
# ---------------------------------------------------------------------------

def get_resources(environment) -> Dict:
    """Return oci_resources dict, initialising if None."""
    if environment.oci_resources is None:
        environment.oci_resources = {}
    return environment.oci_resources


def flag_resources_modified(db, environment) -> None:
    """Tell SQLAlchemy the JSON column was mutated in-place."""
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(environment, "oci_resources")
    db.commit()


def find_by_id(items: List[Dict], id_key: str, id_val: str) -> Optional[Dict]:
    return next((i for i in items if i.get(id_key) == id_val), None)


def remove_by_id(items: List[Dict], id_key: str, id_val: str) -> bool:
    original = len(items)
    items[:] = [i for i in items if i.get(id_key) != id_val]
    return len(items) < original
