import re

import pytest

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel
from openstack_fip_dns_reconciler.domain.services.dns_label_generator import Base32DnsLabelGenerator


def test_base32_random_label_is_dns_safe_lowercase() -> None:
    label = Base32DnsLabelGenerator(length=13).generate()

    assert len(label.value) == 13
    assert re.fullmatch(r"[a-z2-7]+", label.value)


def test_dns_label_rejects_invalid_characters() -> None:
    with pytest.raises(ValueError):
        DnsLabel("bad_label")
