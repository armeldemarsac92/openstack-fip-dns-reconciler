from pathlib import Path

import pytest

from openstack_fip_dns_reconciler.config.loader import load_settings


def test_load_settings_normalizes_base_domain(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
dns:
  base_domain: FIP.INTERNAL.EXAMPLE
""",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.dns.base_domain == "fip.internal.example."


def test_dns_all_projects_defaults_to_false(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
dns:
  base_domain: fip.internal.example.
""",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.dns.all_projects is False


def test_project_zone_creation_requires_email(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
dns:
  base_domain: fip.internal.example.
  zone_strategy: per_project_zone
  create_missing_project_zones: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="project_zone_email is required"):
        load_settings(config_file)


def test_project_zone_creation_requires_per_project_strategy(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
dns:
  base_domain: fip.internal.example.
  zone_strategy: single_zone
  create_missing_project_zones: true
  project_zone_email: hostmaster@fip.internal.example
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="zone_strategy must be per_project_zone"):
        load_settings(config_file)
