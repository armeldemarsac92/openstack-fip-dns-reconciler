from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ZoneStrategy(StrEnum):
    SINGLE_ZONE = "single_zone"
    PER_PROJECT_ZONE = "per_project_zone"


class ProjectIdLabelMode(StrEnum):
    FULL = "full"
    SHORT = "short"


class LabelEncoding(StrEnum):
    BASE32 = "base32"


class OpenStackSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloud: str | None = None


class ControllerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_seconds: int = Field(default=15, ge=1)
    dry_run: bool = False


class DnsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_domain: str
    zone_strategy: ZoneStrategy = ZoneStrategy.SINGLE_ZONE
    ttl: int = Field(default=60, ge=1)
    label_length: int = Field(default=13, ge=1, le=63)
    label_encoding: LabelEncoding = LabelEncoding.BASE32
    project_id_label_mode: ProjectIdLabelMode = ProjectIdLabelMode.SHORT
    project_id_short_length: int = Field(default=8, ge=1, le=63)

    @field_validator("base_domain")
    @classmethod
    def normalize_base_domain(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("base_domain must not be empty")
        return normalized if normalized.endswith(".") else f"{normalized}."


class RecordsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_txt_metadata: bool = True
    managed_by: str = "openstack-fip-dns-reconciler"
    fqdn_template: str = "{random_label}.{project_id_label}.{base_domain}"


class NeutronMetadataSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    update_description: bool = True
    description_template: str = "Auto DNS: {fqdn}"
    update_tags: bool = True
    tags: list[str] = Field(
        default_factory=lambda: [
            "auto-dns",
            "dns-label:{random_label}",
            "dns-project:{project_id_label}",
        ]
    )


class CleanupSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delete_stale_records: bool = True


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openstack: OpenStackSettings = Field(default_factory=OpenStackSettings)
    controller: ControllerSettings = Field(default_factory=ControllerSettings)
    dns: DnsSettings
    records: RecordsSettings = Field(default_factory=RecordsSettings)
    neutron_metadata: NeutronMetadataSettings = Field(default_factory=NeutronMetadataSettings)
    cleanup: CleanupSettings = Field(default_factory=CleanupSettings)


def default_config_path() -> Path:
    return Path("/etc/openstack-fip-dns-reconciler/config.yaml")
