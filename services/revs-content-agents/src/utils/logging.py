import json
import logging
import sys
from pathlib import Path

from src.utils.config import load_config

_configured = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure() -> None:
    config = load_config().get("logging", {})
    level = getattr(logging, str(config.get("level", "INFO")).upper(), logging.INFO)
    formatter = (
        _JsonFormatter() if config.get("format") == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root = logging.getLogger("revs")
    root.setLevel(level)
    root.propagate = False

    if config.get("console", True):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    log_file = config.get("file")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        _configure()
        _configured = True
    return logging.getLogger(f"revs.{name}")
