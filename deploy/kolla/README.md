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
4. Share the generated Designate zone with the `service` project.
5. Create a restricted application credential for a `fip-dns-reconciler` user in
   the `service` project.
6. Configure the reconciler with `dns.all_projects: true` and disable Neutron
   metadata writes unless the credential has explicit Neutron update policy.
7. Run a one-shot dry run, then start the persistent container.

Avoid granting `update_floatingip` to the inventory role unless the deployment
intentionally wants the reconciler to mutate floating IP descriptions or tags.
