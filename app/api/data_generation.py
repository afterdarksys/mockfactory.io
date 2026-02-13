"""
Data Generation API - Generate and seed fake data into environments
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import mysql.connector
import psycopg2
from psycopg2 import sql
import redis
import boto3
import json
import re

from app.core.database import get_db
from app.models.user import User
from app.models.environment import Environment, EnvironmentStatus
from app.security.auth import get_current_user
from app.services.data_generator import generate_dataset


def validate_sql_identifier(identifier: str, max_length: int = 64) -> str:
    """
    Validate and sanitize SQL identifier (table name, column name, etc.)

    Only allows: alphanumeric characters, underscores
    Maximum length: 64 characters (MySQL/PostgreSQL limit)

    Raises ValueError if invalid
    """
    if not identifier:
        raise ValueError("Identifier cannot be empty")

    if len(identifier) > max_length:
        raise ValueError(f"Identifier too long (max {max_length} characters)")

    # Only allow alphanumeric and underscores
    if not re.match(r'^[a-zA-Z0-9_]+$', identifier):
        raise ValueError(
            f"Invalid identifier '{identifier}'. "
            "Only alphanumeric characters and underscores allowed."
        )

    # Must start with letter or underscore (SQL standard)
    if not re.match(r'^[a-zA-Z_]', identifier):
        raise ValueError(f"Identifier '{identifier}' must start with a letter or underscore")

    return identifier


router = APIRouter()


# Pydantic schemas
class DataGenerationRequest(BaseModel):
    """Request to generate fake data"""
    template: str = Field(..., description="Template name (e.g., 'medical_patients', 'crime_incidents')")
    count: int = Field(default=100, ge=1, le=10000, description="Number of records to generate")
    seed_into: Optional[str] = Field(None, description="Service to seed data into (mysql, postgresql, redis, s3)")
    table_name: Optional[str] = Field(None, description="Table name for database seeding")
    redis_key_prefix: Optional[str] = Field(None, description="Key prefix for Redis seeding")
    s3_bucket: Optional[str] = Field(None, description="S3 bucket for file seeding")


class DataTemplate(BaseModel):
    """Available data template info"""
    name: str
    description: str
    category: str
    fields: List[str]
    estimated_size_kb: int


@router.get("/templates", response_model=List[DataTemplate])
async def list_templates():
    """
    List all available data generation templates
    """
    templates = [
        # Medical
        {
            "name": "medical_patients",
            "description": "Fake patient records with demographics, allergies, and conditions",
            "category": "Medical",
            "fields": ["patient_id", "name", "dob", "blood_type", "insurance", "allergies"],
            "estimated_size_kb": 2
        },
        {
            "name": "medical_appointments",
            "description": "Fake appointment schedules with providers and specialties",
            "category": "Medical",
            "fields": ["appointment_id", "patient_id", "provider", "date", "status"],
            "estimated_size_kb": 1
        },
        {
            "name": "medical_prescriptions",
            "description": "Fake prescriptions with medications and dosages",
            "category": "Medical",
            "fields": ["prescription_id", "patient_id", "medication", "dosage", "frequency"],
            "estimated_size_kb": 1
        },

        # Crime
        {
            "name": "crime_incidents",
            "description": "Fake crime incident reports with locations and evidence",
            "category": "Crime",
            "fields": ["incident_id", "crime_type", "location", "officer", "status"],
            "estimated_size_kb": 3
        },
        {
            "name": "crime_suspects",
            "description": "Fake suspect records with physical descriptions",
            "category": "Crime",
            "fields": ["suspect_id", "name", "description", "prior_arrests", "status"],
            "estimated_size_kb": 2
        },

        # IT
        {
            "name": "it_servers",
            "description": "Fake server inventory with specs and status",
            "category": "IT",
            "fields": ["server_id", "hostname", "ip", "os", "cpu", "ram", "status"],
            "estimated_size_kb": 1
        },
        {
            "name": "it_applications",
            "description": "Fake application inventory with tech stack",
            "category": "IT",
            "fields": ["app_id", "name", "version", "language", "deployment"],
            "estimated_size_kb": 1
        },

        # Threat Intelligence
        {
            "name": "threat_indicators",
            "description": "Fake threat intel with IOCs and malware families",
            "category": "IT Security",
            "fields": ["threat_id", "type", "severity", "indicators", "malware_family"],
            "estimated_size_kb": 3
        },

        # Security
        {
            "name": "security_events",
            "description": "Fake security events and IDS/IPS alerts",
            "category": "IT Security",
            "fields": ["event_id", "timestamp", "type", "severity", "source_ip"],
            "estimated_size_kb": 1
        },
        {
            "name": "security_vulnerabilities",
            "description": "Fake vulnerability scan results with CVEs",
            "category": "IT Security",
            "fields": ["vuln_id", "cve_id", "severity", "cvss_score", "status"],
            "estimated_size_kb": 2
        },

        # Tech Support
        {
            "name": "support_tickets",
            "description": "Fake tech support tickets for Windows/Linux/macOS",
            "category": "Tech Support",
            "fields": ["ticket_id", "user", "issue", "platform", "priority", "status"],
            "estimated_size_kb": 2
        }
    ]

    return templates


@router.post("/{environment_id}/generate")
async def generate_data(
    environment_id: str,
    request: DataGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate fake data and optionally seed into environment services

    Examples:
    - Generate 100 fake patient records: {"template": "medical_patients", "count": 100}
    - Generate and seed into MySQL: {"template": "medical_patients", "count": 100, "seed_into": "mysql", "table_name": "patients"}
    - Generate and save to S3: {"template": "threat_indicators", "count": 500, "seed_into": "s3", "s3_bucket": "test"}
    """
    # Verify environment ownership
    environment = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.user_id == current_user.id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    if environment.status != EnvironmentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Environment must be running to generate data")

    # Generate data
    try:
        result = generate_dataset(request.template, request.count)
        generated_data = result["data"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Seed into service if requested
    seed_result = None
    if request.seed_into:
        try:
            if request.seed_into == "mysql":
                seed_result = await seed_into_mysql(environment, generated_data, request.table_name)
            elif request.seed_into == "postgresql":
                seed_result = await seed_into_postgresql(environment, generated_data, request.table_name)
            elif request.seed_into == "redis":
                seed_result = await seed_into_redis(environment, generated_data, request.redis_key_prefix)
            elif request.seed_into == "s3":
                seed_result = await seed_into_s3(environment, generated_data, request.s3_bucket, request.template)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported seed target: {request.seed_into}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to seed data: {str(e)}")

    return {
        "template": request.template,
        "count": len(generated_data),
        "generated_at": result["generated_at"],
        "seeded_into": request.seed_into,
        "seed_result": seed_result,
        "preview": generated_data[:5] if len(generated_data) > 5 else generated_data
    }


async def seed_into_mysql(environment: Environment, data: List[Dict], table_name: str) -> Dict:
    """Seed generated data into MySQL database - SQL injection safe"""
    if not table_name:
        raise ValueError("table_name required for MySQL seeding")

    # Validate table name to prevent SQL injection
    try:
        table_name = validate_sql_identifier(table_name)
    except ValueError as e:
        raise ValueError(f"Invalid table name: {e}")

    endpoint = environment.endpoints.get("mysql")
    if not endpoint:
        raise ValueError("MySQL service not available in this environment")

    # Parse connection string: mysql://root:mockfactory@localhost:30146/testdb
    # Extract host, port, user, password, database
    parts = endpoint.replace("mysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    conn = mysql.connector.connect(
        host=host_port[0],
        port=int(host_port[1]),
        user=user_pass[0],
        password=user_pass[1],
        database=host_port_db[1]
    )

    cursor = conn.cursor()

    # Create table based on first record keys
    if data:
        # Validate all field names
        fields = data[0].keys()
        validated_fields = []
        for field in fields:
            try:
                validated_fields.append(validate_sql_identifier(field))
            except ValueError:
                raise ValueError(f"Invalid field name: {field}")

        # Build CREATE TABLE with validated identifiers (backticks for MySQL)
        create_sql = f"CREATE TABLE IF NOT EXISTS `{table_name}` ("
        create_sql += ", ".join([f"`{field}` TEXT" for field in validated_fields])
        create_sql += ")"
        cursor.execute(create_sql)

        # Insert data using parameterized queries
        for record in data:
            placeholders = ", ".join(["%s"] * len(validated_fields))
            # Use validated table name with backticks
            insert_sql = f"INSERT INTO `{table_name}` VALUES ({placeholders})"
            # Convert complex fields to JSON
            values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in record.values()]
            cursor.execute(insert_sql, values)

        conn.commit()

    cursor.close()
    conn.close()

    return {
        "table": table_name,
        "records_inserted": len(data)
    }


