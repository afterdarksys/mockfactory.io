# MockFactory: Projects & Team Collaboration

**Multi-tenant project structure with team collaboration**

## Hierarchy

```
Customer (Organization)
├── customer_id (UUID)
├── customer_name (e.g., "AfterDark Technologies")
├── subscription_plan (free, pro, enterprise)
│
└── Projects
    ├── Project 1: "staging"
    │   ├── project_id (UUID)
    │   ├── Members
    │   │   ├── alice@afterdark.com (owner)
    │   │   ├── bob@afterdark.com (admin)
    │   │   └── charlie@contractor.com (contributor)
    │   └── Resources
    │       ├── VPCs
    │       ├── Lambda Functions
    │       ├── DynamoDB Tables
    │       └── ...
    │
    └── Project 2: "pr-456"
        ├── project_id (UUID)
        ├── auto_delete_at (2026-02-14T10:00:00Z)
        └── Resources
            └── ...
```

## Data Model

### Customer (Organization)

```json
{
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "customer_name": "AfterDark Technologies",
  "customer_slug": "afterdark",
  "subscription_plan": "pro",
  "billing_email": "billing@afterdark.com",

  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-02-13T10:00:00Z",

  "usage": {
    "api_calls_month": 1234567,
    "cost_month_usd": 123.45,
    "project_count": 15,
    "user_count": 8
  }
}
```

### Project

```json
{
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",

  "name": "staging",
  "description": "Staging environment for testing",
  "slug": "staging",

  "status": "active",
  "auto_delete_at": null,

  "created_by": "user_abc123",
  "created_at": "2026-02-10T10:00:00Z",
  "updated_at": "2026-02-13T10:00:00Z",

  "stats": {
    "resource_count": 15,
    "api_call_count": 1234,
    "cost_usd": 1.23
  },

  "members": [
    {
      "user_id": "user_abc123",
      "email": "alice@afterdark.com",
      "role": "owner",
      "added_at": "2026-02-10T10:00:00Z"
    },
    {
      "user_id": "user_def456",
      "email": "bob@afterdark.com",
      "role": "admin",
      "added_at": "2026-02-11T14:00:00Z",
      "added_by": "user_abc123"
    },
    {
      "user_id": "user_ghi789",
      "email": "charlie@contractor.com",
      "role": "contributor",
      "added_at": "2026-02-12T09:00:00Z",
      "added_by": "user_abc123"
    }
  ]
}
```

### Resource (e.g., VPC)

```json
{
  "vpc_id": "vpc-abc123",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",

  "cidr_block": "10.0.0.0/16",
  "state": "available",

  "created_by": "user_abc123",
  "created_at": "2026-02-10T11:00:00Z",
  "updated_at": "2026-02-13T10:00:00Z",

  "tags": {
    "Name": "staging-vpc",
    "Project": "staging",
    "Owner": "alice@afterdark.com"
  }
}
```

## Database Schema

