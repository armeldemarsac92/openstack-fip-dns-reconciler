import shlex

from openstack_fip_dns_reconciler.domain.models.record_ownership import RecordOwnership


class OwnershipParser:
    def __init__(self, managed_by: str) -> None:
        self._managed_by = managed_by

    def serialize(self, ownership: RecordOwnership) -> str:
        return ownership.to_txt_value()

    def parse(self, txt_value: str) -> RecordOwnership | None:
        cleaned = txt_value.strip().strip('"')
        if not cleaned:
            return None
        fields: dict[str, str] = {}
        try:
            tokens = shlex.split(cleaned)
        except ValueError:
            return None
        for token in tokens:
            key, separator, value = token.partition("=")
            if not separator:
                continue
            fields[key] = value

        if fields.get("managed-by") != self._managed_by:
            return None
        fip_id = fields.get("fip_id")
        project_id = fields.get("project_id")
        if not fip_id or not project_id:
            return None
        return RecordOwnership(managed_by=self._managed_by, fip_id=fip_id, project_id=project_id)
