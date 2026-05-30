from pathlib import Path
from typing import Any

import yaml

from openstack_fip_dns_reconciler.config.settings import AppSettings


class ConfigurationError(RuntimeError):
    """Raised when configuration cannot be loaded."""


def load_settings(path: str | Path) -> AppSettings:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"Unable to read configuration file: {config_path}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be a YAML mapping")
    return AppSettings.model_validate(raw)


def load_settings_from_mapping(raw: dict[str, Any]) -> AppSettings:
    return AppSettings.model_validate(raw)
