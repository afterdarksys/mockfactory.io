-- MockFactory AI Usage Tracking Table
-- Run this on your production database

BEGIN;

-- Create ai_usage table
CREATE TABLE IF NOT EXISTS ai_usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    model VARCHAR NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    api_cost FLOAT NOT NULL,
    user_cost FLOAT NOT NULL,
    profit FLOAT NOT NULL,
    session_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_ai_usage_id ON ai_usage(id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_user_id ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created_at ON ai_usage(created_at);

-- Grant admin access to rjc@afterdarksys.com
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE email = 'rjc@afterdarksys.com') THEN
        UPDATE users
        SET is_employee = TRUE, tier = 'employee', is_active = TRUE
        WHERE email = 'rjc@afterdarksys.com';
        RAISE NOTICE 'Admin access granted to rjc@afterdarksys.com';
    ELSE
        INSERT INTO users (email, oauth_user_id, is_active, is_employee, tier, created_at, updated_at)
        VALUES ('rjc@afterdarksys.com', 'sso_rjc', TRUE, TRUE, 'employee', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        RAISE NOTICE 'Admin user created: rjc@afterdarksys.com';
    END IF;
END $$;

COMMIT;

-- Verify
SELECT
    'ai_usage table' as object,
    COUNT(*) as row_count
FROM ai_usage
UNION ALL
SELECT
    'admin user' as object,
    CASE WHEN is_employee THEN 1 ELSE 0 END as row_count
FROM users
WHERE email = 'rjc@afterdarksys.com';
