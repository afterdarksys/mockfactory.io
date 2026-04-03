# MockFactory Environments

**Isolated, named environments for organized cloud resource mocking.**

## Concept

Each **environment** is an isolated namespace containing related resources. Think of it like:
- AWS accounts (but lightweight and instant)
- Kubernetes namespaces
- Docker Compose projects

**Key Features**:
- **Named**: Human-readable names like `"staging"`, `"pr-456"`, `"dev-alice"`
- **UUID**: Each environment has a unique ID for API isolation
- **Scoped**: All resources belong to an environment
- **Disposable**: Delete environment = delete all resources
- **Cost Tracking**: Track costs per environment
- **Concurrent**: Multiple environments run in parallel

## Use Cases

### Use Case 1: Multi-Developer Team

**Without Environments**:
```python
# Alice
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")  # Creates vpc-abc123

# Bob (5 minutes later)
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")  # Creates vpc-def456
vpcs = mf.vpc.list()  # Sees both Alice's and Bob's VPCs! Confusion!
```

**With Environments**:
```python
# Alice
mf = MockFactory(api_key="mf_...", environment="alice-dev")
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")  # Isolated to alice-dev

# Bob
mf = MockFactory(api_key="mf_...", environment="bob-dev")
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")  # Isolated to bob-dev
vpcs = mf.vpc.list()  # Only sees Bob's resources
```

### Use Case 2: CI/CD per Pull Request

```yaml
# .github/workflows/test.yml
env:
  # Unique environment per PR
  MOCKFACTORY_ENVIRONMENT: "pr-${{ github.event.pull_request.number }}"

steps:
  - name: Setup test infrastructure
    run: |
      mocklib env create "pr-${{ github.event.pull_request.number }}"

      # All resources created in this environment
      VPC=$(mocklib mocklib_vpc_create "10.0.0.0/16")
      LAMBDA=$(mocklib mocklib_lambda_create "api" "python3.9")

  - name: Run tests
    run: pytest tests/

  - name: Cleanup
    if: always()
    run: |
      # Deletes ALL resources in environment
      mocklib env delete "pr-${{ github.event.pull_request.number }}"
```

**Benefits**:
- ✅ Parallel PR tests don't interfere
- ✅ Single command cleanup
- ✅ Cost tracking per PR

### Use Case 3: Long-Running Test Environments

```bash
# Create staging environment
mocklib env create staging

# Use it
export MOCKFACTORY_ENVIRONMENT=staging

# Setup infrastructure
mocklib mocklib_vpc_create "10.0.0.0/16"
mocklib mocklib_lambda_create "api" "python3.9"
mocklib mocklib_dynamodb_create_table "users" "id"

# Environment persists across sessions
# (until explicitly deleted)

# Days later, continue using it
export MOCKFACTORY_ENVIRONMENT=staging
mocklib mocklib_lambda_invoke "api" '{"test": "data"}'

# When done
mocklib env delete staging
```

### Use Case 4: Cost Tracking

```python
# Get environment usage
env = mf.environments.get("staging")

print(f"API Calls: {env.api_call_count}")
print(f"Cost: ${env.cost_usd}")
print(f"Created: {env.created_at}")
print(f"Resources: {env.resource_count}")

# List all environments with costs
environments = mf.environments.list()
for env in environments:
    print(f"{env.name}: ${env.cost_usd}")
```

## Implementation

### Database Schema

```sql
-- Environments table
CREATE TABLE environments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(id),

    -- Naming
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Status
    status VARCHAR(50) DEFAULT 'active', -- active, deleted
    auto_delete_at TIMESTAMPTZ,  -- Optional: auto-cleanup

    -- Stats
    resource_count INT DEFAULT 0,
    api_call_count BIGINT DEFAULT 0,
    cost_cents BIGINT DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    -- Unique per user
    UNIQUE(user_id, name)
);

CREATE INDEX idx_environments_user ON environments(user_id);
CREATE INDEX idx_environments_status ON environments(status);

-- Add environment_id to all resource tables
ALTER TABLE vpcs ADD COLUMN environment_id UUID REFERENCES environments(id);
ALTER TABLE lambda_functions ADD COLUMN environment_id UUID REFERENCES environments(id);
ALTER TABLE dynamodb_tables ADD COLUMN environment_id UUID REFERENCES environments(id);
ALTER TABLE sqs_queues ADD COLUMN environment_id UUID REFERENCES environments(id);
ALTER TABLE storage_buckets ADD COLUMN environment_id UUID REFERENCES environments(id);

-- Indexes for fast lookups
CREATE INDEX idx_vpcs_environment ON vpcs(environment_id);
CREATE INDEX idx_lambdas_environment ON lambda_functions(environment_id);
CREATE INDEX idx_dynamodb_environment ON dynamodb_tables(environment_id);
CREATE INDEX idx_sqs_environment ON sqs_queues(environment_id);
CREATE INDEX idx_storage_environment ON storage_buckets(environment_id);

-- Environment resource tracking
CREATE TABLE environment_resources (
    id BIGSERIAL PRIMARY KEY,
    environment_id UUID REFERENCES environments(id),

    resource_type VARCHAR(50), -- vpc, lambda, dynamodb, sqs, storage
    resource_id VARCHAR(255),
    resource_data JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_env_resources ON environment_resources(environment_id);
```

