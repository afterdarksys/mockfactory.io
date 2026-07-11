# AGENTS.md

## Scope

These instructions apply to the entire `mockfactory.io` repository.

## Before changing code

1. Run `git status --short` and `git branch --show-current`.
2. Check whether `.worktrees/platform-overhaul` or `docs/plans/` contains the active implementation plan.
3. Read the target route, its authentication dependency, model ownership, migration history, and relevant provider adapter together.
4. State whether the work targets current `main` or an overhaul branch.

## Required engineering behavior

- Write a failing regression/behavior test first, then implement the smallest passing change.
- Keep FastAPI request handlers short; provisioning belongs in durable workers.
- Treat organization, project, environment, operation, API key, secret, and audit identifiers as tenant-scoped.
- Use explicit authorization permissions rather than scattered role-name checks.
- Use migrations for persistence changes and verify upgrade SQL or a real disposable database.
- Make external connections lazily, with timeouts and bounded retries.
- Use stable structured errors; do not expose internal exceptions.
- Pin workload images and reject caller-controlled runtime privileges.

## Verification expectations

Run the narrow test while developing and the complete available suite before completion. Also run, when present:

```bash
git diff --check
.venv/bin/pytest -q
.venv/bin/python scripts/export_openapi.py --check
docker compose config --quiet
```

For migrations, generate offline SQL or exercise upgrade/downgrade against a disposable PostgreSQL instance. For provider compatibility, exercise an official SDK or CLI, not only an internal helper.

If a command cannot run because the repository lacks tests, configuration, services, or dependencies, report the exact gap. Do not convert absence of evidence into a passing claim.

## Cross-repository changes

Changes affecting public resources normally require coordinated work in:

- `mockfactory.io`: server behavior and OpenAPI
- `mockfactory-mocklib`: semantic contract and each language implementation
- `mockfactory-cli`: migration or deprecation of overlapping commands

Document compatibility and rollout order. Do not silently change authentication headers, base URLs, field names, defaults, errors, or lifecycle semantics.

## Destructive and deployment operations

Do not deploy, publish packages, push images, rotate credentials, modify live DNS, run destructive migrations, or destroy environments without explicit user authorization. Deployment scripts are historical and may reference real or obsolete infrastructure; read them before use.
