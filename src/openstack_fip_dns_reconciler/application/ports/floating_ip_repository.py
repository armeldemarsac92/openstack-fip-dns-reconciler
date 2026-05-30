from typing import Protocol

from openstack_fip_dns_reconciler.domain.models.floating_ip import FloatingIp


class FloatingIpRepository(Protocol):
    def list_floating_ips(self) -> list[FloatingIp]:
        """Return floating IPs visible to the reconciler."""
