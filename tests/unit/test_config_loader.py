from pathlib import Path

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
