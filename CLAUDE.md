# CLAUDE.md

Guidance for Claude Code when working on MockFactory.

## Product reality

MockFactory is a self-hosted developer-platform control plane for privately owned servers. It provides disposable test environments, mock data, trusted-team code execution, and stateful AWS/OCI/GCP/Azure-compatible APIs. The initial audience is the internal engineering team plus customers consuming hosted APIs and services. Customer arbitrary-code execution is intentionally deferred.

This repository is not currently production-ready. The root README and some historical documents overstate readiness or describe obsolete OCI/Kubernetes assumptions. Treat executable code, migrations, tests, and current Compose configuration as stronger evidence than status prose.

Related repositories:

- `../mockfactory-mocklib`: multi-language platform API and environment-composition layer.
- `../mockfactory-cli`: older Python CLI focused on code execution and resource commands.

An active overhaul may exist in `.worktrees/platform-overhaul` on `feature/platform-overhaul`. Never assume those changes are on `main`; inspect branches and commits first.

## Current architecture

- `app/main.py`: global FastAPI application and router assembly.
- `app/api/`: authentication, payments, environments, data/DNS, and provider emulators.
- `app/services/`: provisioning, background loops, billing, generators, DNS, and bridges.
- `app/sandboxes/`: Docker-based trusted code execution.
- `app/models/`: SQLAlchemy persistence.
- `alembic/`: database migration configuration. Confirm revision files are tracked before deployment.
- `frontend/`: static HTML/JavaScript application.
- `docker-compose.yml`: PostgreSQL, Redis, MinIO, registry, and API.
- `terraform/` and `ansible/`: integration prototypes, not proof of production compatibility.

The desired architecture is a modular control plane with durable Redis jobs and authenticated node agents. The public API must not retain direct Docker-socket authority long term.

## Local setup and verification

Use Python 3.11. Do not use a production `.env` in tests.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
docker compose up -d
alembic upgrade head
```

On current `main`, `tests/` may be empty and pytest may not be declared. Report that honestly. On the overhaul branch use:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/python scripts/export_openapi.py --check
docker compose config --quiet
```

Never claim a provider, migration, sandbox, SDK, or deployment works without running its relevant verification.

## Security invariants

- `Authorization: Bearer` is for user JWTs; automation uses `X-API-Key`.
- Protected endpoints must use a dependency that rejects anonymous and inactive users.
- Every tenant-owned query must include organization/project/user scope.
- Never log or return credentials, tokens, connection passwords, uploaded code, or Stripe secrets.
- The public API must not accept arbitrary Docker flags, mounts, images, or host paths.
- Do not broaden arbitrary-code execution beyond trusted engineers without an approved sandbox milestone.
- Long-running mutations must become idempotent operation resources rather than blocking API workers.
- Cleanup must require both ownership labels and matching database ownership.
- Do not trust forwarded host/protocol/client-IP headers from arbitrary peers.
- Preserve security failure tests before refactoring authentication or tenancy.

## API and compatibility rules

- Canonical configurable base path: `/api/v1`.
- Preserve stable error codes, request IDs, pagination semantics, idempotency, and operation lifecycle behavior.
- OpenAPI is the transport contract, but MockLib contains higher-level product semantics that must not be generated away.
- “Cloud compatible” means an official client/provider test passes for the specific advertised operations.
- Prefer a correct, tested subset over broad unverified parity.
- Every create path needs verified get/list/delete and orphan-cleanup behavior.

## Working practices

- Read `git status`, current branch, and applicable plans before editing.
- Preserve unrelated user changes and secrets.
- Use test-first development for behavior changes.
- Add Alembic migrations for schema changes; never use `Base.metadata.create_all()` as deployment migration logic.
- Avoid import-time connections to Docker, Redis, cloud services, or databases.
- Separate API processes, scheduled jobs, and provisioning workers.
- Update docs and compatibility matrices in the same change as behavior.
- Historical reports in `docs/` are evidence of prior thinking, not authoritative current status.
