-- Migration: Add Cloud Resource Tables
-- Adds support for AWS, GCP, Azure resource emulation

-- ============================================================================
-- AWS Resources
-- ============================================================================

CREATE TABLE IF NOT EXISTS mock_ec2_instances (
    id VARCHAR PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    instance_type VARCHAR NOT NULL,
    ami_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    public_ip VARCHAR,
    private_ip VARCHAR NOT NULL,
    vpc_id VARCHAR,
    subnet_id VARCHAR,
    security_groups JSONB DEFAULT '[]',
    tags JSONB DEFAULT '{}',
    user_data TEXT,
    docker_container_id VARCHAR,
    launch_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    terminated_time TIMESTAMP
);

CREATE INDEX idx_ec2_environment ON mock_ec2_instances(environment_id);
CREATE INDEX idx_ec2_state ON mock_ec2_instances(state);

CREATE TABLE IF NOT EXISTS mock_s3_buckets (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    bucket_name VARCHAR UNIQUE NOT NULL,
    region VARCHAR DEFAULT 'us-east-1',
    versioning_enabled BOOLEAN DEFAULT FALSE,
    oci_bucket_name VARCHAR,
    oci_namespace VARCHAR,
    tags JSONB DEFAULT '{}',
    total_objects INTEGER DEFAULT 0,
    total_size_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_s3_bucket_name ON mock_s3_buckets(bucket_name);
CREATE INDEX idx_s3_environment ON mock_s3_buckets(environment_id);

CREATE TABLE IF NOT EXISTS mock_s3_objects (
    id SERIAL PRIMARY KEY,
    bucket_id INTEGER NOT NULL REFERENCES mock_s3_buckets(id) ON DELETE CASCADE,
    key VARCHAR NOT NULL,
    size_bytes BIGINT NOT NULL,
    etag VARCHAR NOT NULL,
    storage_class VARCHAR DEFAULT 'STANDARD',
    oci_object_name VARCHAR,
    metadata JSONB DEFAULT '{}',
    content_type VARCHAR,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bucket_id, key)
);

CREATE INDEX idx_s3_object_key ON mock_s3_objects(bucket_id, key);

CREATE TABLE IF NOT EXISTS mock_lambda_functions (
    id VARCHAR PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    function_name VARCHAR NOT NULL,
    runtime VARCHAR NOT NULL,
    handler VARCHAR NOT NULL,
    memory_mb INTEGER DEFAULT 128,
    timeout_seconds INTEGER DEFAULT 3,
    code_s3_bucket VARCHAR,
    code_s3_key VARCHAR,
    code_sha256 VARCHAR,
    docker_image VARCHAR,
    env_vars JSONB DEFAULT '{}',
    role_arn VARCHAR,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lambda_environment ON mock_lambda_functions(environment_id);
CREATE INDEX idx_lambda_name ON mock_lambda_functions(function_name);

CREATE TABLE IF NOT EXISTS mock_rds_instances (
    id VARCHAR PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    db_instance_identifier VARCHAR UNIQUE NOT NULL,
    engine VARCHAR NOT NULL,
    engine_version VARCHAR NOT NULL,
    db_instance_class VARCHAR NOT NULL,
    allocated_storage_gb INTEGER NOT NULL,
    master_username VARCHAR NOT NULL,
    master_password VARCHAR NOT NULL,
    database_name VARCHAR,
    port INTEGER NOT NULL,
    endpoint_address VARCHAR,
    endpoint_port INTEGER,
    postgres_container_id VARCHAR,
    status VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rds_environment ON mock_rds_instances(environment_id);
CREATE INDEX idx_rds_identifier ON mock_rds_instances(db_instance_identifier);

-- ============================================================================
-- GCP Resources
-- ============================================================================

CREATE TABLE IF NOT EXISTS mock_gcp_compute_instances (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    zone VARCHAR NOT NULL,
    machine_type VARCHAR NOT NULL,
    external_ip VARCHAR,
    internal_ip VARCHAR NOT NULL,
    labels JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    status VARCHAR NOT NULL,
    docker_container_id VARCHAR,
    creation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_gcp_compute_environment ON mock_gcp_compute_instances(environment_id);
CREATE INDEX idx_gcp_compute_name ON mock_gcp_compute_instances(name);

CREATE TABLE IF NOT EXISTS mock_gcp_storage_buckets (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    name VARCHAR UNIQUE NOT NULL,
    location VARCHAR DEFAULT 'US',
    storage_class VARCHAR DEFAULT 'STANDARD',
    oci_bucket_name VARCHAR,
    labels JSONB DEFAULT '{}',
    time_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_gcp_storage_environment ON mock_gcp_storage_buckets(environment_id);
CREATE INDEX idx_gcp_storage_name ON mock_gcp_storage_buckets(name);

-- ============================================================================
-- Azure Resources
-- ============================================================================

CREATE TABLE IF NOT EXISTS mock_azure_vms (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    vm_name VARCHAR NOT NULL,
    resource_group VARCHAR NOT NULL,
    location VARCHAR NOT NULL,
    vm_size VARCHAR NOT NULL,
    public_ip_address VARCHAR,
    private_ip_address VARCHAR NOT NULL,
    os_type VARCHAR NOT NULL,
    image_reference JSONB,
    provisioning_state VARCHAR DEFAULT 'Creating',
    power_state VARCHAR DEFAULT 'running',
    docker_container_id VARCHAR,
    tags JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_azure_vm_environment ON mock_azure_vms(environment_id);
CREATE INDEX idx_azure_vm_name ON mock_azure_vms(vm_name);

CREATE TABLE IF NOT EXISTS mock_azure_blob_storage (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    account_name VARCHAR UNIQUE NOT NULL,
    location VARCHAR NOT NULL,
    kind VARCHAR DEFAULT 'StorageV2',
    oci_bucket_name VARCHAR,
    tags JSONB DEFAULT '{}',
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_azure_blob_environment ON mock_azure_blob_storage(environment_id);
CREATE INDEX idx_azure_blob_account ON mock_azure_blob_storage(account_name);

-- ============================================================================
-- Add indexes for performance
-- ============================================================================

-- Composite indexes for common queries
CREATE INDEX idx_ec2_env_state ON mock_ec2_instances(environment_id, state);
CREATE INDEX idx_s3_bucket_env_name ON mock_s3_buckets(environment_id, bucket_name);
CREATE INDEX idx_lambda_env_name ON mock_lambda_functions(environment_id, function_name);

-- Done
SELECT 'Cloud resource tables created successfully!' AS status;
