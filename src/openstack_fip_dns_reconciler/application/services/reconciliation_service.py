import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from openstack_fip_dns_reconciler.application.ports.dns_record_repository import (
    DnsRecordRepository,
)
from openstack_fip_dns_reconciler.application.ports.floating_ip_metadata_repository import (
    FloatingIpMetadataRepository,
)
from openstack_fip_dns_reconciler.application.ports.floating_ip_repository import (
    FloatingIpRepository,
)
from openstack_fip_dns_reconciler.domain.models.dns_record import GeneratedDnsRecord
from openstack_fip_dns_reconciler.domain.models.reconciliation_plan import (
    FloatingIpMetadataUpdate,
    ReconciliationPlan,
)
from openstack_fip_dns_reconciler.domain.services.reconciliation_planner import (
    ReconciliationPlanner,
)

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReconciliationRunResult:
    plan: ReconciliationPlan
    error_count: int
    duration_seconds: float

    @property
    def success(self) -> bool:
        return self.error_count == 0


class FloatingIpDnsReconciliationService:
    def __init__(
        self,
        floating_ip_repository: FloatingIpRepository,
        dns_record_repository: DnsRecordRepository,
        floating_ip_metadata_repository: FloatingIpMetadataRepository,
        planner: ReconciliationPlanner,
        dry_run: bool = False,
    ) -> None:
        self._floating_ip_repository = floating_ip_repository
        self._dns_record_repository = dns_record_repository
        self._floating_ip_metadata_repository = floating_ip_metadata_repository
        self._planner = planner
        self._dry_run = dry_run

    def reconcile_once(self) -> ReconciliationRunResult:
        started_at = time.monotonic()
        floating_ips = self._floating_ip_repository.list_floating_ips()
        managed_records = self._dns_record_repository.list_managed_records()
        plan = self._planner.plan(floating_ips, managed_records)

        LOG.info(
            "Built reconciliation plan",
            extra={
                "floating_ip_count": len(floating_ips),
                "managed_record_count": len(managed_records),
                "records_to_create": len(plan.records_to_create),
                "records_to_update": len(plan.records_to_update),
                "records_to_delete": len(plan.records_to_delete),
                "metadata_updates": len(plan.floating_ip_metadata_updates),
                "dry_run": self._dry_run,
            },
        )

        error_count = 0
        if self._dry_run:
            self._log_dry_run_plan(plan)
        else:
            error_count += self._apply_records(plan.records_to_create, self._create_record)
            error_count += self._apply_records(plan.records_to_update, self._update_record)
            error_count += self._apply_records(plan.records_to_delete, self._delete_record)
            error_count += self._apply_metadata_updates(plan.floating_ip_metadata_updates)

        duration_seconds = time.monotonic() - started_at
        LOG.info(
            "Finished reconciliation",
            extra={
                "duration_seconds": round(duration_seconds, 3),
                "error_count": error_count,
                "dry_run": self._dry_run,
            },
        )
        return ReconciliationRunResult(
            plan=plan,
            error_count=error_count,
            duration_seconds=duration_seconds,
        )

    def _apply_records(
        self,
        records: tuple[GeneratedDnsRecord, ...],
        operation: Callable[[GeneratedDnsRecord], None],
    ) -> int:
        error_count = 0
        for record in records:
            try:
                operation(record)
            except Exception:
                error_count += 1
                LOG.exception(
                    "Failed to apply DNS record operation",
                    extra={
                        "fqdn": record.fqdn,
                        "record_type": record.record_type.value,
                        "project_id": record.project_id,
                        "fip_id": record.ownership.fip_id if record.ownership else None,
                    },
                )
        return error_count

    def _apply_metadata_updates(
        self,
        updates: tuple[FloatingIpMetadataUpdate, ...],
    ) -> int:
        error_count = 0
        for update in updates:
            try:
                self._floating_ip_metadata_repository.apply_metadata_update(update)
            except Exception:
                error_count += 1
                LOG.exception(
                    "Failed to apply floating IP metadata update",
                    extra={"fip_id": update.fip_id},
                )
        return error_count

    def _create_record(self, record: GeneratedDnsRecord) -> None:
        self._dns_record_repository.create_record(record)

    def _update_record(self, record: GeneratedDnsRecord) -> None:
        self._dns_record_repository.update_record(record)

    def _delete_record(self, record: GeneratedDnsRecord) -> None:
        self._dns_record_repository.delete_record(record)

    def _log_dry_run_plan(self, plan: ReconciliationPlan) -> None:
        for record in plan.records_to_create:
            LOG.info("Dry run would create DNS record", extra=_record_extra(record))
        for record in plan.records_to_update:
            LOG.info("Dry run would update DNS record", extra=_record_extra(record))
        for record in plan.records_to_delete:
            LOG.info("Dry run would delete DNS record", extra=_record_extra(record))
        for update in plan.floating_ip_metadata_updates:
            LOG.info(
                "Dry run would update floating IP metadata",
                extra={
                    "fip_id": update.fip_id,
                    "description": update.description,
                    "tags": update.tags,
                },
            )


def _record_extra(record: GeneratedDnsRecord) -> dict[str, object]:
    return {
        "fqdn": record.fqdn,
        "record_type": record.record_type.value,
        "records": record.records,
        "project_id": record.project_id,
        "fip_id": record.ownership.fip_id if record.ownership else None,
    }