### API Changes

**Create Environment**:
```http
POST /api/v1/environments
Content-Type: application/json
Authorization: Bearer mf_...

{
  "name": "staging",
  "description": "Staging environment for testing",
  "auto_delete_after_hours": 24
}

Response:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "staging",
  "description": "Staging environment for testing",
  "status": "active",
  "resource_count": 0,
  "api_call_count": 0,
  "cost_usd": 0.0,
  "created_at": "2026-02-13T10:00:00Z",
  "auto_delete_at": "2026-02-14T10:00:00Z"
}
```

**List Environments**:
```http
GET /api/v1/environments
Authorization: Bearer mf_...

Response:
{
  "environments": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "staging",
      "status": "active",
      "resource_count": 15,
      "api_call_count": 1234,
      "cost_usd": 1.23,
      "created_at": "2026-02-13T10:00:00Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "pr-456",
      "status": "active",
      "resource_count": 3,
      "api_call_count": 45,
      "cost_usd": 0.05,
      "created_at": "2026-02-13T11:00:00Z",
      "auto_delete_at": "2026-02-13T23:00:00Z"
    }
  ]
}
```

**Delete Environment** (cascades to all resources):
```http
DELETE /api/v1/environments/staging
Authorization: Bearer mf_...

Response:
{
  "success": true,
  "deleted_resources": {
    "vpcs": 2,
    "lambda_functions": 5,
    "dynamodb_tables": 3,
    "sqs_queues": 4,
    "storage_buckets": 1
  },
  "total_resources_deleted": 15
}
```

**Create Resource in Environment**:
```http
POST /api/v1/aws/vpc
Content-Type: application/json
Authorization: Bearer mf_...
X-MockFactory-Environment: staging

{
  "Action": "CreateVpc",
  "CidrBlock": "10.0.0.0/16"
}

Response includes environment:
{
  "VpcId": "vpc-abc123",
  "EnvironmentId": "550e8400-e29b-41d4-a716-446655440000",
  "EnvironmentName": "staging",
  ...
}
```

### SDK Updates

**Python SDK**:

```python
# mocklib/client.py

class MockFactory:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = "https://api.mockfactory.io/v1",
        environment: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("MOCKFACTORY_API_KEY")
        self.environment = environment or os.getenv("MOCKFACTORY_ENVIRONMENT")

        # If no environment specified, create a default one
        if not self.environment:
            self.environment = "default"

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "X-MockFactory-Environment": self.environment,
            "Content-Type": "application/json",
        })

        # Environment management
        self.environments = EnvironmentManager(self)

        # Resources
        self.vpc = VPCResource(self)
        self.lambda_function = LambdaResource(self)
        # ...

class EnvironmentManager:
    def __init__(self, client):
        self.client = client

    def create(
        self,
        name: str,
        description: str = None,
        auto_delete_after_hours: int = None
    ) -> Environment:
        """Create a new environment"""
        response = self.client.post("/environments", json={
            "name": name,
            "description": description,
            "auto_delete_after_hours": auto_delete_after_hours,
        })

        return Environment(
            id=response["id"],
            name=response["name"],
            description=response.get("description"),
            status=response["status"],
            resource_count=response["resource_count"],
            api_call_count=response["api_call_count"],
            cost_usd=response["cost_usd"],
            created_at=response["created_at"],
            auto_delete_at=response.get("auto_delete_at"),
        )

    def get(self, name: str) -> Environment:
        """Get environment by name"""
        response = self.client.get(f"/environments/{name}")
        return Environment(**response)

    def list(self) -> List[Environment]:
        """List all environments"""
        response = self.client.get("/environments")
        return [Environment(**env) for env in response["environments"]]

    def delete(self, name: str) -> Dict:
        """Delete environment and all its resources"""
        return self.client.delete(f"/environments/{name}")

    def switch(self, name: str):
        """Switch to a different environment"""
        self.client.environment = name
        self.client.session.headers["X-MockFactory-Environment"] = name
```

**Usage Examples**:

