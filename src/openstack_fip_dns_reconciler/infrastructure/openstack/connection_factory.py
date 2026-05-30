from typing import Any

from openstack_fip_dns_reconciler.config.settings import OpenStackSettings
from openstack_fip_dns_reconciler.infrastructure.exceptions import InfrastructureError


class OpenStackConnectionFactory:
    def __init__(self, settings: OpenStackSettings) -> None:
        self._settings = settings

    def create(self) -> Any:
        try:
            import openstack
        except ImportError as exc:
            raise InfrastructureError("openstacksdk is not installed") from exc

        try:
            if self._settings.cloud:
                return openstack.connect(cloud=self._settings.cloud)
            return openstack.connect()
        except Exception as exc:
            raise InfrastructureError("Unable to create OpenStack SDK connection") from exc
