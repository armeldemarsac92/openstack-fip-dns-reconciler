import re
from dataclasses import dataclass

from openstack_fip_dns_reconciler.domain.exceptions import DomainError

_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class DnsLabel:
    value: str

    def __post_init__(self) -> None:
        if not _DNS_LABEL_RE.fullmatch(self.value):
            raise DomainError(f"Invalid DNS label: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DnsZoneName:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized:
            raise DomainError("DNS zone name must not be empty")
        if not normalized.endswith("."):
            normalized = f"{normalized}."
        labels = normalized.rstrip(".").split(".")
        for label in labels:
            DnsLabel(label)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
