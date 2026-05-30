import logging
from typing import Any

from openstack_fip_dns_reconciler.domain.models.reconciliation_plan import FloatingIpMetadataUpdate
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError
from openstack_fip_dns_reconciler.infrastructure.openstack.neutron_floating_ip_repository import (
    _resource_value,
)

LOG = logging.getLogger(__name__)


class OpenStackFloatingIpMetadataRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def apply_metadata_update(self, update: FloatingIpMetadataUpdate) -> None:
        try:
            resource = self._connection.network.get_ip(update.fip_id)
            if resource is None:
                raise InfrastructureError(f"Floating IP not found: {update.fip_id}")
            if update.description is not None:
                resource = self._connection.network.update_ip(
                    update.fip_id,
                    description=update.description,
                )
            if update.tags:
                current_tags = set(_resource_value(resource, "tags") or ())
                desired_tags = sorted(current_tags.union(update.tags))
                self._connection.network.set_tags(resource, desired_tags)
        except InfrastructureError:
            raise
        except Exception as exc:
            LOG.exception(
                "Failed to update floating IP metadata",
                extra={"fip_id": update.fip_id},
            )
            raise InfrastructureError("Failed to update floating IP metadata") from exc
        LOG.info(
            "Updated floating IP metadata",
            extra={"fip_id": update.fip_id, "tags": update.tags},
        )
