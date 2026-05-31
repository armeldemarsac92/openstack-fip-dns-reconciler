# openstack-fip-dns-reconciler

`openstack-fip-dns-reconciler` is a small polling controller that creates and
maintains OpenStack Designate `A` and `TXT` recordsets for Neutron floating IPs.
Neutron floating IPs are the source of truth. Designate records are generated
state.

```text
Neutron floating IPs
  -> openstack-fip-dns-reconciler
  -> Designate recordsets
  -> edge resolver / HAProxy / SSH gateway
```

The default generated record shape is:

```text
<random-label>.<dns-safe-project-id>.fip.internal.mycloud.net. A <floating-ip-address>
<random-label>.<dns-safe-project-id>.fip.internal.mycloud.net. TXT "managed-by=openstack-fip-dns-reconciler fip_id=<uuid> project_id=<uuid>"
```

Example:

```text
x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net. A 10.50.0.42
x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net. TXT "managed-by=openstack-fip-dns-reconciler fip_id=2c4f... project_id=8ab1c22f4d6e4f19a21c4d8f23bb912a"
```

## Why Direct Designate Records

Neutron floating IP DNS attributes such as `dns_name` and `dns_domain` are a
different feature. They are commonly create-time metadata and are not a good
control surface for an after-the-fact reconciler.

This controller creates normal Designate recordsets directly. The TXT record is
the ownership marker used for idempotency and cleanup. Records without the
expected TXT ownership metadata are ignored and never deleted.

## Why Project IDs

DNS names are based on OpenStack `project_id`, not project name. Project names
can change, collide, or contain unsafe DNS characters. The controller sanitizes
project IDs defensively:

- lowercase only
- `a-z` and `0-9`
- invalid characters become `-`
- repeated hyphens collapse
- leading and trailing hyphens are trimmed
- labels are kept within the 63 character DNS limit

Two modes are supported:

```yaml
project_id_label_mode: full
project_id_label_mode: short
project_id_short_length: 8
```

Short mode detects collisions before reconciling affected projects. The full
project ID is always preserved in TXT ownership metadata.

## Edge Architecture

This is useful in small private clouds or homelabs where instances are reached
through a shared edge, SSH gateway, reverse proxy, or split-horizon resolver. A
tenant allocates a floating IP, and the controller publishes a stable generated
DNS name that can be consumed by HAProxy, SSH config, monitoring, or users.

## Configuration

Start from:

```bash
cp config.example.yaml config.yaml
```

Minimal example:

```yaml
openstack:
  cloud: admin

controller:
  poll_interval_seconds: 15
  dry_run: false

dns:
  base_domain: fip.internal.mycloud.net.
  zone_strategy: single_zone
  all_projects: false
  ttl: 60
  label_length: 13
  label_encoding: base32
  project_id_label_mode: short
  project_id_short_length: 8
```

Credentials are loaded by `openstacksdk`, so both `clouds.yaml` and `OS_*`
environment variables are supported.

Set `dns.all_projects: true` when the reconciler uses a least-privilege service
credential that can read/write generated Designate recordsets across projects
but does not own the generated zone. With this enabled, the Designate adapter
adds `all_projects=True` to zone and recordset discovery and resolves managed
zones from the all-project zone list instead of using project-scoped zone lookup.

If the service credential does not have Neutron floating IP write privileges,
disable display metadata writes:

```yaml
neutron_metadata:
  update_description: false
  update_tags: false
```

## Zone Strategies

`single_zone` uses one generated zone:

```text
fip.internal.mycloud.net.
```

Records include the project label:

```text
x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net.
```

`per_project_zone` uses a generated zone per project label:

```text
8ab1c22f.fip.internal.mycloud.net.
```

The FQDN remains the same. The MVP expects generated zones to exist and be
readable/writable by the reconciler. Missing zones are logged as operational
errors and retried on the next polling pass.

## User Visibility

Users can see generated records through Designate if they have read access to
the generated zone:

```bash
openstack recordset list fip.internal.mycloud.net.
```

When Neutron metadata updates are enabled, users can also inspect the floating
IP:

```bash
openstack floating ip show <fip-id>
```

Expected display metadata:

```text
description='Auto DNS: x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net.'
tags='auto-dns,dns-label:x7k9m2q4pa,dns-project:8ab1c22f'
```

