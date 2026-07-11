# MockFactory Security Architecture

## Scope and security objectives

MockFactory serves internal engineers and external API customers from privately owned servers. Initially, only trusted engineering users may execute uploaded code. Customers may create approved service environments and use cloud-compatible APIs, but cannot submit arbitrary executables or container specifications.

Primary objectives:

1. Prevent access across organizations, projects, and environments.
2. Prevent customer workloads from reaching the control plane, host APIs, or other tenants.
3. Prevent public API compromise from becoming host-level compromise.
4. Make mutations attributable, bounded, idempotent, and recoverable.
5. Protect credentials, customer data, backups, and software supply chains.
6. Fail closed when identity, policy, node health, or ownership is uncertain.

## Trust boundaries

```text
Internet / customer networks (untrusted)
        |
        v
Reverse proxy / TLS boundary
        |
        v
Control-plane API (authenticated but hostile inputs)
        |
        +--> PostgreSQL / Redis / MinIO control data
        |
        v
Durable operation queue
        |
        v
Node-agent mTLS boundary
        |
        v
Approved customer service containers (untrusted workloads)

Trusted-team execution nodes form a separate pool and security class.
```

The API never receives a Docker socket. Node agents accept typed operations referencing server-side templates and image digests; they reject arbitrary Docker flags, bind mounts, host namespaces, privileged mode, devices, capabilities, and unapproved images.

## Identity classes

- **Human session:** OIDC login, short-lived JWT access token, rotated refresh token, session revocation.
- **Automation:** `X-API-Key`, hashed at rest, scoped, expiring, revocable, and optionally environment-restricted.
- **Node agent:** unique machine identity with mutually authenticated TLS, short certificate lifetime, and rotation.
- **Internal worker:** workload identity restricted to job types and data it needs.

Credentials are never accepted through query strings. JWTs and API keys use separate parsers. Authentication identifies an actor; authorization independently evaluates organization, project, resource, action, and contextual constraints.

## Authorization model

Roles are assignments of explicit permissions, not hard-coded endpoint checks:

- Organization owner: membership, billing, policy, and all projects.
- Organization admin: projects, members, keys, templates, and audit access.
- Project operator: environment lifecycle and credential retrieval.
- Project developer: create/use environments within quota.
- Project viewer: read-only metadata; no secret retrieval.
- Service account: explicitly granted automation scopes.

All resource queries include tenant scope at the repository layer. Tests must attempt cross-tenant reads, writes, identifiers, subdomains, pagination cursors, operation IDs, logs, and secret retrieval.

## Workload isolation

- Dedicated control-plane and workload networks.
- Per-environment container networks with deny-by-default egress.
- No host networking, privileged mode, host PID/IPC/user namespaces, or unrestricted mounts.
- CPU, memory, process, disk, file-descriptor, execution-time, and log-output limits.
- Read-only root filesystems and dropped capabilities where images permit.
- Dedicated trusted execution nodes for internal uploaded code.
- gVisor or equivalent sandbox evaluation before external code execution.
- Node admission requires supported kernel, runtime configuration, disk health, and time synchronization.

## Data and secret protection

- TLS for external and internal connections; private CA support is first-class.
- Envelope encryption for retrievable secrets with versioned keys and rotation.
- Unique generated credentials per environment and clone.
- Secrets excluded from URLs, logs, traces, metrics, audit details, and error bodies.
- Time-limited secret retrieval with an audit event.
- Encrypted backups stored on a physically separate system; scheduled restore drills.
- Explicit retention and secure deletion policies for logs, artifacts, and customer data.

## API defenses

- Strict schemas, size limits, bounded collection lengths, and normalized identifiers.
- Request IDs, stable errors, idempotency keys, cursor pagination, and optimistic concurrency.
- Per-IP, actor, organization, project, operation, and resource quotas.
- SSRF protection using scheme/host/IP validation and post-resolution address checks.
- Archive extraction limits preventing traversal, symlinks, decompression bombs, and excessive files.
- Safe XML parsing; no external entities or DTDs.
- Streaming uploads with byte limits, checksums, and content quarantine.
- Webhook signatures with timestamp and replay windows.
- Trusted proxy headers accepted only from configured proxy networks.
- CORS allowlists; security headers; no reflected internal exception content.

## Supply-chain controls

- Images pinned by digest and mirrored to the private registry.
- Allowed-image policies per template and node capability.
- Image and dependency vulnerability scanning with severity gates.
- Signed release artifacts, provider binaries, agent binaries, and offline bundles.
- SBOM generation and provenance records.
- Reproducible builds where practical and protected release credentials.
- Dependency update policy with contract and migration testing.

## Audit and detection

Audit events include actor, credential identity, organization/project/resource, action, decision, request/operation IDs, source address, user agent, result, and timestamp. Secret values and sensitive payloads are never stored. Audit records are append-only to application actors and exported to separate retention storage.

Alert conditions include repeated authorization failures, cross-tenant probes, unusual key use, quota attacks, provisioning floods, node drift, agent certificate failures, orphan growth, image-policy violations, secret access spikes, backup failures, and cleanup failures.

## Availability and safe failure

- State-changing requests are idempotent and persist desired state before dispatch.
- Workers use leases, bounded retries, poison queues, and reconciled cleanup.
- Stale agents are unschedulable; existing resources become degraded rather than silently recreated.
- Ownership labels plus matching database records are required before destructive cleanup.
- Emergency controls can disable a credential, project, organization, provider, template, node, or all provisioning without disabling read-only diagnosis.

## Security release gates

A release cannot advertise production readiness until:

- Threat-model tests cover all new trust-boundary crossings.
- Authentication, authorization, and tenant-isolation suites pass.
- No critical/high known vulnerability lacks a documented exception and mitigation.
- Backup restoration and orphan cleanup are demonstrated.
- Official clients cannot bypass quotas or policy through alternative protocol forms.
- Secrets scanning, dependency scanning, image scanning, and SBOM generation run in CI.
- Incident response, credential rotation, node compromise, and customer-data deletion runbooks exist and have been exercised.

## Deferred external code execution

External arbitrary code execution remains disabled until dedicated sandbox nodes, stronger isolation, immutable runtime images, syscall policy, egress brokerage, artifact scanning, abuse monitoring, forensic logging, and adversarial escape testing are independently validated. Enabling it is a security milestone, not a feature flag.
