from dataclasses import dataclass, field

from openstack_fip_dns_reconciler.application.services.reconciliation_service import (
    FloatingIpDnsReconciliationService,
)
from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel
from openstack_fip_dns_reconciler.domain.models.dns_record import DnsRecordType, GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.floating_ip import FloatingIp
from openstack_fip_dns_reconciler.domain.models.reconciliation_plan import FloatingIpMetadataUpdate
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import FqdnBuilder
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.domain.services.project_id_label_generator import (
    ProjectIdLabelGenerator,
    ProjectIdLabelMode,
)
from openstack_fip_dns_reconciler.domain.services.reconciliation_planner import (
    ReconciliationPlanner,
    ReconciliationPlanningOptions,
)


class FixedLabelGenerator:
    def __init__(self, labels: list[str]) -> None:
        self._labels = labels

    def generate(self) -> DnsLabel:
        return DnsLabel(self._labels.pop(0))


@dataclass
class FakeFloatingIpRepository:
    floating_ips: list[FloatingIp]

    def list_floating_ips(self) -> list[FloatingIp]:
        return self.floating_ips


@dataclass
class FakeDnsRecordRepository:
    managed_records: list[GeneratedDnsRecord] = field(default_factory=list)
    created: list[GeneratedDnsRecord] = field(default_factory=list)
    updated: list[GeneratedDnsRecord] = field(default_factory=list)
    deleted: list[GeneratedDnsRecord] = field(default_factory=list)
    fail_create: bool = False

    def list_managed_records(self) -> list[GeneratedDnsRecord]:
        return self.managed_records

    def create_record(self, record: GeneratedDnsRecord) -> None:
        if self.fail_create:
            raise RuntimeError("create failed")
        self.created.append(record)

    def update_record(self, record: GeneratedDnsRecord) -> None:
        self.updated.append(record)

    def delete_record(self, record: GeneratedDnsRecord) -> None:
        self.deleted.append(record)


@dataclass
class FakeMetadataRepository:
    updates: list[FloatingIpMetadataUpdate] = field(default_factory=list)

    def apply_metadata_update(self, update: FloatingIpMetadataUpdate) -> None:
        self.updates.append(update)


def _service(
    *,
    floating_ips: list[FloatingIp],
    dns_repository: FakeDnsRecordRepository | None = None,
    metadata_repository: FakeMetadataRepository | None = None,
    dry_run: bool = False,
) -> tuple[FloatingIpDnsReconciliationService, FakeDnsRecordRepository, FakeMetadataRepository]:
    dns_repository = dns_repository or FakeDnsRecordRepository()
    metadata_repository = metadata_repository or FakeMetadataRepository()
    planner = ReconciliationPlanner(
        label_generator=FixedLabelGenerator(["x7k9m2q4pa"]),
        project_id_label_generator=ProjectIdLabelGenerator(ProjectIdLabelMode.SHORT, 8),
        fqdn_builder=FqdnBuilder("fip.internal.mycloud.net."),
        ownership_parser=OwnershipParser("openstack-fip-dns-reconciler"),
        options=ReconciliationPlanningOptions(
            managed_by="openstack-fip-dns-reconciler",
            ttl=60,
        ),
    )
    return (
        FloatingIpDnsReconciliationService(
            floating_ip_repository=FakeFloatingIpRepository(floating_ips),
            dns_record_repository=dns_repository,
            floating_ip_metadata_repository=metadata_repository,
            planner=planner,
            dry_run=dry_run,
        ),
        dns_repository,
        metadata_repository,
    )


def test_reconciliation_service_creates_records_and_metadata_with_fakes() -> None:
    floating_ip = FloatingIp(
        id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
        address="10.50.0.42",
    )
    service, dns_repository, metadata_repository = _service(floating_ips=[floating_ip])

    result = service.reconcile_once()

    assert result.success
    assert [record.record_type for record in dns_repository.created] == [
        DnsRecordType.A,
        DnsRecordType.TXT,
    ]
    assert metadata_repository.updates[0].fip_id == "fip-1"


def test_reconciliation_service_dry_run_does_not_write() -> None:
    floating_ip = FloatingIp(
        id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
        address="10.50.0.42",
    )
    service, dns_repository, metadata_repository = _service(
        floating_ips=[floating_ip],
        dry_run=True,
    )

    result = service.reconcile_once()

    assert result.success
    assert not dns_repository.created
    assert not metadata_repository.updates


def test_reconciliation_service_survives_record_write_failures() -> None:
    floating_ip = FloatingIp(
        id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
        address="10.50.0.42",
    )
    service, _, metadata_repository = _service(
        floating_ips=[floating_ip],
        dns_repository=FakeDnsRecordRepository(fail_create=True),
    )

    result = service.reconcile_once()

    assert not result.success
    assert result.error_count == 2
    assert metadata_repository.updates[0].fip_id == "fip-1"
