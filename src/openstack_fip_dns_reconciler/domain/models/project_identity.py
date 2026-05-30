from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    id: str
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Project id must not be empty")