async def seed_into_postgresql(environment: Environment, data: List[Dict], table_name: str) -> Dict:
    """Seed generated data into PostgreSQL database - SQL injection safe"""
    if not table_name:
        raise ValueError("table_name required for PostgreSQL seeding")

    # Validate table name to prevent SQL injection
    try:
        table_name = validate_sql_identifier(table_name)
    except ValueError as e:
        raise ValueError(f"Invalid table name: {e}")

    endpoint = environment.endpoints.get("postgresql")
    if not endpoint:
        raise ValueError("PostgreSQL service not available in this environment")

    # Parse connection string
    parts = endpoint.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    conn = psycopg2.connect(
        host=host_port[0],
        port=int(host_port[1]),
        user=user_pass[0],
        password=user_pass[1],
        database=host_port_db[1]
    )

    cursor = conn.cursor()

    # Create table
    if data:
        # Validate all field names
        fields = data[0].keys()
        validated_fields = []
        for field in fields:
            try:
                validated_fields.append(validate_sql_identifier(field))
            except ValueError:
                raise ValueError(f"Invalid field name: {field}")

        # Build CREATE TABLE using psycopg2.sql for safe identifier quoting
        create_query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join([
                sql.SQL("{} TEXT").format(sql.Identifier(field))
                for field in validated_fields
            ])
        )
        cursor.execute(create_query)

        # Insert data using parameterized queries
        for record in data:
            placeholders = ", ".join(["%s"] * len(validated_fields))
            # Use sql.Identifier for safe table name quoting
            insert_query = sql.SQL("INSERT INTO {} VALUES ({})").format(
                sql.Identifier(table_name),
                sql.SQL(placeholders)
            )
            values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in record.values()]
            cursor.execute(insert_query, values)

        conn.commit()

    cursor.close()
    conn.close()

    return {
        "table": table_name,
        "records_inserted": len(data)
    }


