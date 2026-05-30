from dataclasses import dataclass, field

from openstack_fip_dns_reconciler.domain.models.dns_record import GeneratedDnsRecord


@dataclass(frozen=True, slots=True)
class FloatingIpMetadataUpdate:
    fip_id: str
    description: str | None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    records_to_create: tuple[GeneratedDnsRecord, ...] = field(default_factory=tuple)
    records_to_update: tuple[GeneratedDnsRecord, ...] = field(default_factory=tuple)
    records_to_delete: tuple[GeneratedDnsRecord, ...] = field(default_factory=tuple)
    floating_ip_metadata_updates: tuple[FloatingIpMetadataUpdate, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (
            self.records_to_create
            or self.records_to_update
            or self.records_to_delete
            or self.floating_ip_metadata_updates
        )