```sql
-- Customers (Organizations)
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,

    subscription_plan VARCHAR(50) DEFAULT 'free',
    billing_email VARCHAR(255),

    -- Stats
    project_count INT DEFAULT 0,
    user_count INT DEFAULT 0,
    api_calls_month BIGINT DEFAULT 0,
    cost_month_cents BIGINT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_customers_slug ON customers(slug);

-- Customer users (team members)
CREATE TABLE customer_users (
    id BIGSERIAL PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    user_id BIGINT REFERENCES users(id),

    role VARCHAR(50) DEFAULT 'member', -- owner, admin, member

    added_by BIGINT REFERENCES users(id),
    added_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(customer_id, user_id)
);

CREATE INDEX idx_customer_users_customer ON customer_users(customer_id);
CREATE INDEX idx_customer_users_user ON customer_users(user_id);

-- Projects (Environments)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),

    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    description TEXT,

    status VARCHAR(50) DEFAULT 'active',
    auto_delete_at TIMESTAMPTZ,

    -- Creator
    created_by BIGINT REFERENCES users(id),

    -- Stats
    resource_count INT DEFAULT 0,
    api_call_count BIGINT DEFAULT 0,
    cost_cents BIGINT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    UNIQUE(customer_id, slug)
);

CREATE INDEX idx_projects_customer ON projects(customer_id);
CREATE INDEX idx_projects_status ON projects(status);

-- Project members (collaboration)
CREATE TABLE project_members (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    user_id BIGINT REFERENCES users(id),

    role VARCHAR(50) DEFAULT 'contributor', -- owner, admin, contributor, viewer

    added_by BIGINT REFERENCES users(id),
    added_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, user_id)
);

CREATE INDEX idx_project_members_project ON project_members(project_id);
CREATE INDEX idx_project_members_user ON project_members(user_id);

-- Resources now have customer_id AND project_id
ALTER TABLE vpcs ADD COLUMN customer_id UUID REFERENCES customers(id);
ALTER TABLE vpcs ADD COLUMN project_id UUID REFERENCES projects(id);
ALTER TABLE lambda_functions ADD COLUMN customer_id UUID REFERENCES customers(id);
ALTER TABLE lambda_functions ADD COLUMN project_id UUID REFERENCES projects(id);
-- ... same for all resource tables

CREATE INDEX idx_vpcs_project ON vpcs(project_id);
CREATE INDEX idx_lambdas_project ON lambda_functions(project_id);
```

## Roles & Permissions

### Customer-Level Roles

| Role | Create Projects | Manage Billing | Invite Users | Delete Customer |
|------|----------------|----------------|--------------|-----------------|
| **Owner** | ✅ | ✅ | ✅ | ✅ |
| **Admin** | ✅ | ✅ | ✅ | ❌ |
| **Member** | ✅ | ❌ | ❌ | ❌ |

### Project-Level Roles

| Role | Create Resources | Delete Resources | Invite Members | Delete Project |
|------|------------------|------------------|----------------|----------------|
| **Owner** | ✅ | ✅ | ✅ | ✅ |
| **Admin** | ✅ | ✅ | ✅ | ❌ |
| **Contributor** | ✅ | ✅ | ❌ | ❌ |
| **Viewer** | ❌ | ❌ | ❌ | ❌ |

## API Examples

### Create Customer (Sign Up)

```http
POST /api/v1/customers
Content-Type: application/json

{
  "name": "AfterDark Technologies",
  "slug": "afterdark",
  "billing_email": "billing@afterdark.com"
}

Response:
{
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "AfterDark Technologies",
  "slug": "afterdark",
  "subscription_plan": "free",
  "api_key": "mf_550e8400..."
}
```

### Invite User to Customer

```http
POST /api/v1/customers/afterdark/members
Content-Type: application/json
Authorization: Bearer mf_...

{
  "email": "bob@afterdark.com",
  "role": "admin"
}

Response:
{
  "user_id": "user_def456",
  "email": "bob@afterdark.com",
  "role": "admin",
  "invitation_sent": true
}
```

### Create Project

```http
POST /api/v1/customers/afterdark/projects
Content-Type: application/json
Authorization: Bearer mf_...

{
  "name": "staging",
  "description": "Staging environment",
  "auto_delete_after_hours": null
}

Response:
{
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "staging",
  "slug": "staging",
  "status": "active",
  "members": [
    {
      "user_id": "user_abc123",
      "email": "alice@afterdark.com",
      "role": "owner"
    }
  ]
}
```

### Invite User to Project

```http
POST /api/v1/projects/staging/members
Content-Type: application/json
Authorization: Bearer mf_...

{
  "email": "charlie@contractor.com",
  "role": "contributor"
}

Response:
{
  "user_id": "user_ghi789",
  "email": "charlie@contractor.com",
  "role": "contributor",
  "invitation_sent": true
}
```

### Create Resource (scoped to customer + project)

