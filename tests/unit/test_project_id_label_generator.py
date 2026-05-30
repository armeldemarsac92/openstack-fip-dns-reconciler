import pytest

from openstack_fip_dns_reconciler.domain.exceptions import DomainError
from openstack_fip_dns_reconciler.domain.services.project_id_label_generator import (
    ProjectIdLabelCollisionError,
    ProjectIdLabelGenerator,
    ProjectIdLabelMode,
    sanitize_project_id,
)


def test_sanitize_project_id_replaces_unsafe_characters() -> None:
    assert sanitize_project_id(" Tenant_ID--With Spaces ") == "tenant-id-with-spaces"


def test_project_id_full_mode_preserves_safe_project_id() -> None:
    generator = ProjectIdLabelGenerator(ProjectIdLabelMode.FULL)

    label = generator.generate("8AB1C22F4D6E4F19A21C4D8F23BB912A")

    assert label.value == "8ab1c22f4d6e4f19a21c4d8f23bb912a"


def test_project_id_short_mode_uses_prefix() -> None:
    generator = ProjectIdLabelGenerator(ProjectIdLabelMode.SHORT, short_length=8)

    label = generator.generate("8ab1c22f4d6e4f19a21c4d8f23bb912a")

    assert label.value == "8ab1c22f"


def test_project_id_short_mode_detects_collisions() -> None:
    generator = ProjectIdLabelGenerator(ProjectIdLabelMode.SHORT, short_length=4)

    with pytest.raises(ProjectIdLabelCollisionError):
        generator.assert_no_collisions(["abcd-tenant-one", "abcd-tenant-two"])


def test_empty_sanitized_project_id_is_rejected() -> None:
    with pytest.raises(DomainError):
        sanitize_project_id("___")
