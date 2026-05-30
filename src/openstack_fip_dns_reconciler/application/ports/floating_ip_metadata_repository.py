from typing import Protocol

from openstack_fip_dns_reconciler.domain.models.reconciliation_plan import FloatingIpMetadataUpdate


class FloatingIpMetadataRepository(Protocol):
    def apply_metadata_update(self, update: FloatingIpMetadataUpdate) -> None:
        """Apply display metadata to a floating IP."""
