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

Kolla-Ansible can install the Neutron and Designate policy overrides that make a
least-privilege reconciler credential possible. It does not manage this project
as an OpenStack service by default; run the reconciler as a normal container or
systemd service beside the Kolla containers.

The recommended model is:

```text
Keystone service user: fip-dns-reconciler
Project scope: service
Roles: network_inventory_reader, dns_reconciler
Neutron: floating IP read across projects only
Designate: generated-zone and recordset read/write across projects
```

For a single shared generated zone that is owned by an admin or DNS project,
share that zone with the `service` project. This keeps the app credential scoped
to the service project while allowing Designate to pass its zone visibility
checks for recordset writes:

```bash
openstack project show service -f value -c id
openstack zone share create <generated-zone-id-or-name> <service-project-id>
```

### Policy Overrides

Create Kolla policy override files on the deployment host. Adjust role names if
your cloud uses different custom roles.

`/etc/kolla/config/neutron/policy.yaml`:

```yaml
context_with_global_access: "role:network_inventory_reader or role:admin"
get_floatingip: "role:network_inventory_reader or rule:admin_only or rule:admin_or_owner or (role:reader and project_id:%(project_id)s)"
"get_floatingip:tags": "role:network_inventory_reader or rule:admin_only or rule:admin_or_owner or (role:reader and project_id:%(project_id)s)"
```

`context_with_global_access` is what lets Neutron return resources from every
project without granting floating IP create, update, delete, or tag mutation.
Do not add `update_floatingip` unless you intentionally enable
`neutron_metadata.update_description` or `neutron_metadata.update_tags`.

`/etc/kolla/config/designate/policy.yaml`:

```yaml
all_tenants: "role:dns_reconciler or role:admin"
get_zones: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s)"
find_zones: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s)"
get_zone: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s) or ('True':%(zone_shared)s)"

get_recordsets: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s)"
get_recordset: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s) or ('True':%(zone_shared)s)"
find_recordset: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s)"
find_recordsets: "role:dns_reconciler or role:admin or (role:reader and project_id:%(project_id)s)"

create_recordset: "role:dns_reconciler or ((role:member and project_id:%(project_id)s) and ('PRIMARY':%(zone_type)s)) or (role:admin and ('PRIMARY':%(zone_type)s)) or (role:admin and ('SECONDARY':%(zone_type)s)) or (('True':%(zone_shared)s) and ('PRIMARY':%(zone_type)s))"
update_recordset: "role:dns_reconciler or ((role:member and project_id:%(project_id)s) and ('PRIMARY':%(zone_type)s)) or (role:admin and ('PRIMARY':%(zone_type)s)) or (role:admin and ('SECONDARY':%(zone_type)s)) or (role:member and project_id:%(recordset_project_id)s and ('PRIMARY':%(zone_type)s))"
delete_recordset: "role:dns_reconciler or ((role:member and project_id:%(project_id)s) and ('PRIMARY':%(zone_type)s)) or (role:admin and ('PRIMARY':%(zone_type)s)) or (role:admin and ('SECONDARY':%(zone_type)s)) or (role:member and project_id:%(recordset_project_id)s and ('PRIMARY':%(zone_type)s))"
```

`all_tenants` lets Designate list zones and recordsets outside the credential's
project. The recordset rules grant generated recordset management, but not zone
create, update, delete, transfer, import, export, or managed-record editing.

Apply the overrides with a focused reconfigure:

```bash
kolla-ansible reconfigure \
  -i /path/to/multinode \
  -t neutron,designate \
  --configdir /etc/kolla
```

After the play finishes, confirm the relevant containers are healthy and test
the intended API surface with the reconciler credential before running the
controller.

### Application Credential

Create the custom roles and assign them only to the reconciler service user in
the `service` project:

```bash
openstack role create network_inventory_reader
openstack role create dns_reconciler
openstack user create --domain Default --project service --password-prompt fip-dns-reconciler
openstack role add --user fip-dns-reconciler --project service network_inventory_reader
openstack role add --user fip-dns-reconciler --project service dns_reconciler
```