```http
POST /api/v1/aws/vpc
Content-Type: application/json
Authorization: Bearer mf_...
X-MockFactory-Customer: afterdark
X-MockFactory-Project: staging

{
  "Action": "CreateVpc",
  "CidrBlock": "10.0.0.0/16"
}

Response:
{
  "VpcId": "vpc-abc123",
  "CustomerId": "550e8400-e29b-41d4-a716-446655440000",
  "CustomerName": "afterdark",
  "ProjectId": "660e8400-e29b-41d4-a716-446655440001",
  "ProjectName": "staging",
  "CidrBlock": "10.0.0.0/16",
  "State": "available"
}
```

## SDK Updates

```python
from mocklib import MockFactory

# Initialize with customer + project
mf = MockFactory(
    api_key="mf_...",
    customer="afterdark",
    project="staging"
)

# Or use environment variables
# export MOCKFACTORY_API_KEY=mf_...
# export MOCKFACTORY_CUSTOMER=afterdark
# export MOCKFACTORY_PROJECT=staging
mf = MockFactory()

# Customer management
customer = mf.customers.create(
    name="AfterDark Technologies",
    slug="afterdark"
)

# Invite team members to customer
mf.customers.invite_member(
    customer="afterdark",
    email="bob@afterdark.com",
    role="admin"
)

# Project management
project = mf.projects.create(
    name="staging",
    description="Staging environment"
)

# Invite collaborator to project
mf.projects.invite_member(
    project="staging",
    email="charlie@contractor.com",
    role="contributor"
)

# Switch project context
mf.projects.switch("staging")

# Create resources (automatically scoped to customer + project)
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")

# List resources (only shows resources in current project)
vpcs = mf.vpc.list()

# List all projects
projects = mf.projects.list()
for project in projects:
    print(f"{project.name}: {project.resource_count} resources, ${project.cost_usd}")

# Get project details
project = mf.projects.get("staging")
print(f"Members: {len(project.members)}")
for member in project.members:
    print(f"  {member.email} ({member.role})")
```

## CLI Updates

```bash
# Customer management
mocklib customer create afterdark --name "AfterDark Technologies"
mocklib customer invite bob@afterdark.com --role admin

# Project management
mocklib project create staging --customer afterdark
mocklib project list
mocklib project invite charlie@contractor.com --project staging --role contributor

# Set context
export MOCKFACTORY_CUSTOMER=afterdark
export MOCKFACTORY_PROJECT=staging

# Or use flags
mocklib --customer afterdark --project staging mocklib_vpc_create "10.0.0.0/16"

# List projects with stats
mocklib project list --customer afterdark

# Output:
# Projects for afterdark:
# ========================
#
# staging
#   15 resources · 1,234 API calls · $1.23
#   Members: 3 (alice@afterdark.com, bob@afterdark.com, charlie@contractor.com)
#   Created: Feb 10, 2026
#
# pr-456
#   3 resources · 45 API calls · $0.05
#   Auto-deletes in 11 hours
#   Created: Feb 13, 2026
```

## Use Cases

### Use Case 1: Development Team

**AfterDark Technologies** has 5 developers:

```bash
# Alice (owner) creates customer
mocklib customer create afterdark --name "AfterDark Technologies"

# Alice invites team
mocklib customer invite bob@afterdark.com --role admin
mocklib customer invite carol@afterdark.com --role member
mocklib customer invite dave@afterdark.com --role member
mocklib customer invite eve@afterdark.com --role member

# Alice creates shared staging project
mocklib project create staging --customer afterdark

# Alice invites everyone to staging
mocklib project invite bob@afterdark.com --project staging --role admin
mocklib project invite carol@afterdark.com --project staging --role contributor
mocklib project invite dave@afterdark.com --project staging --role contributor

# Bob creates his own dev project
mocklib project create bob-dev --customer afterdark

# Carol works in staging project
export MOCKFACTORY_CUSTOMER=afterdark
export MOCKFACTORY_PROJECT=staging

# Carol creates resources (visible to whole team in staging)
mocklib mocklib_vpc_create "10.0.0.0/16"
mocklib mocklib_lambda_create "api" "python3.9"

# Dave also works in staging (sees Carol's resources)
export MOCKFACTORY_PROJECT=staging
mocklib mocklib_vpc_list
# Shows VPC that Carol created

# Eve creates temporary PR project
mocklib project create pr-789 --customer afterdark --auto-delete-hours 12
export MOCKFACTORY_PROJECT=pr-789
# ... do PR testing ...
# Project auto-deletes after 12 hours
```

