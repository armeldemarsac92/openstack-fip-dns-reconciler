from dataclasses import dataclass
from enum import StrEnum

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsZoneName
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership


class DnsRecordType(StrEnum):
    A = "A"
    TXT = "TXT"


@dataclass(frozen=True, slots=True)
class GeneratedDnsRecord:
    fqdn: str
    record_type: DnsRecordType
    records: tuple[str, ...]
    zone_name: DnsZoneName
    ttl: int
    project_id: str
    ownership: RecordOwnership | None = None

    def __post_init__(self) -> None:
        if not self.fqdn.endswith("."):
            raise ValueError("DNS record fqdn must be absolute")
        if not self.records:
            raise ValueError("DNS record must contain at least one value")
        if self.ttl < 1:
            raise ValueError("DNS record ttl must be positive")

    @property
    def identity(self) -> tuple[str, DnsRecordType]:
        return (self.fqdn, self.record_type)


@dataclass(frozen=True, slots=True)
class DesiredDnsRecordSet:
    fip_id: str
    project_id: str
    project_id_label: str
    random_label: str
    fqdn: str
    address: str
    zone_name: DnsZoneName
    ttl: int
    ownership: RecordOwnership

    def a_record(self) -> GeneratedDnsRecord:
        return GeneratedDnsRecord(
            fqdn=self.fqdn,
            record_type=DnsRecordType.A,
            records=(self.address,),
            zone_name=self.zone_name,
            ttl=self.ttl,
            project_id=self.project_id,
            ownership=self.ownership,
        )

    def txt_record(self) -> GeneratedDnsRecord:
        return GeneratedDnsRecord(
            fqdn=self.fqdn,
            record_type=DnsRecordType.TXT,
            records=(self.ownership.to_txt_value(),),
            zone_name=self.zone_name,
            ttl=self.ttl,
            project_id=self.project_id,
            ownership=self.ownership,
        )
