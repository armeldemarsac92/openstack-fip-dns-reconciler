import logging
from typing import Any

from openstack_fip_dns_reconciler.domain.models.floating_ip import FloatingIp
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError

LOG = logging.getLogger(__name__)


class OpenStackFloatingIpRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_floating_ips(self) -> list[FloatingIp]:
        try:
            floating_ips = [
                self._to_domain(resource) for resource in self._connection.network.ips()
            ]
        except Exception as exc:
            LOG.exception("Failed to list Neutron floating IPs")
            raise InfrastructureError("Failed to list Neutron floating IPs") from exc
        LOG.info("Discovered floating IPs", extra={"floating_ip_count": len(floating_ips)})
        return floating_ips

    def _to_domain(self, resource: Any) -> FloatingIp:
        resource_id = _resource_value(resource, "id")
        project_id = _resource_value(resource, "project_id") or _resource_value(resource, "tenant_id")
        address = _resource_value(resource, "floating_ip_address")
        if not resource_id or not project_id or not address:
            raise InfrastructureError("Floating IP resource is missing required fields")
        return FloatingIp(
            id=str(resource_id),
            project_id=str(project_id),
            address=str(address),
            description=_resource_value(resource, "description"),
            tags=frozenset(_resource_value(resource, "tags") or ()),
        )


def _resource_value(resource: Any, name: str) -> Any:
    if isinstance(resource, dict):
        return resource.get(name)
    return getattr(resource, name, None)
