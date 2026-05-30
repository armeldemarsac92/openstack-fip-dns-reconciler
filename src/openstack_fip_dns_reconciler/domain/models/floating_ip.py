from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FloatingIp:
    id: str
    project_id: str
    address: str
    description: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Floating IP id must not be empty")
        if not self.project_id:
            raise ValueError("Floating IP project_id must not be empty")
        if not self.address:
            raise ValueError("Floating IP address must not be empty")
