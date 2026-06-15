from dataclasses import dataclass, field
from typing import Any

import pytest

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsZoneName
from openstack_fip_dns_reconciler.domain.models.dns_record import DnsRecordType, GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import ZoneStrategy
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError
from openstack_fip_dns_reconciler.infrastructure.openstack.designate_dns_record_repository import (
    OpenStackDesignateRecordRepository,
)


@dataclass
class FakeResponse:
    payload: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self.payload


@dataclass
class FakeDnsProxy:
    zones_result: list[dict[str, Any]]
    recordsets_by_zone: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    zones_calls: list[dict[str, Any]] = field(default_factory=list)
    recordsets_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    create_calls: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    post_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    put_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    delete_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def zones(self, **query: Any) -> list[dict[str, Any]]:
        self.zones_calls.append(query)
        return self.zones_result

    def recordsets(self, zone: str, **query: Any) -> list[dict[str, Any]]:
        self.recordsets_calls.append((zone, query))
        return self.recordsets_by_zone.get(zone, [])

    def create_recordset(self, zone: dict[str, Any], **attrs: Any) -> None:
        self.create_calls.append((zone, attrs))

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append((url, kwargs))
        if url == "/zones":
            return self._create_zone(kwargs)
        if url.endswith("/recordsets"):
            return self._create_recordset(url, kwargs)
        raise AssertionError(f"Unexpected POST URL: {url}")

    def put(self, url: str, **kwargs: Any) -> FakeResponse:
        self.put_calls.append((url, kwargs))
        return FakeResponse(kwargs["json"])

    def delete(self, url: str, **kwargs: Any) -> FakeResponse:
        self.delete_calls.append((url, kwargs))
        return FakeResponse({})

    def _create_zone(self, kwargs: dict[str, Any]) -> FakeResponse:
        attrs = kwargs["json"]
        headers = kwargs["headers"]
        zone = {
            "id": f"zone-{len(self.post_calls)}",
            "name": attrs["name"],
            "project_id": headers["X-Auth-Sudo-Project-ID"],
        }
        self.zones_result.append(zone)
        return FakeResponse(zone)

    def _create_recordset(self, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        attrs = kwargs["json"]
        headers = kwargs["headers"]
        zone_id = url.split("/")[2]
        recordset = {
            "id": f"recordset-{len(self.recordsets_by_zone.get(zone_id, [])) + 1}",
            "project_id": headers["X-Auth-Sudo-Project-ID"],
            **attrs,
        }
        self.recordsets_by_zone.setdefault(zone_id, []).append(recordset)
        return FakeResponse(recordset)

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


def test_missing_per_project_zone_is_created_for_floating_ip_project() -> None:
    dns = FakeDnsProxy(zones_result=[])
    repository = _repository(
        dns,
        all_projects=True,
        zone_strategy=ZoneStrategy.PER_PROJECT_ZONE,
        create_missing_project_zones=True,
        project_zone_email="hostmaster@apps.mustelinet.com",
    )
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    repository.create_record(record)

    assert len(dns.post_calls) == 2
    url, kwargs = dns.post_calls[0]
    assert url == "/zones"
    assert kwargs["headers"] == {"X-Auth-Sudo-Project-ID": "8ab1c22f4d6e4f19a21c4d8f23bb912a"}
    assert kwargs["raise_exc"] is True
    assert kwargs["json"] == {
        "name": "8ab1c22f.apps.mustelinet.com.",
        "email": "hostmaster@apps.mustelinet.com",
        "type": "PRIMARY",
        "ttl": 60,
        "description": (
            "Generated floating IP DNS zone for OpenStack project 8ab1c22f4d6e4f19a21c4d8f23bb912a"
        ),
    }
    assert "project_id" not in kwargs["json"]
    recordset_url, recordset_kwargs = dns.post_calls[1]
    assert recordset_url == "/zones/zone-1/recordsets"
    assert recordset_kwargs["headers"] == {
        "X-Auth-Sudo-Project-ID": "8ab1c22f4d6e4f19a21c4d8f23bb912a"
    }
    assert recordset_kwargs["json"]["name"] == "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com."
    assert dns.create_calls == []
    assert dns.recordsets_calls == [
        (
            "zone-1",
            {
                "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                "type": "A",
                "all_projects": True,
            },
        )
    ]


def test_missing_zone_is_not_created_by_default() -> None:
    dns = FakeDnsProxy(zones_result=[])
    repository = _repository(dns, all_projects=True, zone_strategy=ZoneStrategy.PER_PROJECT_ZONE)
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    with pytest.raises(InfrastructureError, match="Failed to create Designate record"):
        repository.create_record(record)

    assert dns.post_calls == []


def test_per_project_recordset_create_uses_sudo_project_header() -> None:
    dns = FakeDnsProxy(
        zones_result=[
            {
                "id": "tenant-zone",
                "name": "8ab1c22f.apps.mustelinet.com.",
                "project_id": "8ab1c22f4d6e4f19a21c4d8f23bb912a",
            }
        ]
    )
    repository = _repository(dns, all_projects=True, zone_strategy=ZoneStrategy.PER_PROJECT_ZONE)
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    repository.create_record(record)

    assert dns.post_calls == [
        (
            "/zones/tenant-zone/recordsets",
            {
                "json": {
                    "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                    "type": "A",
                    "records": ["10.50.0.42"],
                    "ttl": 60,
                    "description": _ownership().to_txt_value(),
                },
                "headers": {"X-Auth-Sudo-Project-ID": "8ab1c22f4d6e4f19a21c4d8f23bb912a"},
                "raise_exc": True,
            },
        )
    ]
    assert dns.create_calls == []


def test_per_project_recordset_update_uses_sudo_project_header() -> None:
    dns = FakeDnsProxy(
        zones_result=[
            {
                "id": "tenant-zone",
                "name": "8ab1c22f.apps.mustelinet.com.",
                "project_id": "8ab1c22f4d6e4f19a21c4d8f23bb912a",
            }
        ],
        recordsets_by_zone={
            "tenant-zone": [
                {
                    "id": "recordset-1",
                    "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                    "type": "A",
                    "records": ["10.50.0.41"],
                    "ttl": 60,
                    "project_id": "8ab1c22f4d6e4f19a21c4d8f23bb912a",
                }
            ]
        },
    )
    repository = _repository(dns, all_projects=True, zone_strategy=ZoneStrategy.PER_PROJECT_ZONE)
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    repository.update_record(record)

    assert dns.put_calls == [
        (
            "/zones/tenant-zone/recordsets/recordset-1",
            {
                "json": {
                    "records": ["10.50.0.42"],
                    "ttl": 60,
                    "description": _ownership().to_txt_value(),
                },
                "headers": {"X-Auth-Sudo-Project-ID": "8ab1c22f4d6e4f19a21c4d8f23bb912a"},
                "raise_exc": True,
            },
        )
    ]


def test_per_project_recordset_delete_uses_sudo_project_header() -> None:
    dns = FakeDnsProxy(
        zones_result=[
            {
                "id": "tenant-zone",
                "name": "8ab1c22f.apps.mustelinet.com.",
                "project_id": "8ab1c22f4d6e4f19a21c4d8f23bb912a",
            }
        ],
        recordsets_by_zone={
            "tenant-zone": [
                {
                    "id": "recordset-1",
                    "name": "x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
                    "type": "A",
                    "records": ["10.50.0.42"],
                    "ttl": 60,
                    "project_id": "8ab1c22f4d6e4f19a21c4d8f23bb912a",
                }
            ]
        },
    )
    repository = _repository(dns, all_projects=True, zone_strategy=ZoneStrategy.PER_PROJECT_ZONE)
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    repository.delete_record(record)

    assert dns.delete_calls == [
        (
            "/zones/tenant-zone/recordsets/recordset-1",
            {
                "headers": {"X-Auth-Sudo-Project-ID": "8ab1c22f4d6e4f19a21c4d8f23bb912a"},
                "raise_exc": False,
            },
        )
    ]


def test_per_project_zone_creation_does_not_require_root_zone() -> None:
    dns = FakeDnsProxy(zones_result=[{"id": "root-zone", "name": "apps.mustelinet.com."}])
    repository = _repository(
        dns,
        all_projects=True,
        zone_strategy=ZoneStrategy.PER_PROJECT_ZONE,
        create_missing_project_zones=True,
        project_zone_email="hostmaster@apps.mustelinet.com",
    )
    record = _a_record(zone_name="8ab1c22f.apps.mustelinet.com.")

    repository.create_record(record)

    assert dns.post_calls[0][0] == "/zones"
    assert dns.post_calls[0][1]["json"]["name"] == "8ab1c22f.apps.mustelinet.com."
    assert all(zone_id != "root-zone" for zone_id, _query in dns.recordsets_calls)


def _repository(
    dns: FakeDnsProxy,
    *,
    all_projects: bool = False,
    zone_strategy: ZoneStrategy = ZoneStrategy.SINGLE_ZONE,
    create_missing_project_zones: bool = False,
    project_zone_email: str | None = None,
) -> OpenStackDesignateRecordRepository:
    return OpenStackDesignateRecordRepository(
        connection=FakeConnection(dns),
        base_domain="apps.mustelinet.com.",
        zone_strategy=zone_strategy,
        ownership_parser=OwnershipParser("openstack-fip-dns-reconciler"),
        all_projects=all_projects,
        create_missing_project_zones=create_missing_project_zones,
        project_zone_email=project_zone_email,
    )


def _ownership() -> RecordOwnership:
    return RecordOwnership(
        managed_by="openstack-fip-dns-reconciler",
        fip_id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
    )


def _a_record(zone_name: str = "apps.mustelinet.com.") -> GeneratedDnsRecord:
    ownership = _ownership()
    return GeneratedDnsRecord(
        fqdn="x7k9m2q4pa.8ab1c22f.apps.mustelinet.com.",
        record_type=DnsRecordType.A,
        records=("10.50.0.42",),
        zone_name=DnsZoneName(zone_name),
        ttl=60,
        project_id=ownership.project_id,
        ownership=ownership,
    )
