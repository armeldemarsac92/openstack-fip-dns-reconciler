import re
from dataclasses import dataclass
from enum import StrEnum

from openstack_fip_dns_reconciler.domain.exceptions import DomainError
from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel

_INVALID_DNS_LABEL_CHARS_RE = re.compile(r"[^a-z0-9]+")
_REPEATED_HYPHENS_RE = re.compile(r"-+")


class ProjectIdLabelMode(StrEnum):
    FULL = "full"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class ProjectIdLabelCollision:
    label: str
    project_ids: tuple[str, ...]


class ProjectIdLabelCollisionError(DomainError):
    def __init__(self, collisions: list[ProjectIdLabelCollision]) -> None:
        self.collisions = collisions
        labels = ", ".join(collision.label for collision in collisions)
        super().__init__(f"Project ID label collision detected for labels: {labels}")


class ProjectIdLabelGenerator:
    def __init__(
        self, mode: ProjectIdLabelMode = ProjectIdLabelMode.SHORT, short_length: int = 8
    ) -> None:
        if not 1 <= short_length <= 63:
            raise ValueError("short_length must be between 1 and 63")
        self._mode = mode
        self._short_length = short_length

    def generate(self, project_id: str) -> DnsLabel:
        sanitized = sanitize_project_id(project_id)
        if self._mode == ProjectIdLabelMode.SHORT:
            return DnsLabel(sanitized[: self._short_length])
        if len(sanitized) > 63:
            raise DomainError("Sanitized project_id exceeds the DNS label length limit")
        return DnsLabel(sanitized)

    def detect_collisions(self, project_ids: list[str]) -> list[ProjectIdLabelCollision]:
        labels: dict[str, set[str]] = {}
        for project_id in project_ids:
            label = self.generate(project_id).value
            labels.setdefault(label, set()).add(project_id)
        return [
            ProjectIdLabelCollision(label=label, project_ids=tuple(sorted(ids)))
            for label, ids in sorted(labels.items())
            if len(ids) > 1
        ]

    def assert_no_collisions(self, project_ids: list[str]) -> None:
        collisions = self.detect_collisions(project_ids)
        if collisions:
            raise ProjectIdLabelCollisionError(collisions)


def sanitize_project_id(project_id: str) -> str:
    sanitized = project_id.strip().lower()
    sanitized = _INVALID_DNS_LABEL_CHARS_RE.sub("-", sanitized)
    sanitized = _REPEATED_HYPHENS_RE.sub("-", sanitized).strip("-")
    if not sanitized:
        raise DomainError("project_id cannot be converted into a DNS-safe label")
    return sanitized
