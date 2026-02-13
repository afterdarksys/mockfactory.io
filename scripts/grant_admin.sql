-- Grant Admin/Employee Access to rjc@afterdarksys.com
-- This gives unlimited AI access and marks as After Dark Systems employee

-- Check if user exists first
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE email = 'rjc@afterdarksys.com') THEN
        -- Update existing user
        UPDATE users
        SET
            is_employee = TRUE,
            tier = 'employee',
            is_active = TRUE
        WHERE email = 'rjc@afterdarksys.com';

        RAISE NOTICE 'Admin access granted to rjc@afterdarksys.com';
    ELSE
        -- Create new user with admin access
        INSERT INTO users (
            email,
            oauth_user_id,
            is_active,
            is_employee,
            tier,
            created_at,
            updated_at
        ) VALUES (
            'rjc@afterdarksys.com',
            'sso_rjc_afterdark',  -- Placeholder OAuth ID
            TRUE,
            TRUE,
            'employee',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        );

        RAISE NOTICE 'New admin user created: rjc@afterdarksys.com';
    END IF;
END $$;

-- Verify the changes
SELECT
    id,
    email,
    is_employee,
    tier,
    is_active,
    created_at
FROM users
WHERE email = 'rjc@afterdarksys.com';