async def seed_into_redis(environment: Environment, data: List[Dict], key_prefix: str) -> Dict:
    """Seed generated data into Redis - injection safe"""
    if not key_prefix:
        key_prefix = "mockdata"

    # Validate key prefix to prevent Redis command injection
    try:
        key_prefix = validate_sql_identifier(key_prefix, max_length=200)
    except ValueError as e:
        raise ValueError(f"Invalid key prefix: {e}")

    endpoint = environment.endpoints.get("redis")
    if not endpoint:
        raise ValueError("Redis service not available in this environment")

    # Parse: redis://localhost:30145 or redis://:password@localhost:30145
    # Handle passwords in connection string
    redis_url = endpoint.replace("redis://", "")
    if "@" in redis_url:
        # Has password: :password@host:port
        auth_part, host_part = redis_url.split("@")
        password = auth_part.lstrip(":")
        host_port = host_part.split(":")
        r = redis.Redis(
            host=host_port[0],
            port=int(host_port[1]),
            password=password,
            decode_responses=True
        )
    else:
        # No password: host:port
        host_port = redis_url.split(":")
        r = redis.Redis(
            host=host_port[0],
            port=int(host_port[1]),
            decode_responses=True
        )

    # Store each record as a hash
    for i, record in enumerate(data):
        key = f"{key_prefix}:{i}"
        # Flatten nested structures to JSON strings
        flat_record = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in record.items()}
        r.hset(key, mapping=flat_record)

    return {
        "key_pattern": f"{key_prefix}:*",
        "records_inserted": len(data)
    }


async def seed_into_s3(environment: Environment, data: List[Dict], bucket: str, template: str) -> Dict:
    """Seed generated data into S3 as JSON file"""
    if not bucket:
        bucket = "test"

    endpoint = environment.endpoints.get("aws_s3")
    if not endpoint:
        raise ValueError("S3 service not available in this environment")

    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id='mockfactory',
        aws_secret_access_key='mockfactory'
    )

    # Upload as JSON file
    filename = f"mockdata/{template}_{len(data)}_records.json"
    s3.put_object(
        Bucket=bucket,
        Key=filename,
        Body=json.dumps(data, indent=2).encode()
    )

    return {
        "bucket": bucket,
        "file": filename,
        "records": len(data),
        "url": f"{endpoint}/{bucket}/{filename}"
    }