```python
from mocklib import MockFactory

# Option 1: Specify environment in constructor
mf = MockFactory(api_key="mf_...", environment="staging")

# Option 2: Use environment variable
# export MOCKFACTORY_ENVIRONMENT=staging
mf = MockFactory(api_key="mf_...")

# Option 3: Create environment programmatically
mf = MockFactory(api_key="mf_...")
env = mf.environments.create(
    name="pr-456",
    description="Test environment for PR #456",
    auto_delete_after_hours=12
)

# Switch to the environment
mf.environments.switch("pr-456")

# Create resources (automatically scoped to environment)
vpc = mf.vpc.create(cidr_block="10.0.0.0/16")
lambda_fn = mf.lambda_function.create(
    name="api",
    runtime="python3.9"
)

# List resources (only shows resources in current environment)
vpcs = mf.vpc.list()  # Only VPCs in pr-456 environment

# Get environment info
env = mf.environments.get("pr-456")
print(f"Resources: {env.resource_count}")
print(f"Cost: ${env.cost_usd}")

# Cleanup - delete environment and ALL resources
mf.environments.delete("pr-456")
```

### CLI Updates

```bash
# Environment management commands
mocklib env create <name> [--description "..."] [--auto-delete-hours 24]
mocklib env list
mocklib env get <name>
mocklib env delete <name>
mocklib env switch <name>  # Set default for subsequent commands

# Set environment via flag
mocklib --env staging mocklib_vpc_create "10.0.0.0/16"

# Or via environment variable
export MOCKFACTORY_ENVIRONMENT=staging
mocklib mocklib_vpc_create "10.0.0.0/16"

# Create ephemeral environment
mocklib env create "temp-test" --auto-delete-hours 1
mocklib --env temp-test mocklib_vpc_create "10.0.0.0/16"
# ... do work ...
# Environment auto-deletes after 1 hour
```

**Implementation** (`mocklib-cli/environment.go`):

```go
func envCreate(name string, description string, autoDeleteHours int) error {
    reqBody := map[string]interface{}{
        "name": name,
    }

    if description != "" {
        reqBody["description"] = description
    }

    if autoDeleteHours > 0 {
        reqBody["auto_delete_after_hours"] = autoDeleteHours
    }

    resp, err := makeRequest("POST", "/environments", reqBody)
    if err != nil {
        return err
    }

    fmt.Printf("✓ Created environment: %s\n", name)
    fmt.Printf("  ID: %s\n", resp["id"])
    fmt.Printf("  Status: %s\n", resp["status"])

    if autoDelete, ok := resp["auto_delete_at"]; ok {
        fmt.Printf("  Auto-delete at: %s\n", autoDelete)
    }

    return nil
}

func envList() error {
    resp, err := makeRequest("GET", "/environments", nil)
    if err != nil {
        return err
    }

    environments := resp["environments"].([]interface{})

    if len(environments) == 0 {
        fmt.Println("No environments found")
        return nil
    }

    fmt.Println("Environments:")
    fmt.Println("============")
    for _, e := range environments {
        env := e.(map[string]interface{})
        fmt.Printf("\n%s (ID: %s)\n", env["name"], env["id"])
        fmt.Printf("  Status: %s\n", env["status"])
        fmt.Printf("  Resources: %d\n", int(env["resource_count"].(float64)))
        fmt.Printf("  API Calls: %d\n", int(env["api_call_count"].(float64)))
        fmt.Printf("  Cost: $%.2f\n", env["cost_usd"].(float64))
        fmt.Printf("  Created: %s\n", env["created_at"])
    }

    return nil
}

func envDelete(name string) error {
    resp, err := makeRequest("DELETE", fmt.Sprintf("/environments/%s", name), nil)
    if err != nil {
        return err
    }

    deleted := resp["deleted_resources"].(map[string]interface{})
    total := int(resp["total_resources_deleted"].(float64))

    fmt.Printf("✓ Deleted environment: %s\n", name)
    fmt.Printf("\nDeleted Resources:\n")
    for resourceType, count := range deleted {
        fmt.Printf("  %s: %d\n", resourceType, int(count.(float64)))
    }
    fmt.Printf("\nTotal: %d resources deleted\n", total)

    return nil
}
```

## Advanced Features

### Auto-Cleanup Policies

**Use Case**: Prevent abandoned environments from accumulating costs

```python
# Create environment that auto-deletes after 24 hours
env = mf.environments.create(
    name="temp-test",
    auto_delete_after_hours=24
)

# Create environment that auto-deletes when idle for 2 hours
env = mf.environments.create(
    name="dev-alice",
    auto_delete_when_idle_hours=2
)
```

**Backend Implementation**:

