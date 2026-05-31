from dataclasses import dataclass, field
from typing import Any

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsZoneName
from openstack_fip_dns_reconciler.domain.models.dns_record import DnsRecordType, GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import ZoneStrategy
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.infrastructure.openstack.designate_dns_record_repository import (
    OpenStackDesignateRecordRepository,
)


@dataclass
class FakeDnsProxy:
    zones_result: list[dict[str, Any]]
    recordsets_by_zone: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    zones_calls: list[dict[str, Any]] = field(default_factory=list)
    recordsets_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    create_calls: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)

    def zones(self, **query: Any) -> list[dict[str, Any]]:
        self.zones_calls.append(query)
        return self.zones_result

    def recordsets(self, zone: str, **query: Any) -> list[dict[str, Any]]:
        self.recordsets_calls.append((zone, query))
        return self.recordsets_by_zone.get(zone, [])

    def create_recordset(self, zone: dict[str, Any], **attrs: Any) -> None:
        self.create_calls.append((zone, attrs))

    def find_zone(self, name_or_id: str, ignore_missing: bool = True) -> None:
        raise AssertionError("find_zone must not be used by the Designate repository")


@dataclass
class FakeConnection:
    dns: FakeDnsProxy


def test_single_zone_lookup_uses_all_project_zone_listing() -> None:
    dns = FakeDnsProxy(
        zones_result=[
            {"id": "other-zone", "name": "other.example."},
            {"id": "managed-zone", "name": "apps.mustelinet.com."},
        ]
    )
    repository = _repository(dns, all_projects=True)
    record = _a_record()

    repository.create_record(record)

    assert dns.zones_calls == [{"all_projects": True}]
    assert dns.recordsets_calls == [
        (
            "managed-zone",
            {
                "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                "type": "A",
                "all_projects": True,
            },
        )
    ]
    assert dns.create_calls[0][0]["id"] == "managed-zone"


def test_managed_record_listing_uses_all_project_mode() -> None:
    ownership = _ownership()
    dns = FakeDnsProxy(
        zones_result=[{"id": "managed-zone", "name": "apps.mustelinet.com."}],
        recordsets_by_zone={
            "managed-zone": [
                {
                    "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                    "type": "TXT",
                    "records": [ownership.to_txt_value()],
                    "ttl": 60,
                    "project_id": ownership.project_id,
                }
            ]
        },
    )
    repository = _repository(dns, all_projects=True)

    records = repository.list_managed_records()

    assert len(records) == 1
    assert records[0].ownership == ownership
    assert dns.zones_calls == [{"all_projects": True}]
    assert dns.recordsets_calls == [("managed-zone", {"all_projects": True})]


def test_default_designate_discovery_remains_project_scoped() -> None:
    dns = FakeDnsProxy(
        zones_result=[{"id": "managed-zone", "name": "apps.mustelinet.com."}],
        recordsets_by_zone={"managed-zone": []},
    )
    repository = _repository(dns)

    repository.list_managed_records()

    assert dns.zones_calls == [{}]
    assert dns.recordsets_calls == [("managed-zone", {})]


def _repository(
    dns: FakeDnsProxy,
    *,
    all_projects: bool = False,
) -> OpenStackDesignateRecordRepository:
    return OpenStackDesignateRecordRepository(
        connection=FakeConnection(dns),
        base_domain="apps.mustelinet.com.",
        zone_strategy=ZoneStrategy.SINGLE_ZONE,
        ownership_parser=OwnershipParser("openstack-fip-dns-reconciler"),
        all_projects=all_projects,
    )


def _ownership() -> RecordOwnership:
    return RecordOwnership(
        managed_by="openstack-fip-dns-reconciler",
        fip_id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
    )


def _a_record() -> GeneratedDnsRecord:
    ownership = _ownership()
    return GeneratedDnsRecord(
        fqdn="x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
        record_type=DnsRecordType.A,
        records=("10.50.0.42",),
        zone_name=DnsZoneName("apps.mustelinet.com."),
        ttl=60,
        project_id=ownership.project_id,
        ownership=ownership,
    )