Description and tags are display metadata only. The authoritative state remains
the Neutron floating IP inventory and controller-owned TXT recordsets.

## Running Locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
openstack-fip-dns-reconciler --config config.yaml --once
```

Use dry-run for the first pass:

```bash
openstack-fip-dns-reconciler --config config.yaml --once --dry-run
```

Run tests and checks:

```bash
pytest
ruff check .
ruff format --check .
mypy
```

## Docker

Build:

```bash
docker build -f docker/Dockerfile -t openstack-fip-dns-reconciler:latest .
```

Run:

```bash
docker run --rm \
  -v /etc/openstack/clouds.yaml:/etc/openstack/clouds.yaml:ro \
  -v ./config.yaml:/etc/openstack-fip-dns-reconciler/config.yaml:ro \
  openstack-fip-dns-reconciler:latest
```

## GitHub Artifacts

The repository publishes artifacts with GitHub Actions on pushes to `main`,
pull requests, manual dispatches, and `v*.*.*` tags.

On `main`, the workflow runs tests, Ruff, mypy, builds Python wheel/source
distributions, uploads them as workflow artifacts, and publishes a Docker image
to GitHub Container Registry:

```text
ghcr.io/armeldemarsac92/openstack-fip-dns-reconciler:latest
ghcr.io/armeldemarsac92/openstack-fip-dns-reconciler:sha-<commit>
```

On version tags such as `v0.1.0`, it also creates a GitHub Release with the
wheel, source distribution, and SHA256 checksum attached.

## systemd

Install the package in a virtualenv or system Python path, place configuration
at `/etc/openstack-fip-dns-reconciler/config.yaml`, then adapt:

```text
deploy/systemd/openstack-fip-dns-reconciler.service
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now openstack-fip-dns-reconciler
```

## Kolla-Ansible Notes

Use a dedicated Keystone service user. The recommended role model is:

```text
network_inventory_reader
dns_reconciler
```

Desired permissions:

- Neutron: list/read floating IPs across projects
- Neutron: optionally update floating IP description and tags
- Neutron: no floating IP create/delete permission
- Designate: read generated zones and recordsets
- Designate: create/update/delete generated recordsets

Keep generated zones controller-written and tenant-readable. Avoid promising
per-recordset read-only behavior inside a tenant-writable zone. If tenants need
custom DNS, give them separate tenant-managed zones.

See `deploy/kolla/README.md` for policy sketches and a `clouds.yaml` example.

## Architecture

The project uses a layered object-oriented design:

```text
endpoints/        CLI and worker loop
application/      use cases and repository ports
domain/           pure models, naming, ownership, planning rules
infrastructure/   OpenStack SDK adapters
config/           typed settings and YAML loading
observability/    logging setup
```

Application services depend on repository protocols, not OpenStack SDK classes.
OpenStack SDK resources are mapped into domain models in the infrastructure
adapters.

## Reconciliation

Each polling pass:

1. Lists Neutron floating IPs.
2. Lists controller-managed Designate records by finding TXT ownership metadata.
3. Builds desired DNS state.
4. Plans creates, updates, stale deletes, and metadata updates.
5. Applies the plan unless dry-run is enabled.

The controller repairs partial failures on later passes. Designate recordset
descriptions also carry the ownership marker, so if an `A` record is created but
TXT metadata creation fails, the next pass can recreate the missing TXT record.
Records without controller TXT metadata or a controller description marker are
not considered managed.

## Future Neutron Events

Polling is the correctness mechanism. A future oslo.messaging/RabbitMQ listener
can implement `FloatingIpEventSource` and trigger early reconciliation on:

```text
floatingip.create.end
floatingip.update.end
floatingip.delete.end
```

Events should only reduce reaction time. Periodic polling must remain enabled
for eventual consistency and missed notification recovery.

## Limitations

- IPv4 `A` records are implemented first.
- Per-project zone creation is not automated in the MVP.
- Prometheus metrics are not implemented yet.
- Neutron event listening is intentionally left as a future adapter.
- TXT ownership metadata should remain enabled for idempotent cleanup.

## Git Workflow

Development uses small conventional commits. The current history is intentionally
split by project skeleton, tooling, config, domain, planner, infrastructure,
service, endpoint, tests, and docs. Commits in this workspace are local and can
be re-signed before publishing.
