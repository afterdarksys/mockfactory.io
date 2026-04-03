-- Migration: Add missing columns to users table
-- Date: 2026-02-13

BEGIN;

-- Add hashed_password column for email/password auth
ALTER TABLE users
ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255);

-- Add oauth_user_id for SSO
ALTER TABLE users
ADD COLUMN IF NOT EXISTS oauth_user_id VARCHAR(255) UNIQUE;

CREATE INDEX IF NOT EXISTS idx_users_oauth_user_id ON users(oauth_user_id);

-- Add Stripe billing columns
ALTER TABLE users
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255) UNIQUE;

CREATE INDEX IF NOT EXISTS idx_users_stripe_customer_id ON users(stripe_customer_id);

ALTER TABLE users
ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255) UNIQUE;

CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription_id ON users(stripe_subscription_id);

ALTER TABLE users
ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50);

-- Add updated_at column
ALTER TABLE users
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Drop full_name column if it exists (not in current model)
ALTER TABLE users
DROP COLUMN IF EXISTS full_name;

COMMIT;
