from dataclasses import dataclass

from openstack_fip_dns_reconciler.domain.exceptions import DomainError


@dataclass(frozen=True, slots=True)
class RecordOwnership:
    managed_by: str
    fip_id: str
    project_id: str

    def __post_init__(self) -> None:
        if not self.managed_by.strip():
            raise DomainError("managed_by must not be empty")
        if not self.fip_id.strip():
            raise DomainError("fip_id must not be empty")
        if not self.project_id.strip():
            raise DomainError("project_id must not be empty")

    def to_txt_value(self) -> str:
        return (
            f"managed-by={self.managed_by} "
            f"fip_id={self.fip_id} "
            f"project_id={self.project_id}"
        )
