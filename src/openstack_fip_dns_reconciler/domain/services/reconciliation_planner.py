from dataclasses import dataclass

from openstack_fip_dns_reconciler.domain.exceptions import DomainError
from openstack_fip_dns_reconciler.domain.models.dns_record import (
    DesiredDnsRecordSet,
    DnsRecordType,
    GeneratedDnsRecord,
)
from openstack_fip_dns_reconciler.domain.models.floating_ip import FloatingIp
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
from openstack_fip_dns_reconciler.domain.models.reconciliation_plan import (
    FloatingIpMetadataUpdate,
    ReconciliationPlan,
)
from openstack_fip_dns_reconciler.domain.services.dns_label_generator import DnsLabelGenerator
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import FqdnBuilder
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.domain.services.project_id_label_generator import (
    ProjectIdLabelGenerator,
)


@dataclass(frozen=True, slots=True)
class ReconciliationPlanningOptions:
    managed_by: str
    ttl: int
    create_txt_metadata: bool = True
    delete_stale_records: bool = True
    update_description: bool = True
    description_template: str = "Auto DNS: {fqdn}"
    update_tags: bool = True
    tag_templates: tuple[str, ...] = (
        "auto-dns",
        "dns-label:{random_label}",
        "dns-project:{project_id_label}",
    )


@dataclass(frozen=True, slots=True)
class _ManagedRecordGroup:
    ownership: RecordOwnership
    txt_record: GeneratedDnsRecord
    a_record: GeneratedDnsRecord | None


