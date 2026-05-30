from typing import Protocol

from openstack_fip_dns_reconciler.domain.models.project_identity import ProjectIdentity


class ProjectRepository(Protocol):
    def get_project(self, project_id: str) -> ProjectIdentity | None:
        """Return project identity details when available."""
