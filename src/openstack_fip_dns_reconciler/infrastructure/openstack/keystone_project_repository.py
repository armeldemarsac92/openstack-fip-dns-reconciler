import logging
from typing import Any

from openstack_fip_dns_reconciler.domain.models.project_identity import ProjectIdentity
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError

LOG = logging.getLogger(__name__)


class OpenStackProjectRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_project(self, project_id: str) -> ProjectIdentity | None:
        try:
            project = self._connection.identity.get_project(project_id)
        except Exception as exc:
            LOG.exception("Failed to read Keystone project", extra={"project_id": project_id})
            raise InfrastructureError("Failed to read Keystone project") from exc
        if project is None:
            return None
        return ProjectIdentity(
            id=str(_resource_value(project, "id")),
            name=_resource_value(project, "name"),
        )


def _resource_value(resource: Any, name: str) -> Any:
    if isinstance(resource, dict):
        return resource.get(name)
    return getattr(resource, name, None)
