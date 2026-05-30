from typing import Protocol

from openstack_fip_dns_reconciler.domain.models.dns_record import GeneratedDnsRecord


class DnsRecordRepository(Protocol):
    def list_managed_records(self) -> list[GeneratedDnsRecord]:
        """Return Designate records owned by this controller."""

    def create_record(self, record: GeneratedDnsRecord) -> None:
        """Create a DNS recordset."""

    def update_record(self, record: GeneratedDnsRecord) -> None:
        """Update a DNS recordset."""

    def delete_record(self, record: GeneratedDnsRecord) -> None:
        """Delete a DNS recordset."""
