import logging
from typing import Any

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsZoneName
from openstack_fip_dns_reconciler.domain.models.dns_record import DnsRecordType, GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import ZoneStrategy
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError

LOG = logging.getLogger(__name__)


class OpenStackDesignateRecordRepository:
    def __init__(
        self,
        connection: Any,
        base_domain: str,
        zone_strategy: ZoneStrategy,
        ownership_parser: OwnershipParser,
        all_projects: bool = False,
        create_missing_project_zones: bool = False,
        project_zone_email: str | None = None,
        project_zone_description_template: str = (
            "Generated floating IP DNS zone for OpenStack project {project_id}"
        ),
    ) -> None:
        self._connection = connection
        self._base_domain = DnsZoneName(base_domain)
        self._zone_strategy = zone_strategy
        self._ownership_parser = ownership_parser
        self._all_projects = all_projects
        self._create_missing_project_zones = create_missing_project_zones
        self._project_zone_email = project_zone_email
        self._project_zone_description_template = project_zone_description_template

    def list_managed_records(self) -> list[GeneratedDnsRecord]:
        try:
            records = self._list_managed_records()
        except Exception as exc:
            LOG.exception("Failed to list managed Designate records")
            raise InfrastructureError("Failed to list managed Designate records") from exc
        LOG.info("Discovered managed DNS records", extra={"record_count": len(records)})
        return records

    def create_record(self, record: GeneratedDnsRecord) -> None:
        try:
            zone = self._find_or_create_required_zone(record)
            existing = self._find_recordset(zone, record)
            if existing is not None:
                self._update_existing_recordset(existing, record)
            else:
                self._connection.dns.create_recordset(zone, **self._recordset_attrs(record))
        except Exception as exc:
            LOG.exception("Failed to create Designate record", extra=_record_log_extra(record))
            raise InfrastructureError("Failed to create Designate record") from exc
        LOG.info("Created DNS record", extra=_record_log_extra(record))

    def update_record(self, record: GeneratedDnsRecord) -> None:
        try:
            zone = self._find_or_create_required_zone(record)
            existing = self._find_recordset(zone, record)
            if existing is None:
                self._connection.dns.create_recordset(zone, **self._recordset_attrs(record))
            else:
                self._update_existing_recordset(existing, record)
        except Exception as exc:
            LOG.exception("Failed to update Designate record", extra=_record_log_extra(record))
            raise InfrastructureError("Failed to update Designate record") from exc
        LOG.info("Updated DNS record", extra=_record_log_extra(record))

    def delete_record(self, record: GeneratedDnsRecord) -> None:
        try:
            zone = self._find_required_zone(record.zone_name.value)
            existing = self._find_recordset(zone, record)
            if existing is not None:
                self._connection.dns.delete_recordset(existing, zone, ignore_missing=True)
        except Exception as exc:
            LOG.exception("Failed to delete Designate record", extra=_record_log_extra(record))
            raise InfrastructureError("Failed to delete Designate record") from exc
        LOG.info("Deleted DNS record", extra=_record_log_extra(record))

    def _list_managed_records(self) -> list[GeneratedDnsRecord]:
        managed_records: list[GeneratedDnsRecord] = []
        for zone in self._managed_zones():
            zone_name = DnsZoneName(str(_resource_value(zone, "name")))
            zone_id = _resource_value(zone, "id")
            recordsets = [
                record
                for recordset in self._connection.dns.recordsets(
                    zone_id,
                    **self._scope_query(),
                )
                if (record := self._to_domain(recordset, zone_name)) is not None
            ]
            a_records_by_fqdn = {
                record.fqdn: record
                for record in recordsets
                if record.record_type == DnsRecordType.A
            }
            managed_fqdns: set[str] = set()
            for record in recordsets:
                if record.record_type != DnsRecordType.TXT:
                    continue
                ownership = self._ownership_for(record)
                if ownership is None:
                    continue
                txt_record = self._with_ownership(record, ownership)
                managed_records.append(txt_record)
                managed_fqdns.add(record.fqdn)
                a_record = a_records_by_fqdn.get(record.fqdn)
                if a_record is not None:
                    managed_records.append(self._with_ownership(a_record, ownership))
            for record in a_records_by_fqdn.values():
                if record.fqdn not in managed_fqdns and record.ownership is not None:
                    managed_records.append(record)
        return managed_records

    def _managed_zones(self) -> list[Any]:
        zones = list(self._connection.dns.zones(**self._scope_query()))
        if self._zone_strategy == ZoneStrategy.SINGLE_ZONE:
            return [
                zone
                for zone in zones
                if _normalize_name(_resource_value(zone, "name")) == self._base_domain.value
            ]
        suffix = f".{self._base_domain.value}"
        return [
            zone
            for zone in zones
            if _normalize_name(_resource_value(zone, "name")).endswith(suffix)
        ]

    def _to_domain(self, recordset: Any, zone_name: DnsZoneName) -> GeneratedDnsRecord | None:
        raw_record_type = str(_resource_value(recordset, "type")).upper()
        if raw_record_type not in {DnsRecordType.A.value, DnsRecordType.TXT.value}:
            return None
        record_type = DnsRecordType(raw_record_type)
        records = tuple(str(value) for value in (_resource_value(recordset, "records") or ()))
        project_id = str(_resource_value(recordset, "project_id") or "")
        return GeneratedDnsRecord(
            fqdn=_normalize_name(_resource_value(recordset, "name")),
            record_type=record_type,
            records=records,
            zone_name=zone_name,
            ttl=int(_resource_value(recordset, "ttl") or 300),
            project_id=project_id,
            ownership=self._ownership_parser.parse(
                str(_resource_value(recordset, "description") or "")
            ),
        )

    def _ownership_for(self, record: GeneratedDnsRecord) -> RecordOwnership | None:
        for value in record.records:
            ownership = self._ownership_parser.parse(value)
            if ownership is not None:
                return ownership
        return None

    def _with_ownership(
        self,
        record: GeneratedDnsRecord,
        ownership: RecordOwnership,
    ) -> GeneratedDnsRecord:
        return GeneratedDnsRecord(
            fqdn=record.fqdn,
            record_type=record.record_type,
            records=record.records,
            zone_name=record.zone_name,
            ttl=record.ttl,
            project_id=ownership.project_id,
            ownership=ownership,
        )

    def _find_required_zone(self, zone_name: str) -> Any:
        zone = self._find_zone_from_managed_list(zone_name)
        if zone is not None:
            return zone
        raise InfrastructureError(f"Designate zone not found: {zone_name}")

    def _find_or_create_required_zone(self, record: GeneratedDnsRecord) -> Any:
        zone = self._find_zone_from_managed_list(record.zone_name.value)
        if zone is not None:
            return zone
        if not self._can_create_project_zone(record.zone_name.value):
            raise InfrastructureError(f"Designate zone not found: {record.zone_name.value}")
        return self._create_project_zone(record)

    def _find_zone_from_managed_list(self, zone_name: str) -> Any | None:
        normalized_zone_name = _normalize_name(zone_name)
        for zone in self._managed_zones():
            if _normalize_name(_resource_value(zone, "name")) == normalized_zone_name:
                return zone
        return None

    def _can_create_project_zone(self, zone_name: str) -> bool:
        if not self._create_missing_project_zones:
            return False
        if self._zone_strategy != ZoneStrategy.PER_PROJECT_ZONE:
            return False
        if self._project_zone_email is None:
            raise InfrastructureError(
                "dns.project_zone_email is required when project zone creation is enabled"
            )
        normalized_zone_name = _normalize_name(zone_name)
        return normalized_zone_name.endswith(f".{self._base_domain.value}")

    def _create_project_zone(self, record: GeneratedDnsRecord) -> Any:
        assert self._project_zone_email is not None
        attrs = {
            "name": record.zone_name.value,
            "email": self._project_zone_email,
            "type": "PRIMARY",
            "ttl": record.ttl,
            "description": self._project_zone_description_template.format(
                project_id=record.project_id,
                zone_name=record.zone_name.value,
            ),
        }
        try:
            response = self._connection.dns.post(
                "/zones",
                json=attrs,
                headers={"X-Auth-Sudo-Project-ID": record.project_id},
                raise_exc=True,
            )
            zone = _response_json(response)
        except Exception:
            existing_zone = self._find_zone_from_managed_list(record.zone_name.value)
            if existing_zone is not None:
                return existing_zone
            raise
        LOG.info(
            "Created Designate project zone",
            extra={
                "zone_name": record.zone_name.value,
                "project_id": record.project_id,
            },
        )
        return zone

    def _find_recordset(self, zone: Any, record: GeneratedDnsRecord) -> Any | None:
        query = {
            "name": record.fqdn,
            "type": record.record_type.value,
            **self._scope_query(),
        }
        for existing in self._connection.dns.recordsets(
            _resource_value(zone, "id"),
            **query,
        ):
            if (
                _normalize_name(_resource_value(existing, "name")) == record.fqdn
                and str(_resource_value(existing, "type")).upper() == record.record_type.value
            ):
                return existing
        return None

    def _update_existing_recordset(self, existing: Any, record: GeneratedDnsRecord) -> None:
        self._connection.dns.update_recordset(existing, **self._recordset_update_attrs(record))

    def _recordset_attrs(self, record: GeneratedDnsRecord) -> dict[str, Any]:
        return {
            "name": record.fqdn,
            "type": record.record_type.value,
            "records": list(record.records),
            "ttl": record.ttl,
            "description": _record_description(record),
        }

    def _recordset_update_attrs(self, record: GeneratedDnsRecord) -> dict[str, Any]:
        return {
            "records": list(record.records),
            "ttl": record.ttl,
            "description": _record_description(record),
        }

    def _scope_query(self) -> dict[str, bool]:
        if not self._all_projects:
            return {}
        return {"all_projects": True}


def _resource_value(resource: Any, name: str) -> Any:
    if isinstance(resource, dict):
        return resource.get(name)
    return getattr(resource, name, None)


def _response_json(response: Any) -> Any:
    if hasattr(response, "json"):
        return response.json()
    return response


def _normalize_name(value: Any) -> str:
    normalized = str(value).strip().lower()
    return normalized if normalized.endswith(".") else f"{normalized}."


def _record_log_extra(record: GeneratedDnsRecord) -> dict[str, Any]:
    return {
        "fqdn": record.fqdn,
        "record_type": record.record_type.value,
        "zone_name": record.zone_name.value,
        "project_id": record.project_id,
        "fip_id": record.ownership.fip_id if record.ownership else None,
    }


def _record_description(record: GeneratedDnsRecord) -> str:
    if record.ownership is not None:
        return record.ownership.to_txt_value()
    return "managed-by=openstack-fip-dns-reconciler"
