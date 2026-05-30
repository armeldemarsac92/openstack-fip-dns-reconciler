from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class FloatingIpEventType(StrEnum):
    CREATED = "floatingip.create.end"
    UPDATED = "floatingip.update.end"
    DELETED = "floatingip.delete.end"


@dataclass(frozen=True, slots=True)
class FloatingIpEvent:
    event_type: FloatingIpEventType
    floating_ip_id: str
    project_id: str | None = None


class FloatingIpEventSource(Protocol):
    def iter_events(self) -> Iterable[FloatingIpEvent]:
        """Yield floating IP events from a future Neutron notification adapter."""
