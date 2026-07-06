# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MockFactory (mockfactory.io) — "clouds, emulated." A FastAPI platform that started as a secure multi-language code execution sandbox and has grown into a cloud-provider emulation service: local AWS/GCP/Azure/OCI API emulators, mock data generation, DNS management, and PostgreSQL-first test environments, with OAuth2 auth, usage tiers, and Stripe billing.

## Commands

No Makefile and no configured test framework (the `tests/` dir is empty; pytest is not in requirements.txt).

```bash
cp .env.example .env       # required config
docker-compose up -d       # postgres, redis, minio, registry, api (api on :8000, /docs for OpenAPI)
alembic upgrade head       # DB migrations — tables are Alembic-managed; never use Base.metadata.create_all()
```

Deployment is script-driven: `deploy-staging.sh`, `deploy-production.sh`, `deploy-k8s-update.sh`, `k8s-hot-update.sh` (AWS/k8s targets; read before running — they touch real infrastructure). Ansible config lives in `ansible/`.

## Architecture

- **`app/main.py`** — assembles the FastAPI app: HTTPS-redirect middleware (production hosts only), global rate limiting (slowapi + `app/middleware/rate_limit_middleware.py`), tenant middleware, and mounts every API router.
- **`app/api/`** — two product families:
  - *Code execution*: `execute.py` runs user code (Python/PHP/Perl/JS/Go/shell/HTML) inside hardened Docker containers via `app/sandboxes/docker_sandbox.py` (no root, no network, read-only FS, seccomp, resource limits — the api container mounts `/var/run/docker.sock` to spawn sandboxes).
  - *Cloud emulation*: per-provider emulators — `aws_*` (VPC, Lambda, DynamoDB, SQS, services), `oci_*` (functions, queue, streaming, database, notifications), `gcp_emulator.py`, `azure_emulator.py`, plus `cloud_emulation.py`, `compute_emulation.py`, `container_registry_emulation.py`, `data_generation.py`, `dns_management.py`. `API_SEPARATION.md` in this dir documents the routing split.
  - Cross-cutting: `auth.py` (After Dark Systems SSO OAuth2 + email/password), `payments.py` (Stripe tiers: Anonymous 5 runs / Free 10 / Pro $9.99 unlimited), `api_keys.py`, `client_dashboard.py`, `ai_assistant.py` (Anthropic).
- **`app/services/`** — background_tasks (auto-shutdown of environments), environment_provisioner/provisioning_manager, data_generator (faker), dns_server, sqs_rabbitmq_bridge, credit_billing, usage_tracker.
- **Backing services** (docker-compose): PostgreSQL (SQLAlchemy + Alembic in `alembic/`), Redis, MinIO (S3 emulation storage), and a real `registry:2` container backing the container-registry emulation.
- **`frontend/`** — static HTML pages (index, app, dashboard, docs, tools, login).
- README.md has the full env-var reference and architecture diagram; `docs/` contains extensive per-feature notes.
