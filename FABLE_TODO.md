# FABLE_TODO — MockFactory emulation expansion

Handoff for a Fable planning pass. Fable scopes + sequences; Opus builds. This is
forward-looking growth work, not a bug hunt.

## What exists today (2026-07-11)
A genuine multi-cloud emulation platform, not a single-cloud mock:
- **4 clouds:** AWS (Lambda, DynamoDB, SQS, SNS, VPC), Azure, GCP, and OCI (deep —
  database, functions, notifications, queue, streaming, network).
- **28 API routers** (`app/api/`), **10 service modules** (`app/services/`), plus
  container registry, DNS, compute, data generation, environment provisioning, and a
  billing/usage/credits + auth/api-key layer.
- **6-language SDK** in `~/development/mockfactory-mocklib` (Python, Node, Go, PHP,
  Shell, CLI).
- **Terraform provider** at `terraform/mockfactory-provider`.

## Two high-leverage extensions (Fable: pick order + scope)
1. **Contract-test the Terraform provider.** The `terraform apply`-against-the-mock
   story is the killer feature (test real IaC in CI, no cloud bill) — but the killer
   feature has no test net. Wire real contract tests so a provider regression is
   caught automatically. Look at `tests/contract/` and `contract/scenarios/` for the
   existing harness shape before adding.
2. **Deepen the thinnest cloud.** OCI is deep; AWS is broad; Azure/GCP are likely
   thinner. Fable should assess coverage per provider and recommend which one to
   round out first (by real-world demand, not symmetry).

## The differentiators to protect (don't regress these)
- **OCI depth** — nobody else emulates Oracle Cloud well; it's the moat and it's the
  cloud Ryan has real background in.
- **The Terraform provider** — turns "a mock library" into "a thing teams pay for."

## Definition of done (per chosen item)
- Terraform provider: a CI-runnable contract-test suite that exercises the provider
  against the mock and fails on drift.
- Cloud deepening: the chosen provider reaches parity with a named coverage target,
  with tests.
- Author commits Ryan Coleman, no AI attribution.
