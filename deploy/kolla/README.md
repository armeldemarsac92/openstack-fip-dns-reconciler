# Kolla-Ansible Deployment Notes

Run the reconciler as a small sidecar-style service container or systemd service
on a control node with network access to Keystone, Neutron, and Designate.

Mount credentials rather than baking them into the image:

```bash
docker run --rm \
  -v /etc/kolla/clouds.yaml:/etc/openstack/clouds.yaml:ro \
  -v ./config.yaml:/etc/openstack-fip-dns-reconciler/config.yaml:ro \
  openstack-fip-dns-reconciler:latest
```

For a Kolla host, point the controller at a dedicated service user in
`clouds.yaml`:

```yaml
clouds:
  fip-dns-reconciler:
    auth:
      auth_url: https://openstack.example.net:5000
      username: fip-dns-reconciler
      password: change-me
      project_name: service
      user_domain_name: Default
      project_domain_name: Default
    region_name: RegionOne
    interface: internal
    identity_api_version: 3
```

The service user needs cross-project floating IP read access and generated-zone
recordset write access. In a hardened cloud, model this with roles such as:

```text
network_inventory_reader
dns_reconciler
```

Policy sketch:

```yaml
# Neutron policy concept
get_floatingip: "role:network_inventory_reader or project_id:%(project_id)s"
get_floatingips: "role:network_inventory_reader"
update_floatingip: "role:network_inventory_reader"

# Designate policy concept
get_zones: "role:dns_reconciler or role:reader"
get_recordsets: "role:dns_reconciler or role:reader"
create_recordset: "role:dns_reconciler"
update_recordset: "role:dns_reconciler"
delete_recordset: "role:dns_reconciler"
```

Keep generated zones controller-written and tenant-readable. Do not rely on
per-recordset read-only policy inside a tenant-writable zone.
