from openstack_fip_dns_reconciler.domain.services.fqdn_builder import FqdnBuilder, ZoneStrategy


def test_fqdn_builder_uses_single_zone_by_default() -> None:
    result = FqdnBuilder("fip.internal.mycloud.net.").build("x7k9m2q4pa", "8ab1c22f")

    assert result.fqdn == "x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net."
    assert result.zone_name.value == "fip.internal.mycloud.net."


def test_fqdn_builder_supports_per_project_zones() -> None:
    result = FqdnBuilder(
        "fip.internal.mycloud.net.",
        zone_strategy=ZoneStrategy.PER_PROJECT_ZONE,
    ).build("x7k9m2q4pa", "8ab1c22f")

    assert result.fqdn == "x7k9m2q4pa.8ab1c22f.fip.internal.mycloud.net."
    assert result.zone_name.value == "8ab1c22f.fip.internal.mycloud.net."