Then authenticate as that service user and create a restricted
application credential. The access-rule service names are Keystone service types;
confirm them with `openstack catalog list` if your deployment uses custom types.
Do not use `--unrestricted`.

`access-rules.json`:

```json
[
  {"service": "network", "method": "GET", "path": "/v2.0/floatingips"},
  {"service": "network", "method": "GET", "path": "/v2.0/floatingips/*"},
  {"service": "dns", "method": "GET", "path": "/v2/zones"},
  {"service": "dns", "method": "GET", "path": "/v2/zones/*"},
  {"service": "dns", "method": "GET", "path": "/v2/zones/*/recordsets"},
  {"service": "dns", "method": "GET", "path": "/v2/zones/*/recordsets/*"},
  {"service": "dns", "method": "POST", "path": "/v2/zones/*/recordsets"},
  {"service": "dns", "method": "PUT", "path": "/v2/zones/*/recordsets/*"},
  {"service": "dns", "method": "PATCH", "path": "/v2/zones/*/recordsets/*"},
  {"service": "dns", "method": "DELETE", "path": "/v2/zones/*/recordsets/*"}
]
```

```bash
openstack application credential create \
  --role network_inventory_reader \
  --role dns_reconciler \
  --access-rules access-rules.json \
  fip-dns-reconciler
```

Store the returned application credential ID and secret in a root-owned
`clouds.yaml`, then mount that file into the reconciler container. The secret is
shown only once. Do not bake credentials into the image.

```yaml
clouds:
  fip-dns-reconciler:
    auth_type: v3applicationcredential
    auth:
      auth_url: https://openstack.example.net:5000
      application_credential_id: <id>
      application_credential_secret: <secret>
    region_name: RegionOne
    interface: internal
    identity_api_version: 3
```

### Reconciler Configuration

For a Kolla deployment that uses the policy model above, set:

```yaml
openstack:
  cloud: fip-dns-reconciler

dns:
  base_domain: apps.example.net.
  zone_strategy: single_zone
  all_projects: true

neutron_metadata:
  update_description: false
  update_tags: false
```

Set `dns.all_projects: true` so the reconciler requests all-project Designate
zone and recordset discovery. Keep Neutron metadata writes disabled unless the
credential is intentionally granted the corresponding Neutron update policies.

If your Designate deployment rejects the generated TXT ownership records, set:

```yaml
records:
  create_txt_metadata: false
```

In that mode, ownership is kept in managed A record descriptions instead of TXT
recordsets.

### Container Runtime

On many Kolla control nodes, the Docker bridge cannot reach the internal API
VIP. Use host networking if the reconciler needs the same internal management
network access as the Kolla containers:

```bash
docker run -d \
  --name openstack_fip_dns_reconciler \
  --restart unless-stopped \
  --network host \
  -v /etc/openstack-fip-dns-reconciler/clouds.yaml:/etc/openstack/clouds.yaml:ro \
  -v /etc/openstack-fip-dns-reconciler/config.yaml:/etc/openstack-fip-dns-reconciler/config.yaml:ro \
  ghcr.io/armeldemarsac92/openstack-fip-dns-reconciler:latest
```

Run a one-shot dry run before starting the persistent container:

```bash
docker run --rm --network host \
  -v /etc/openstack-fip-dns-reconciler/clouds.yaml:/etc/openstack/clouds.yaml:ro \
  -v /etc/openstack-fip-dns-reconciler/config.yaml:/etc/openstack-fip-dns-reconciler/config.yaml:ro \
  ghcr.io/armeldemarsac92/openstack-fip-dns-reconciler:latest \
  --config /etc/openstack-fip-dns-reconciler/config.yaml \
  --once \
  --dry-run
```

A healthy pass should discover floating IPs and managed DNS records, build a
plan, and finish with `error_count=0`.

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
