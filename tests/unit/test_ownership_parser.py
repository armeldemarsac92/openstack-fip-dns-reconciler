from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership
from openstack_fip_dns_reconciler.domain.services.ownership_parser import OwnershipParser


def test_ownership_parser_round_trips_metadata() -> None:
    parser = OwnershipParser("openstack-fip-dns-reconciler")
    ownership = RecordOwnership(
        managed_by="openstack-fip-dns-reconciler",
        fip_id="2c4f",
        project_id="8ab1c22f4d6e4f19a21c4d8f23bb912a",
    )

    parsed = parser.parse(parser.serialize(ownership))

    assert parsed == ownership


def test_ownership_parser_ignores_other_managers() -> None:
    parser = OwnershipParser("openstack-fip-dns-reconciler")

    parsed = parser.parse("managed-by=someone-else fip_id=2c4f project_id=project")

    assert parsed is None


def test_ownership_parser_accepts_quoted_txt_values() -> None:
    parser = OwnershipParser("openstack-fip-dns-reconciler")

    parsed = parser.parse(
        '"managed-by=openstack-fip-dns-reconciler fip_id=2c4f project_id=project"'
    )

    assert parsed is not None
    assert parsed.fip_id == "2c4f"