```python
# app/tasks/cleanup.py

@celery.task
def cleanup_expired_environments():
    """Run every hour"""

    # Find expired environments
    expired = Environment.query.filter(
        Environment.status == 'active',
        Environment.auto_delete_at <= datetime.utcnow()
    ).all()

    for env in expired:
        logger.info(f"Auto-deleting expired environment: {env.name}")

        # Delete all resources
        delete_environment(env.id)

        # Mark as deleted
        env.status = 'deleted'
        env.deleted_at = datetime.utcnow()
        db.session.commit()

@celery.task
def cleanup_idle_environments():
    """Run every hour"""

    # Find environments with auto_delete_when_idle set
    idle_threshold = datetime.utcnow() - timedelta(hours=2)

    idle_envs = Environment.query.filter(
        Environment.status == 'active',
        Environment.auto_delete_when_idle_hours.isnot(None),
        Environment.last_activity_at <= idle_threshold
    ).all()

    for env in idle_envs:
        logger.info(f"Auto-deleting idle environment: {env.name}")
        delete_environment(env.id)
        env.status = 'deleted'
        env.deleted_at = datetime.utcnow()
        db.session.commit()
```

### Environment Templates

**Use Case**: Quickly create pre-configured environments

```python
# Save current environment as template
template = mf.environments.save_as_template(
    environment="staging",
    template_name="microservices-stack",
    description="VPC + 5 Lambdas + 3 DynamoDB tables + 2 SQS queues"
)

# Create new environment from template
new_env = mf.environments.create_from_template(
    template="microservices-stack",
    name="pr-789"
)

# All resources from template are created in new environment
```

### Environment Snapshots

**Use Case**: Backup and restore environment state

```python
# Create snapshot
snapshot = mf.environments.create_snapshot("staging")

# Restore to a new environment
mf.environments.restore_snapshot(
    snapshot_id=snapshot.id,
    target_environment="staging-restore"
)
```

### Environment Sharing

**Use Case**: Share environment with team members

```python
# Share environment (read-only)
mf.environments.share(
    environment="staging",
    email="teammate@example.com",
    access="read"
)

# Share with write access
mf.environments.share(
    environment="staging",
    email="teammate@example.com",
    access="write"
)
```

## Migration Path

### For Existing Users

**Phase 1**: Implicit default environment
- All existing resources moved to "default" environment per user
- SDK automatically uses "default" if no environment specified
- Zero breaking changes

**Phase 2**: Encourage named environments
- Show environment in dashboard
- Suggest creating named environments
- Show cost savings from cleanup

**Phase 3**: Environment-first UX
- Require environment name for new resources
- Provide easy environment creation
- Show benefits in onboarding

## UI/Dashboard

**Environment List View**:

```
┌─────────────────────────────────────────────────────────────┐
│ Environments                                   [+ New]       │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ staging                                        Active    │ │
│ │ 15 resources · 1,234 API calls · $1.23                  │ │
│ │ Created: Feb 13, 2026                                   │ │
│ │ [View] [Delete]                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ pr-456                                         Active    │ │
│ │ 3 resources · 45 API calls · $0.05                      │ │
│ │ Auto-deletes in 11 hours                                │ │
│ │ [View] [Delete]                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ dev-alice                                      Active    │ │
│ │ 8 resources · 567 API calls · $0.57                     │ │
│ │ Created: Feb 10, 2026                                   │ │
│ │ [View] [Delete]                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Environment Detail View**:

```
┌─────────────────────────────────────────────────────────────┐
│ Environment: staging                                         │
│ ID: 550e8400-e29b-41d4-a716-446655440000                    │
│                                                              │
│ [Edit] [Delete] [Create Snapshot] [Share]                   │
│                                                              │
│ ═══════════════════════════════════════════════════════════ │
│                                                              │
│ Resources (15)                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ VPCs (2)                                              │   │
│ │   vpc-abc123   10.0.0.0/16   available               │   │
│ │   vpc-def456   172.31.0.0/16 available               │   │
│ │                                                       │   │
│ │ Lambda Functions (5)                                  │   │
│ │   api-gateway    nodejs18.x   512MB                  │   │
│ │   auth-service   python3.9    256MB                  │   │
│ │   ...                                                 │   │
│ │                                                       │   │
│ │ DynamoDB Tables (3)                                   │   │
│ │   users         id (S)        ACTIVE                 │   │
│ │   ...                                                 │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ Usage & Cost                                                │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ API Calls: 1,234 (last 30 days)                      │   │
│ │ Cost: $1.23                                           │   │
│ │ [View detailed breakdown]                             │   │
│ └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Summary

**Environments provide**:

✅ **Isolation**: Multiple developers/PRs don't interfere
✅ **Organization**: Group related resources
✅ **Cleanup**: Delete all resources with one command
✅ **Cost Tracking**: See costs per environment/PR/developer
✅ **Auto-Cleanup**: Prevent abandoned resources
✅ **Team Collaboration**: Share environments

**This makes MockFactory**:
- More powerful for teams
- Safer for CI/CD
- Easier to manage costs
- Better organized

**Implementation Priority**: HIGH - This should be built alongside the SDKs, as it's a foundational feature that affects the entire platform! 🚀