### Use Case 2: Agency with Multiple Clients

**Web Agency** manages projects for different clients:

```bash
# Create customer for each client
mocklib customer create client-a --name "Client A Corp"
mocklib customer create client-b --name "Client B Inc"

# Create projects for Client A
mocklib --customer client-a project create staging
mocklib --customer client-a project create production

# Create projects for Client B
mocklib --customer client-b project create staging
mocklib --customer client-b project create production

# Invite clients to their own projects
mocklib --customer client-a project invite client@clienta.com --project production --role viewer

# Resources are completely isolated by customer
mocklib --customer client-a --project staging mocklib_vpc_create "10.0.0.0/16"
mocklib --customer client-b --project staging mocklib_vpc_create "10.0.0.0/16"
# Different VPCs, no conflicts!

# Billing is per customer
mocklib customer usage client-a
# Shows: $123.45 this month

mocklib customer usage client-b
# Shows: $67.89 this month
```

### Use Case 3: Contractor Access

**Temporary access for contractors**:

```python
# Invite contractor to specific project only
mf.projects.invite_member(
    project="feature-redesign",
    email="contractor@freelance.com",
    role="contributor"
)

# Contractor can only access this project
# When project is done, delete it
mf.projects.delete("feature-redesign")

# Contractor automatically loses access
```

## Dashboard UI

### Customer Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ AfterDark Technologies                            [Settings] │
│                                                              │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│ │ Projects      │ │ API Calls     │ │ Cost (MTD)    │      │
│ │ 15            │ │ 1.2M          │ │ $123.45       │      │
│ └───────────────┘ └───────────────┘ └───────────────┘      │
│                                                              │
│ ═══════════════════════════════════════════════════════════ │
│                                                              │
│ Team Members (8)                           [+ Invite Member] │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ alice@afterdark.com              Owner        [Remove]   ││
│ │ bob@afterdark.com                Admin        [Remove]   ││
│ │ carol@afterdark.com              Member       [Remove]   ││
│ │ ...                                                       ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ Projects (15)                                [+ New Project] │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ staging                    15 resources       $1.23      ││
│ │ 3 members · 1,234 API calls                              ││
│ │ [View] [Settings]                                        ││
│ ├──────────────────────────────────────────────────────────┤│
│ │ pr-456                     3 resources        $0.05      ││
│ │ Auto-deletes in 11 hours                                 ││
│ │ [View] [Delete]                                          ││
│ └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Project Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ AfterDark / staging                          [Edit] [Delete] │
│                                                              │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│ │ Resources     │ │ API Calls     │ │ Cost          │      │
│ │ 15            │ │ 1,234         │ │ $1.23         │      │
│ └───────────────┘ └───────────────┘ └───────────────┘      │
│                                                              │
│ Members (3)                                  [+ Invite]      │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ alice@afterdark.com         Owner                        ││
│ │ bob@afterdark.com           Admin         [Remove]       ││
│ │ charlie@contractor.com      Contributor   [Remove]       ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ Resources                                                    │
│ [VPCs] [Lambda] [DynamoDB] [SQS] [Storage]                  │
│                                                              │
│ VPCs (2)                                                     │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ vpc-abc123        10.0.0.0/16        available           ││
│ │ Created by alice@afterdark.com on Feb 10, 2026           ││
│ │ [View] [Delete]                                          ││
│ └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Summary

**Key Improvements**:

1. ✅ **Multi-tenancy**: Customers can have multiple projects
2. ✅ **Team Collaboration**: Invite users to customers and projects
3. ✅ **Role-Based Access**: Owner, Admin, Contributor, Viewer
4. ✅ **Resource Isolation**: Resources scoped to customer + project
5. ✅ **Cost Tracking**: Per-project and per-customer usage
6. ✅ **Contractor Support**: Temporary project access

**This makes MockFactory enterprise-ready!** 🚀