class ReconciliationPlanner:
    def __init__(
        self,
        label_generator: DnsLabelGenerator,
        project_id_label_generator: ProjectIdLabelGenerator,
        fqdn_builder: FqdnBuilder,
        ownership_parser: OwnershipParser,
        options: ReconciliationPlanningOptions,
    ) -> None:
        self._label_generator = label_generator
        self._project_id_label_generator = project_id_label_generator
        self._fqdn_builder = fqdn_builder
        self._ownership_parser = ownership_parser
        self._options = options

    def plan(
        self,
        floating_ips: list[FloatingIp],
        managed_records: list[GeneratedDnsRecord],
    ) -> ReconciliationPlan:
        self._project_id_label_generator.assert_no_collisions(
            sorted({floating_ip.project_id for floating_ip in floating_ips})
        )
        groups_by_fip_id = self._group_managed_records(managed_records)
        current_fip_ids = {floating_ip.id for floating_ip in floating_ips}
        used_fqdns = {record.fqdn for record in managed_records}

        records_to_create: list[GeneratedDnsRecord] = []
        records_to_update: list[GeneratedDnsRecord] = []
        records_to_delete: list[GeneratedDnsRecord] = []
        metadata_updates: list[FloatingIpMetadataUpdate] = []

        for floating_ip in floating_ips:
            group = groups_by_fip_id.get(floating_ip.id)
            if group is None:
                desired = self._new_desired_record_set(floating_ip, used_fqdns)
                used_fqdns.add(desired.fqdn)
                records_to_create.append(desired.a_record())
                if self._options.create_txt_metadata:
                    records_to_create.append(desired.txt_record())
            else:
                desired = self._desired_from_existing(floating_ip, group)
                if group.a_record is None:
                    records_to_create.append(desired.a_record())
                elif group.a_record.records != (floating_ip.address,):
                    records_to_update.append(desired.a_record())
                if self._options.create_txt_metadata and group.txt_record.records != (
                    desired.ownership.to_txt_value(),
                ):
                    records_to_update.append(desired.txt_record())

            metadata_update = self._metadata_update_for(floating_ip, desired)
            if metadata_update is not None:
                metadata_updates.append(metadata_update)

        if self._options.delete_stale_records:
            for group in groups_by_fip_id.values():
                if group.ownership.fip_id in current_fip_ids:
                    continue
                if group.a_record is not None:
                    records_to_delete.append(group.a_record)
                records_to_delete.append(group.txt_record)

        return ReconciliationPlan(
            records_to_create=tuple(records_to_create),
            records_to_update=tuple(records_to_update),
            records_to_delete=tuple(records_to_delete),
            floating_ip_metadata_updates=tuple(metadata_updates),
        )

    def _group_managed_records(
        self,
        records: list[GeneratedDnsRecord],
    ) -> dict[str, _ManagedRecordGroup]:
        a_records_by_fqdn = {
            record.fqdn: record for record in records if record.record_type == DnsRecordType.A
        }
        groups: dict[str, _ManagedRecordGroup] = {}
        for record in records:
            if record.record_type != DnsRecordType.TXT:
                continue
            ownership = record.ownership or self._parse_txt_ownership(record)
            if ownership is None:
                continue
            groups[ownership.fip_id] = _ManagedRecordGroup(
                ownership=ownership,
                txt_record=record,
                a_record=a_records_by_fqdn.get(record.fqdn),
            )
        return groups

    def _parse_txt_ownership(self, record: GeneratedDnsRecord) -> RecordOwnership | None:
        for value in record.records:
            ownership = self._ownership_parser.parse(value)
            if ownership is not None:
                return ownership
        return None

    def _new_desired_record_set(
        self,
        floating_ip: FloatingIp,
        used_fqdns: set[str],
    ) -> DesiredDnsRecordSet:
        project_id_label = self._project_id_label_generator.generate(floating_ip.project_id)
        for _ in range(5):
            random_label = self._label_generator.generate()
            fqdn_result = self._fqdn_builder.build(random_label.value, project_id_label.value)
            if fqdn_result.fqdn not in used_fqdns:
                ownership = RecordOwnership(
                    managed_by=self._options.managed_by,
                    fip_id=floating_ip.id,
                    project_id=floating_ip.project_id,
                )
                return DesiredDnsRecordSet(
                    fip_id=floating_ip.id,
                    project_id=floating_ip.project_id,
                    project_id_label=project_id_label.value,
                    random_label=random_label.value,
                    fqdn=fqdn_result.fqdn,
                    address=floating_ip.address,
                    zone_name=fqdn_result.zone_name,
                    ttl=self._options.ttl,
                    ownership=ownership,
                )
        raise DomainError("Unable to generate a unique DNS label after 5 attempts")

    def _desired_from_existing(
        self,
        floating_ip: FloatingIp,
        group: _ManagedRecordGroup,
    ) -> DesiredDnsRecordSet:
        random_label = group.txt_record.fqdn.split(".", maxsplit=1)[0]
        project_id_label = self._project_id_label_generator.generate(floating_ip.project_id)
        ownership = RecordOwnership(
            managed_by=self._options.managed_by,
            fip_id=floating_ip.id,
            project_id=floating_ip.project_id,
        )
        return DesiredDnsRecordSet(
            fip_id=floating_ip.id,
            project_id=floating_ip.project_id,
            project_id_label=project_id_label.value,
            random_label=random_label,
            fqdn=group.txt_record.fqdn,
            address=floating_ip.address,
            zone_name=group.txt_record.zone_name,
            ttl=self._options.ttl,
            ownership=ownership,
        )

    def _metadata_update_for(
        self,
        floating_ip: FloatingIp,
        desired: DesiredDnsRecordSet,
    ) -> FloatingIpMetadataUpdate | None:
        description = None
        tags: tuple[str, ...] = ()
        render_values = {
            "fqdn": desired.fqdn,
            "random_label": desired.random_label,
            "project_id_label": desired.project_id_label,
            "project_id": desired.project_id,
            "address": desired.address,
        }
        if self._options.update_description:
            wanted_description = self._options.description_template.format(**render_values)
            if floating_ip.description != wanted_description:
                description = wanted_description
        if self._options.update_tags:
            rendered_tags = tuple(template.format(**render_values) for template in self._options.tag_templates)
            missing_tags = tuple(tag for tag in rendered_tags if tag not in floating_ip.tags)
            if missing_tags:
                tags = rendered_tags
        if description is None and not tags:
            return None
        return FloatingIpMetadataUpdate(fip_id=floating_ip.id, description=description, tags=tags)
