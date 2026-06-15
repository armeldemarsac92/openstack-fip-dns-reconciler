import argparse
import logging
import signal
from collections.abc import Sequence

from openstack_fip_dns_reconciler.application.services.reconciliation_service import (
    FloatingIpDnsReconciliationService,
)
from openstack_fip_dns_reconciler.config.loader import load_settings
from openstack_fip_dns_reconciler.config.settings import AppSettings, default_config_path
from openstack_fip_dns_reconciler.domain.services.dns_label_generator import Base32DnsLabelGenerator
from openstack_fip_dns_reconciler.domain.services.fqdn_builder import (
    FqdnBuilder,
    ZoneStrategy,
)
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser
from openstack_fip_dns_reconciler.domain.services.project_id_label_generator import (
    ProjectIdLabelGenerator,
    ProjectIdLabelMode,
)
from openstack_fip_dns_reconciler.domain.services.reconciliation_planner import (
    ReconciliationPlanner,
    ReconciliationPlanningOptions,
)
from openstack_fip_dns_reconciler.endpoints.worker import ReconcilerWorker
from openstack_fip_dns_reconciler.infrastructure.openstack import (
    OpenStackConnectionFactory,
    OpenStackDesignateRecordRepository,
    OpenStackFloatingIpMetadataRepository,
    OpenStackFloatingIpRepository,
)
from openstack_fip_dns_reconciler.observability.logging_config import configure_logging

LOG = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging(args.log_level)
    settings = load_settings(args.config)
    if args.dry_run:
        settings = settings.model_copy(
            update={
                "controller": settings.controller.model_copy(update={"dry_run": True}),
            }
        )
    LOG.info("Configuration loaded", extra={"config": str(args.config)})
    service = build_service(settings)
    if args.once:
        result = service.reconcile_once()
        return 0 if result.success else 1

    worker = ReconcilerWorker(service, settings.controller.poll_interval_seconds)
    _install_signal_handlers(worker)
    worker.run_forever()
    return 0


def build_service(settings: AppSettings) -> FloatingIpDnsReconciliationService:
    connection = OpenStackConnectionFactory(settings.openstack).create()
    ownership_parser = OwnershipParser(settings.records.managed_by)
    zone_strategy = ZoneStrategy(settings.dns.zone_strategy.value)
    project_id_label_mode = ProjectIdLabelMode(settings.dns.project_id_label_mode.value)
    planner = ReconciliationPlanner(
        label_generator=Base32DnsLabelGenerator(settings.dns.label_length),
        project_id_label_generator=ProjectIdLabelGenerator(
            mode=project_id_label_mode,
            short_length=settings.dns.project_id_short_length,
        ),
        fqdn_builder=FqdnBuilder(
            base_domain=settings.dns.base_domain,
            zone_strategy=zone_strategy,
            template=settings.records.fqdn_template,
        ),
        ownership_parser=ownership_parser,
        options=ReconciliationPlanningOptions(
            managed_by=settings.records.managed_by,
            ttl=settings.dns.ttl,
            create_txt_metadata=settings.records.create_txt_metadata,
            delete_stale_records=settings.cleanup.delete_stale_records,
            update_description=settings.neutron_metadata.update_description,
            description_template=settings.neutron_metadata.description_template,
            update_tags=settings.neutron_metadata.update_tags,
            tag_templates=tuple(settings.neutron_metadata.tags),
        ),
    )
    return FloatingIpDnsReconciliationService(
        floating_ip_repository=OpenStackFloatingIpRepository(connection),
        dns_record_repository=OpenStackDesignateRecordRepository(
            connection=connection,
            base_domain=settings.dns.base_domain,
            zone_strategy=zone_strategy,
            ownership_parser=ownership_parser,
            all_projects=settings.dns.all_projects,
            create_missing_project_zones=settings.dns.create_missing_project_zones,
            project_zone_email=settings.dns.project_zone_email,
            project_zone_description_template=settings.dns.project_zone_description_template,
        ),
        floating_ip_metadata_repository=OpenStackFloatingIpMetadataRepository(connection),
        planner=planner,
        dry_run=settings.controller.dry_run,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="openstack-fip-dns-reconciler",
        description="Reconcile OpenStack Neutron floating IPs into Designate DNS records.",
    )
    parser.add_argument(
        "--config",
        default=default_config_path(),
        type=str,
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one reconciliation pass and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log intended writes without applying them.",
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args(argv)


def _install_signal_handlers(worker: ReconcilerWorker) -> None:
    def _request_stop(signum: int, _frame: object) -> None:
        LOG.info("Received shutdown signal", extra={"signal": signum})
        worker.request_stop()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)


if __name__ == "__main__":
    raise SystemExit(main())
