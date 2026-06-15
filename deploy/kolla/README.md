# Kolla-Ansible Deployment Notes

This directory contains operator notes for running the reconciler beside a
Kolla-Ansible OpenStack deployment. Kolla-Ansible is used only to distribute and
reload OpenStack service policy overrides; the reconciler itself runs as a
normal container or systemd service.

For the full walkthrough, see the main README section `Kolla-Ansible Notes`.

Minimum checklist:

1. Create custom Keystone roles: `network_inventory_reader` and
   `dns_reconciler`.
2. Install Neutron and Designate policy overrides under `/etc/kolla/config`.
3. Run `kolla-ansible reconfigure -t neutron,designate`.
4. For a single shared generated zone, share that zone with the `service`
   project.
5. For tenant-isolated generated zones, enable per-project zone creation and
   allow the reconciler to create generated zones with the floating IP owner
   project as `project_id`.
6. Create a restricted application credential for a `fip-dns-reconciler` user in
   the `service` project.
7. Configure the reconciler with `dns.all_projects: true` and disable Neutron
   metadata writes unless the credential has explicit Neutron update policy.
8. For tenant-isolated visibility, use `dns.zone_strategy: per_project_zone` and
   `dns.create_missing_project_zones: true`; the reconciler creates generated
   zones with `project_id` set to the floating IP owner project.
9. Run a one-shot dry run, then start the persistent container.

Avoid granting `update_floatingip` to the inventory role unless the deployment
intentionally wants the reconciler to mutate floating IP descriptions or tags.

If the reconciler should create missing per-project generated zones, enable:

```yaml
dns:
  zone_strategy: per_project_zone
  all_projects: true
  create_missing_project_zones: true
  project_zone_email: hostmaster@apps.mustelinet.com
```

In that mode, the reconciler creates each zone with `project_id` set to the
floating IP owner project. Project members can read/list their generated records
when Designate policy allows normal project members or readers to access
project-owned zones. The service user also needs the generated-zone create rule;
do not grant it update/delete rights for zones unless you intentionally add zone
lifecycle management later.

Keep generated zones controller-written and tenant-readable. Do not rely on
per-recordset read-only policy inside a tenant-writable zone.
