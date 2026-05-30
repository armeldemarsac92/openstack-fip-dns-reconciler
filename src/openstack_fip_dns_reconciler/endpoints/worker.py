import logging
import threading

from openstack_fip_dns_reconciler.application.services.reconciliation_service import (
    FloatingIpDnsReconciliationService,
)

LOG = logging.getLogger(__name__)


class ReconcilerWorker:
    def __init__(
        self,
        service: FloatingIpDnsReconciliationService,
        poll_interval_seconds: int,
    ) -> None:
        self._service = service
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_requested = threading.Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def run_forever(self) -> None:
        LOG.info(
            "Starting reconciliation worker",
            extra={"poll_interval_seconds": self._poll_interval_seconds},
        )
        while not self._stop_requested.is_set():
            try:
                self._service.reconcile_once()
            except Exception:
                LOG.exception("Reconciliation pass failed")
            self._stop_requested.wait(self._poll_interval_seconds)
        LOG.info("Stopped reconciliation worker")
