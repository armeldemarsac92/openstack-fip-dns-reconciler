from dataclasses import dataclass
from enum import StrEnum

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel, DnsZoneName


class ZoneStrategy(StrEnum):
    SINGLE_ZONE = "single_zone"
    PER_PROJECT_ZONE = "per_project_zone"


@dataclass(frozen=True, slots=True)
class FqdnBuildResult:
    fqdn: str
    zone_name: DnsZoneName


class FqdnBuilder:
    def __init__(
        self,
        base_domain: str,
        zone_strategy: ZoneStrategy = ZoneStrategy.SINGLE_ZONE,
        template: str = "{random_label}.{project_id_label}.{base_domain}",
    ) -> None:
        self._base_domain = DnsZoneName(base_domain)
        self._zone_strategy = zone_strategy
        self._template = template

    def build(self, random_label: str, project_id_label: str) -> FqdnBuildResult:
        random_dns_label = DnsLabel(random_label)
        project_dns_label = DnsLabel(project_id_label)
        zone_name = self._zone_name(project_dns_label)
        fqdn = self._template.format(
            random_label=random_dns_label.value,
            project_id_label=project_dns_label.value,
            base_domain=self._base_domain.value,
        )
        fqdn = fqdn.strip().lower()
        if not fqdn.endswith("."):
            fqdn = f"{fqdn}."
        DnsZoneName(fqdn)
        return FqdnBuildResult(fqdn=fqdn, zone_name=zone_name)

    def _zone_name(self, project_id_label: DnsLabel) -> DnsZoneName:
        if self._zone_strategy == ZoneStrategy.PER_PROJECT_ZONE:
            return DnsZoneName(f"{project_id_label.value}.{self._base_domain.value}")
        return self._base_domain
