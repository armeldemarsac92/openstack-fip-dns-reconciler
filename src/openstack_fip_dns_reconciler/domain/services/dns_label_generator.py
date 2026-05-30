import base64
import math
import secrets
from typing import Protocol

from openstack_fip_dns_reconciler.domain.models.dns_name import DnsLabel


class DnsLabelGenerator(Protocol):
    def generate(self) -> DnsLabel:
        """Generate a DNS-safe label."""


class Base32DnsLabelGenerator:
    def __init__(self, length: int = 13) -> None:
        if not 1 <= length <= 63:
            raise ValueError("length must be between 1 and 63")
        self._length = length

    def generate(self) -> DnsLabel:
        byte_count = math.ceil(self._length * 5 / 8) + 1
        encoded = base64.b32encode(secrets.token_bytes(byte_count)).decode("ascii").lower()
        return DnsLabel(encoded.rstrip("=")[: self._length])
