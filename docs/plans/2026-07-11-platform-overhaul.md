# MockFactory Platform Overhaul Implementation Plan

> **For Codex:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Turn MockFactory into a secure, self-hosted developer platform for internal engineers and external API customers, scaling from a 5–10 environment beta to 100+ environments.

**Architecture:** A modular FastAPI control plane stores desired state in PostgreSQL and dispatches durable operations through Redis. Dedicated node agents reconcile allowlisted workloads on homegrown servers; all clients, SDKs, and infrastructure providers consume a single versioned OpenAPI contract.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL, Redis, Docker initially, MinIO, OpenAPI, Go CLI/provider/agent, pytest, Prometheus/OpenTelemetry.

---

## Delivery rules

- Follow red-green-refactor for every behavior change.
- Do not expose the Docker socket to a public API process.
- Use `Authorization: Bearer <JWT>` only for user sessions and `X-API-Key: mf_...` only for automation.
- Require idempotency keys for asynchronous mutations.
- Do not claim cloud-service compatibility without protocol-level contract tests.
- Preserve existing published endpoints behind compatibility adapters until clients migrate.
- Commit at coherent, verified checkpoints; never commit secrets or `.env` files.

## Phase 1: Contract and security foundation

### Task 1: Reproducible test harness

**Files:**
- Modify: `.gitignore`
- Create: `pytest.ini`
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_settings.py`

**Steps:**
1. Add a failing settings test that supplies safe test values without reading a developer `.env`.
2. Run `.venv/bin/pytest tests/unit/test_settings.py -v` and confirm failure.
3. Add test configuration, deterministic environment variables, and isolated SQLite/temporary dependencies where unit tests do not need PostgreSQL.
4. Run the focused test and the complete suite.
5. Commit `test: establish backend test harness`.

### Task 2: Separate JWT and API-key authentication

**Files:**
- Modify: `app/security/auth.py`
- Modify: `app/models/api_key.py`
- Create: `tests/unit/security/test_authentication.py`

**Required tests:**

```python
def test_bearer_token_is_decoded_as_jwt_only(): ...
def test_x_api_key_authenticates_active_key(): ...
def test_api_key_is_rejected_after_expiration(): ...
def test_inactive_api_key_is_rejected(): ...
def test_missing_credentials_returns_401(): ...
def test_malformed_jwt_returns_401_not_500(): ...
```

**Steps:**
1. Write the six failing tests and verify the expected failures.
2. Declare headers with FastAPI `Header`; use `OAuth2PasswordBearer` only for JWTs.
3. Add constant-time API-key hash comparison, expiration validation, active-user validation, and a single last-used update path.
4. Run focused and full tests.
5. Commit `fix: separate user and automation authentication`.

### Task 3: Enforce protected-route authentication

**Files:**
- Modify: `app/api/api_keys.py`
- Modify: `app/api/environments.py`
- Modify: `app/api/data_generation.py`
- Modify: `app/api/dns_management.py`
- Create: `tests/api/test_protected_routes.py`

**Steps:**
1. Parameterize requests to protected endpoints and assert anonymous requests return 401, not 500.
2. Verify failures against current dependencies.
3. Replace nullable dependencies with `require_user` or the scoped automation dependency.
4. Test inactive users and cross-user resource access as 403/404.
5. Run all tests and commit `fix: enforce authentication on protected APIs`.

### Task 4: Standard API errors and request IDs

**Files:**
- Create: `app/core/errors.py`
- Create: `app/middleware/request_id.py`
- Modify: `app/main.py`
- Create: `tests/api/test_error_contract.py`

**Contract:**

```json
{
  "error": {
    "code": "authentication_required",
    "message": "Authentication required",
    "request_id": "req_...",
    "retryable": false,
    "details": []
  }
}
```

**Steps:** Write failing tests for validation, authentication, not-found, and unexpected errors; implement exception handlers and request-ID propagation; verify headers and JSON; commit.

### Task 5: Health and OpenAPI contract

**Files:**
- Create: `app/api/health.py`
- Modify: `app/main.py`
- Create: `tests/api/test_health.py`
- Create: `tests/contract/test_openapi.py`
- Create: `scripts/export_openapi.py`

**Steps:**
1. Test `/health/live`, `/health/ready`, documented security schemes, unique operation IDs, and `/api/v1` path conventions.
2. Implement dependency-aware readiness without leaking credentials.
3. Export a deterministic `openapi.json` artifact and fail tests on duplicate operation IDs.
4. Commit `feat: publish stable health and OpenAPI contracts`.

## Phase 2: Durable environment operations

### Task 6: Operation and idempotency models

**Files:**
- Create: `app/models/operation.py`
- Create: `app/models/idempotency.py`
- Create: `alembic/versions/<revision>_add_operations.py`
- Create: `tests/unit/models/test_operations.py`

Implement state transitions, unique `(actor, idempotency_key)` constraints, request fingerprints, progress, retryability, and structured failure details. Reject reuse of a key with a different payload.

### Task 7: Asynchronous environment API

**Files:**
- Modify: `app/api/environments.py`
- Create: `app/api/operations.py`
- Create: `app/services/operation_service.py`
- Create: `tests/api/test_environment_operations.py`

Change environment mutations to return `202` operation resources. Preserve old synchronous behavior only through a documented compatibility flag during migration.

### Task 8: Redis worker service

**Files:**
- Create: `app/worker/main.py`
- Create: `app/worker/handlers.py`
- Modify: `docker-compose.yml`
- Create: `tests/integration/test_worker_recovery.py`

Test duplicate delivery, worker termination, bounded retries, poison jobs, graceful shutdown, and reconciliation after a partial create.

### Task 9: Remove in-process schedulers

**Files:**
- Modify: `app/main.py`
- Replace: `app/services/background_tasks.py`
- Create: `tests/integration/test_scheduled_jobs.py`

Ensure API replicas never run billing, cleanup, or shutdown loops. Use distributed locks for scheduled enqueueing and idempotent handlers for execution.

## Phase 3: Node-agent control plane

### Task 10: Node inventory and scheduler

Create node, capability, reservation, and heartbeat models plus APIs. Test stale nodes, insufficient capacity, concurrent placement, capability constraints, and release of reservations.

### Task 11: Authenticated node agent

Create a standalone Go agent repository/component with mutual authentication, structured commands, heartbeats, allowlisted images, ownership labels, and no arbitrary Docker arguments. Add a fake agent for control-plane integration tests.

### Task 12: Reconciliation and cleanup

Reconcile desired and observed state. Never delete resources without both MockFactory ownership labels and matching database ownership. Test orphan adoption/quarantine, node loss, partial deletion, and retry exhaustion.

## Phase 4: Templates, projects, and customer API

### Task 13: Organizations, projects, roles, and quotas

Add organization/project membership, RBAC scopes, project API keys, CPU/memory/disk/environment quotas, and audit events. Test every cross-tenant access path.

### Task 14: Versioned environment templates

Add validated YAML/JSON templates for Postgres, Redis, MinIO, queues, Mailpit, seed data, TTL, limits, and network policy. Pin image digests and support template version upgrades.

### Task 15: Secrets and connections

Generate credentials per environment, encrypt secrets at rest, redact logs/responses, expose time-limited authorized retrieval, and rotate secrets during clone/restore.

## Phase 5: Infrastructure-as-code clients

### Task 16: One official Go CLI

Consolidate the Python and Go command surfaces into `mf`. Support profiles, internal CA bundles, login, API keys, environment lifecycle, operation waiting, logs, templates, and offline administration.

### Task 17: Terraform/OpenTofu provider

Implement resources and data sources for projects, environments, services, buckets, queues, and generated connections. Test import, refresh, drift, cancellation, idempotency, and sensitive-state handling using the Terraform provider test framework.

### Task 18: Ansible collection

Implement idempotent modules and dynamic inventory. Support check mode, diff mode, operation polling, certificate configuration, and predictable failure messages.

### Task 19: Generated MockLib transports

Generate models/transports for Python, TypeScript, Go, and PHP from the committed OpenAPI artifact. Retain hand-written ergonomic wrappers. Run the same black-box contract suite against every language.

## Phase 6: Cloud compatibility

### Task 20: Compatibility capability matrix

Publish exact operation-level support rather than broad service claims. Classify each operation as compatible, partial, extension, or unsupported with documented semantics.

### Task 21: AWS baseline

Harden S3, SQS, DynamoDB, Lambda, IAM/STS, and core EC2/VPC behavior. Test official SDK requests, signatures where applicable, pagination, error codes, eventual-consistency expectations, and cleanup.

### Task 22: OCI, GCP, and Azure baseline

Harden OCI Object Storage/Queue/Functions, GCP Storage/Compute, and Azure Blob/VM operations using provider-specific protocol tests. Prefer correct small surfaces over unverified breadth.

## Phase 7: Operations and scale

### Task 23: Observability

Add Prometheus metrics, OpenTelemetry traces, structured logs, Grafana dashboards, node alerts, queue-depth alerts, capacity forecasting, and correlation across request/operation/node IDs.

### Task 24: Backup and disaster recovery

Automate PostgreSQL and MinIO backups to physically separate storage. Run scheduled restore drills and record recovery-point and recovery-time evidence.

### Task 25: Beta and 100-environment load gates

Create repeatable load/failure scenarios for 10 then 100 concurrent environments. Gate releases on provisioning latency, API latency, cleanup success, job recovery, resource leakage, and tenant isolation.

## Cross-repository migration requirements

The current workspace can write only `mockfactory.io`. Changes to `mockfactory-cli` and `mockfactory-mocklib` require expanded writable scope when Phases 5–6 begin. Until then, the backend must provide compatibility tests and a migration document covering:

- Base URL convergence on `/api/v1`
- `X-API-Key` adoption
- Standard error parsing
- Operation polling
- Pagination
- Idempotency keys
- Deprecation schedule for the Python CLI and legacy routes

## Foundation completion gate

Phase 1 is complete only when:

```bash
.venv/bin/pytest -q
.venv/bin/python scripts/export_openapi.py --check
docker compose config --quiet
```

all exit successfully, protected-route tests prove anonymous requests cannot reach handlers, API keys and JWTs are unambiguous, and the OpenAPI artifact describes the actual runtime routes.
