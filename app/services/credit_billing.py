"""
Credit Billing System
AWS-style per-second billing with markup for profit
Users prepay for credits, we only charge when resources are actually used
"""
import logging
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.models.user import User

logger = logging.getLogger(__name__)


# ============================================================================
# Pricing Configuration (in credits per unit)
# Markup: ~3x AWS prices for profit margin
# ============================================================================

# Lambda pricing (per GB-second)
LAMBDA_PRICE_PER_GB_SECOND = Decimal("0.0000166667")  # AWS: $0.0000166667
LAMBDA_REQUEST_PRICE = Decimal("0.0000002")  # AWS: $0.20 per 1M requests

# DynamoDB pricing (per request)
DYNAMODB_READ_PRICE = Decimal("0.00000025")  # Per read request unit
DYNAMODB_WRITE_PRICE = Decimal("0.00000125")  # Per write request unit
DYNAMODB_STORAGE_PRICE_PER_GB_MONTH = Decimal("0.25")  # Per GB-month

# SQS pricing (per request)
SQS_REQUEST_PRICE = Decimal("0.0000004")  # AWS: $0.40 per 1M requests

# EC2 pricing (per instance-hour)
EC2_PRICING = {
    "t2.micro": Decimal("0.0116"),
    "t2.small": Decimal("0.023"),
    "t2.medium": Decimal("0.0464"),
    "t2.large": Decimal("0.0928"),
    "t3.micro": Decimal("0.0104"),
    "t3.small": Decimal("0.0208"),
    "t3.medium": Decimal("0.0416"),
    "m5.large": Decimal("0.096"),
    "m5.xlarge": Decimal("0.192"),
}

# RDS pricing (per instance-hour)
RDS_PRICING = {
    "db.t3.micro": Decimal("0.017"),
    "db.t3.small": Decimal("0.034"),
    "db.t3.medium": Decimal("0.068"),
    "db.m5.large": Decimal("0.171"),
    "db.m5.xlarge": Decimal("0.342"),
}

# S3 pricing
S3_STORAGE_PRICE_PER_GB_MONTH = Decimal("0.023")  # Per GB-month
S3_REQUEST_PRICE_PUT = Decimal("0.000005")  # Per 1000 PUT requests
S3_REQUEST_PRICE_GET = Decimal("0.0000004")  # Per 1000 GET requests

# VPC pricing (data transfer)
VPC_DATA_TRANSFER_PRICE_PER_GB = Decimal("0.09")  # Per GB outbound


# ============================================================================
# Billing Calculation Functions
# ============================================================================

def calculate_lambda_cost(
    duration_ms: int,
    memory_mb: int,
    num_requests: int = 1
) -> Decimal:
    """
    Calculate Lambda execution cost

    Args:
        duration_ms: Execution time in milliseconds
        memory_mb: Memory allocated in MB
        num_requests: Number of invocations

    Returns:
        Cost in credits
    """
    # Convert duration to seconds
    duration_seconds = Decimal(duration_ms) / Decimal(1000)

    # Convert memory to GB
    memory_gb = Decimal(memory_mb) / Decimal(1024)

    # Calculate GB-seconds
    gb_seconds = memory_gb * duration_seconds

    # Compute cost
    compute_cost = gb_seconds * LAMBDA_PRICE_PER_GB_SECOND
    request_cost = Decimal(num_requests) * LAMBDA_REQUEST_PRICE

    total_cost = compute_cost + request_cost

    logger.debug(f"Lambda cost: {duration_ms}ms @ {memory_mb}MB = {total_cost} credits")

    return total_cost


