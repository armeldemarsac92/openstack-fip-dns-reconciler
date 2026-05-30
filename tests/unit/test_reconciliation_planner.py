from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel, DnsZoneName
from openstack_fip_dns_reconciler.domain.models.dns_record import DnsRecordType, GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.floating_ip import FloatingIp
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
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
        label = self._labels.pop(0)
        return DnsLabel(label)


def _planner(labels: list[str] | None = None) -> ReconciliationPlanner:
    return ReconciliationPlanner(
        label_generator=FixedLabelGenerator(labels or ["x7k9m2q4pa"]),
        project_id_label_generator=ProjectIdLabelGenerator(ProjectIdLabelMode.SHORT, 8),
        fqdn_builder=FqdnBuilder("fip.internal.mycloud.net."),
        ownership_parser=OwnershipParser("openstack-fip-dns-reconciler"),
        options=ReconciliationPlanningOptions(
            managed_by="openstack-fip-dns-reconciler",
            ttl=60,
        ),
    )


def _records_for_fip(
    *,
    fip_id: str = "fip-1",
    project_id: str = "8ab1c22f4d6e4f19a21c4d8f23bb912a",
    address: str = "10.50.0.42",
    fqdn: str = "x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net.",
) -> list[GeneratedDnsRecord]:
    zone = DnsZoneName("fip.internal.mycloud.net.")
    ownership = RecordOwnership(
        managed_by="openstack-fip-dns-reconciler",
        fip_id=fip_id,
        project_id=project_id,
    )
    return [
        GeneratedDnsRecord(
            fqdn=fqdn,
            record_type=DnsRecordType.A,
            records=(address,),
            zone_name=zone,
            ttl=60,
            project_id=project_id,
            ownership=ownership,
        ),
        GeneratedDnsRecord(
            fqdn=fqdn,
            record_type=DnsRecordType.TXT,
            records=(ownership.to_txt_value(),),
            zone_name=zone,
            ttl=60,
            project_id=project_id,
            ownership=ownership,
        ),
    ]


def test_planner_creates_a_and_txt_records_for_new_floating_ip() -> None:
    floating_ip = FloatingIp(
        id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
        address="10.50.0.42",
    )

    plan = _planner().plan([floating_ip], [])

    assert [record.record_type for record in plan.records_to_create] == [
        DnsRecordType.A,
        DnsRecordType.TXT,
    ]
    assert plan.records_to_create[0].fqdn == "x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net."
    assert plan.floating_ip_metadata_updates[0].description == (
        "Auto DNS: x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net."
    )


def test_planner_updates_a_record_when_address_changes() -> None:
    floating_ip = FloatingIp(
        id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
        address="10.50.0.99",
    )

    plan = _planner().plan([floating_ip], _records_for_fip(address="10.50.0.42"))

    assert len(plan.records_to_update) == 1
    assert plan.records_to_update[0].record_type == DnsRecordType.A
    assert plan.records_to_update[0].records == ("10.50.0.99",)


def test_planner_deletes_stale_managed_records() -> None:
    plan = _planner().plan([], _records_for_fip())

    assert [record.record_type for record in plan.records_to_delete] == [
        DnsRecordType.A,
        DnsRecordType.TXT,
    ]


def test_planner_repairs_missing_txt_record_for_owned_a_record() -> None:
    zone = DnsZoneName("fip.internal.mycloud.net.")
    ownership = RecordOwnership(
        managed_by="openstack-fip-dns-reconciler",
        fip_id="fip-1",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
    )
    owned_a_record = GeneratedDnsRecord(
        fqdn="x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net.",
        record_type=DnsRecordType.A,
        records=("10.50.0.42",),
        zone_name=zone,
        ttl=60,
        project_id=ownership.project_id,
        ownership=ownership,
    )
    floating_ip = FloatingIp(
        id="fip-1",
        project_id=ownership.project_id,
        address="10.50.0.42",
    )

    plan = _planner().plan([floating_ip], [owned_a_record])

    assert [record.record_type for record in plan.records_to_create] == [DnsRecordType.TXT]


def test_planner_ignores_unmanaged_records_for_cleanup() -> None:
    zone = DnsZoneName("fip.internal.mycloud.net.")
    unmanaged = GeneratedDnsRecord(
        fqdn="manual.fip.internal.mycloud.net.",
        record_type=DnsRecordType.A,
        records=("10.50.0.42",),
        zone_name=zone,
        ttl=60,
        project_id="project",
    )

    plan = _planner().plan([], [unmanaged])

    assert not plan.records_to_delete
