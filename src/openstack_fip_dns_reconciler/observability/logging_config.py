import logging
from collections.abc import Mapping
from typing import Any

_STANDARD_LOG_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__)


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith("_")
        }
        if not extras:
            return message
        return f"{message} {_format_extras(extras)}"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        KeyValueFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def _format_extras(extras: Mapping[str, Any]) -> str:
    return " ".join(f"{key}={value!r}" for key, value in sorted(extras.items()))
