# Cloud Compatibility, MockLib, and CLI Expansion Plan

## Compatibility definition

MockFactory will publish compatibility at the operation level:

- **Compatible:** Official client/provider works without MockFactory-specific behavior.
- **Compatible with limits:** Protocol matches, with documented scale or timing limits.
- **MockFactory extension:** Useful API with no promise of cloud-provider equivalence.
- **Planned:** Contract designed but not implemented.
- **Unsupported:** Rejected with the provider's normal unsupported-operation error.

Every compatible operation requires request/response fixtures, error fixtures, pagination tests, tenant-isolation tests, cleanup tests, and at least one official SDK or CLI black-box test.

## Delivery waves

### Wave 1: Application development primitives

| Provider | Services | Bare-metal backend | Required client proof |
|---|---|---|---|
| AWS | S3, SQS, SNS, DynamoDB, Lambda, STS | MinIO, Redis, PostgreSQL JSONB, isolated workers | boto3 and AWS CLI |
| OCI | Object Storage, Queue, Streaming, Functions, Notifications | MinIO, Redis lists/streams, isolated workers | OCI SDK/CLI |
| GCP | Cloud Storage, Pub/Sub | MinIO, Redis Streams | Google Cloud SDKs |
| Azure | Blob Storage, Queue Storage, Service Bus subset | MinIO, Redis | Azure SDKs |

Edge cases include conditional writes, multipart uploads, range requests, checksums, queue visibility, dead-letter queues, long polling, FIFO ordering, batch partial failures, pagination tokens, TTL, optimistic concurrency, invocation timeouts, binary payloads, and provider-shaped errors.

### Wave 2: Networking and compute control planes

- AWS: EC2 instance lifecycle, VPC, subnet, route table, security group, elastic IP, network interfaces, basic ELBv2.
- OCI: Compute, VCN, subnet, NSG, route table, public IP, block volume, load balancer subset.
- GCP: Compute Engine instances, networks, subnetworks, firewall rules, disks, addresses.
- Azure: VMs, VNets, subnets, NSGs, disks, public IPs, load balancer subset.

These are modeled resources backed by Docker networks, containers, volumes, and controlled proxy listeners. They must never imply hypervisor-grade isolation.

### Wave 3: Databases, secrets, and configuration

- AWS: RDS PostgreSQL/MySQL subset, ElastiCache Redis, Secrets Manager, SSM Parameter Store.
- OCI: Base Database/MySQL shapes, Vault-secret subset.
- GCP: Cloud SQL and Secret Manager subset.
- Azure: PostgreSQL/MySQL flexible-server and Key Vault-secret subset.

Databases use approved images, generated credentials, readiness probes, quotas, backups, and time-limited connection retrieval.

### Wave 4: Developer workflow services

- DNS: Route 53, OCI DNS, Cloud DNS, Azure DNS over one authoritative DNS engine.
- Container registries: ECR, OCIR, Artifact Registry, ACR over the private registry.
- Email/testing: SES-compatible send capture backed by Mailpit.
- Scheduling/events: EventBridge, OCI Events, Eventarc subset, Azure Event Grid subset.
- Observability mocks: CloudWatch logs/metrics, OCI Logging/Monitoring, Cloud Logging, Azure Monitor ingestion subsets.

## One canonical domain model

Provider adapters translate external protocols into canonical internal commands such as `BucketCreate`, `QueueSend`, `InstanceStart`, and `SecretVersionPut`. Canonical services own tenancy, persistence, idempotency, quotas, and audit events. Provider adapters own signing, naming, wire formats, status codes, and provider-specific semantics. Provider request models must not leak into core persistence.

## MockLib language parity

| Surface | Python | TypeScript | Go | PHP | Shell |
|---|---|---|---|---|---|
| Generated transport/models | Yes | Yes | Yes | Yes | No |
| Sync client | Yes | Optional | Yes | Yes | curl functions |
| Async client | Yes | Native | Context-based | Later | No |
| Retries/timeouts | Shared policy | Shared policy | Shared policy | Shared policy | Minimal |
| Operation waiter | Yes | Yes | Yes | Yes | Yes |
| Pagination iterator | Yes | Yes | Yes | Yes | Token helper |
| Typed provider resources | Yes | Yes | Yes | Yes | JSON |
| Custom CA/proxy | Yes | Yes | Yes | Yes | Native curl |

Generated code owns serialization and HTTP mechanics. Hand-written layers provide idiomatic names, waiters, pagers, upload/download streaming, and provider resource groupings. All languages consume the same recorded conformance scenarios and report a parity matrix in CI.

Breaking changes require a new API version. Additive fields remain backward compatible. SDKs support the current API and one prior version. Each release embeds its SDK version and negotiated API version in the user agent.

## Official `mf` CLI

The Go CLI becomes the single supported binary. Command groups:

```text
mf auth        login, logout, whoami, api-key
mf project     create, list, use, quota
mf template    list, inspect, validate
mf env         create, get, list, wait, connect, stop, start, destroy, logs
mf aws         focused convenience commands
mf oci         focused convenience commands
mf gcp         focused convenience commands
mf azure       focused convenience commands
mf operation   get, wait, cancel
mf node        list, inspect, cordon (admin)
mf admin       doctor, images, backup, restore, audit
```

Human output is readable; `--json` is stable automation output. Every mutation supports `--idempotency-key`, `--wait`, `--timeout`, and `--no-wait`. Profiles store URLs and CA paths, while credentials use the OS keychain or permission-restricted files. The CLI must operate against internal DNS names and private certificate authorities without source changes.

## Terraform/OpenTofu and Ansible

The Go API client is shared by the CLI and Terraform/OpenTofu provider. Resources cover projects, environments, service attachments, buckets, queues, and secrets metadata. Sensitive values are marked sensitive; imports and refresh detect drift. Destruction waits for cleanup operations unless explicitly detached.

The Ansible collection provides check/diff mode, idempotent modules, operation waiters, and dynamic inventory. Neither provider permits arbitrary code execution; both submit structured desired state to the public API.

## Cross-repository execution order

1. Commit and version the backend OpenAPI artifact.
2. Fix MockLib base URLs and use `X-API-Key` everywhere.
3. Generate transports and add conformance fixtures.
4. Port ergonomic wrappers one service family at a time.
5. Consolidate CLI commands into the Go `mf` binary.
6. Build the Terraform/OpenTofu provider from the shared Go client.
7. Build the Ansible collection from the generated Python client.
8. Deprecate the Python CLI only after command parity and migration documentation exist.

## Release gates

- No endpoint appears in an SDK until its server contract test passes.
- No service is advertised as compatible until an official client test passes.
- No language release ships with missing required operations relative to its parity manifest.
- No CLI mutation lacks JSON output, idempotency, timeout, and actionable errors.
- Every resource creation has a verified destroy path and orphan reconciliation test.