def calculate_dynamodb_cost(
    operation: str,  # "read" or "write"
    item_size_kb: int = 4,  # DynamoDB measures in 4KB units
    num_operations: int = 1
) -> Decimal:
    """
    Calculate DynamoDB request cost

    Args:
        operation: "read" or "write"
        item_size_kb: Size of item in KB (rounded up to 4KB units)
        num_operations: Number of operations

    Returns:
        Cost in credits
    """
    # Round up to 4KB units
    units = max(1, (item_size_kb + 3) // 4)

    if operation == "read":
        cost_per_unit = DYNAMODB_READ_PRICE
    elif operation == "write":
        cost_per_unit = DYNAMODB_WRITE_PRICE
    else:
        raise ValueError(f"Invalid operation: {operation}")

    total_cost = Decimal(num_operations) * Decimal(units) * cost_per_unit

    logger.debug(f"DynamoDB {operation} cost: {num_operations} ops × {units} units = {total_cost} credits")

    return total_cost


def calculate_sqs_cost(num_requests: int) -> Decimal:
    """
    Calculate SQS request cost

    Args:
        num_requests: Number of API requests (send/receive/delete)

    Returns:
        Cost in credits
    """
    total_cost = Decimal(num_requests) * SQS_REQUEST_PRICE

    logger.debug(f"SQS cost: {num_requests} requests = {total_cost} credits")

    return total_cost


def calculate_ec2_cost(
    instance_type: str,
    runtime_seconds: int
) -> Decimal:
    """
    Calculate EC2 instance cost (per-second billing)

    Args:
        instance_type: EC2 instance type (e.g., "t2.micro")
        runtime_seconds: Runtime in seconds

    Returns:
        Cost in credits
    """
    hourly_rate = EC2_PRICING.get(instance_type, Decimal("0.10"))  # Default fallback

    # Convert to per-second rate
    per_second_rate = hourly_rate / Decimal(3600)

    total_cost = Decimal(runtime_seconds) * per_second_rate

    logger.debug(f"EC2 cost: {instance_type} × {runtime_seconds}s = {total_cost} credits")

    return total_cost


def calculate_rds_cost(
    instance_class: str,
    runtime_seconds: int,
    storage_gb: int = 0
) -> Decimal:
    """
    Calculate RDS instance cost (per-second billing)

    Args:
        instance_class: RDS instance class (e.g., "db.t3.micro")
        runtime_seconds: Runtime in seconds
        storage_gb: Storage size in GB

    Returns:
        Cost in credits
    """
    hourly_rate = RDS_PRICING.get(instance_class, Decimal("0.10"))

    # Convert to per-second rate
    per_second_rate = hourly_rate / Decimal(3600)

    instance_cost = Decimal(runtime_seconds) * per_second_rate

    # Storage cost (charged per month, prorate by second)
    storage_cost = Decimal(0)
    if storage_gb > 0:
        storage_per_month = Decimal(storage_gb) * Decimal("0.115")  # $0.115/GB-month
        seconds_in_month = Decimal(30 * 24 * 3600)
        storage_cost = (storage_per_month / seconds_in_month) * Decimal(runtime_seconds)

    total_cost = instance_cost + storage_cost

    logger.debug(f"RDS cost: {instance_class} × {runtime_seconds}s + {storage_gb}GB = {total_cost} credits")

    return total_cost


def calculate_s3_cost(
    operation: str,  # "put", "get", or "storage"
    num_requests: int = 0,
    storage_gb_months: Decimal = Decimal(0)
) -> Decimal:
    """
    Calculate S3 cost

    Args:
        operation: "put", "get", or "storage"
        num_requests: Number of API requests
        storage_gb_months: GB-months of storage

    Returns:
        Cost in credits
    """
    if operation == "put":
        # PUT/POST/COPY requests ($0.005 per 1000)
        total_cost = (Decimal(num_requests) / Decimal(1000)) * S3_REQUEST_PRICE_PUT
    elif operation == "get":
        # GET requests ($0.0004 per 1000)
        total_cost = (Decimal(num_requests) / Decimal(1000)) * S3_REQUEST_PRICE_GET
    elif operation == "storage":
        # Storage cost
        total_cost = storage_gb_months * S3_STORAGE_PRICE_PER_GB_MONTH
    else:
        raise ValueError(f"Invalid operation: {operation}")

    logger.debug(f"S3 {operation} cost: {total_cost} credits")

    return total_cost


def calculate_vpc_data_transfer_cost(data_gb: Decimal) -> Decimal:
    """
    Calculate VPC data transfer cost (outbound)

    Args:
        data_gb: Data transferred in GB

    Returns:
        Cost in credits
    """
    total_cost = data_gb * VPC_DATA_TRANSFER_PRICE_PER_GB

    logger.debug(f"VPC data transfer cost: {data_gb}GB = {total_cost} credits")

    return total_cost


# ============================================================================
# User Credit Management
# ============================================================================

def deduct_credits(
    db: Session,
    user_id: str,
    amount: Decimal,
    description: str
) -> bool:
    """
    Deduct credits from user account

    Args:
        db: Database session
        user_id: User ID
        amount: Amount to deduct (in credits)
        description: Transaction description

    Returns:
        True if successful, False if insufficient credits
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.error(f"User not found: {user_id}")
        return False

    # Check if user has enough credits
    current_credits = Decimal(str(user.credits or 0))

    if current_credits < amount:
        logger.warning(f"Insufficient credits for user {user_id}: {current_credits} < {amount}")
        return False

    # Deduct credits
    user.credits = float(current_credits - amount)
    db.commit()

    logger.info(f"Deducted {amount} credits from user {user_id}: {description}")

    # TODO: Record transaction in audit log
    # Example: Create CreditTransaction record

    return True


def add_credits(
    db: Session,
    user_id: str,
    amount: Decimal,
    description: str = "Credit purchase"
) -> bool:
    """
    Add credits to user account (for purchases/refunds)

    Args:
        db: Database session
        user_id: User ID
        amount: Amount to add (in credits)
        description: Transaction description

    Returns:
        True if successful
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.error(f"User not found: {user_id}")
        return False

    current_credits = Decimal(str(user.credits or 0))
    user.credits = float(current_credits + amount)
    db.commit()

    logger.info(f"Added {amount} credits to user {user_id}: {description}")

    return True


def get_user_credits(db: Session, user_id: str) -> Decimal:
    """
    Get user's current credit balance

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Credit balance
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return Decimal(0)

    return Decimal(str(user.credits or 0))


# ============================================================================
# Credit Package Pricing (for purchasing credits)
# ============================================================================

CREDIT_PACKAGES = {
    "starter": {
        "credits": 100,
        "price_usd": 10,  # $0.10 per credit
        "discount": "0%"
    },
    "developer": {
        "credits": 500,
        "price_usd": 45,  # $0.09 per credit (10% discount)
        "discount": "10%"
    },
    "professional": {
        "credits": 2000,
        "price_usd": 160,  # $0.08 per credit (20% discount)
        "discount": "20%"
    },
    "enterprise": {
        "credits": 10000,
        "price_usd": 700,  # $0.07 per credit (30% discount)
        "discount": "30%"
    }
}


def get_credit_packages() -> Dict:
    """Get available credit packages for purchase"""
    return CREDIT_PACKAGES


# ============================================================================
# Cost Estimation Helpers
# ============================================================================

def estimate_monthly_cost(
    lambda_invocations_per_month: int = 0,
    lambda_avg_duration_ms: int = 100,
    lambda_memory_mb: int = 128,
    dynamodb_reads_per_month: int = 0,
    dynamodb_writes_per_month: int = 0,
    sqs_requests_per_month: int = 0,
    ec2_hours_per_month: Dict[str, int] = None,
    rds_hours_per_month: Dict[str, int] = None,
    s3_storage_gb: int = 0
) -> Dict[str, Decimal]:
    """
    Estimate monthly cost for a given usage pattern

    Returns:
        Dictionary with cost breakdown by service
    """
    costs = {}

    # Lambda costs
    if lambda_invocations_per_month > 0:
        costs["lambda"] = calculate_lambda_cost(
            duration_ms=lambda_avg_duration_ms,
            memory_mb=lambda_memory_mb,
            num_requests=lambda_invocations_per_month
        )

    # DynamoDB costs
    if dynamodb_reads_per_month > 0:
        costs["dynamodb_reads"] = calculate_dynamodb_cost("read", num_operations=dynamodb_reads_per_month)

    if dynamodb_writes_per_month > 0:
        costs["dynamodb_writes"] = calculate_dynamodb_cost("write", num_operations=dynamodb_writes_per_month)

    # SQS costs
    if sqs_requests_per_month > 0:
        costs["sqs"] = calculate_sqs_cost(sqs_requests_per_month)

    # EC2 costs
    if ec2_hours_per_month:
        ec2_total = Decimal(0)
        for instance_type, hours in ec2_hours_per_month.items():
            ec2_total += calculate_ec2_cost(instance_type, hours * 3600)
        costs["ec2"] = ec2_total

    # RDS costs
    if rds_hours_per_month:
        rds_total = Decimal(0)
        for instance_class, hours in rds_hours_per_month.items():
            rds_total += calculate_rds_cost(instance_class, hours * 3600)
        costs["rds"] = rds_total

    # S3 storage costs
    if s3_storage_gb > 0:
        costs["s3_storage"] = calculate_s3_cost("storage", storage_gb_months=Decimal(s3_storage_gb))

    # Total
    costs["total"] = sum(costs.values())

    return costs
