"""Config loading for the Secure File Transfer to VM agent (USS-TJR-MSN-0205B)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Reuse the Mac Collector Agent's (MSN-0205A) glob-based ignore matcher for
# the transfer-time exclude blocklist rather than duplicating it — the two
# missions are pipeline stages of the same MSN-0205 effort.
_MAC_COLLECTOR_DIR = Path(__file__).resolve().parent.parent / "mac-collector"
if str(_MAC_COLLECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_MAC_COLLECTOR_DIR))

from ignore_rules import IgnoreMatcher  # noqa: E402


@dataclass
class RemoteConfig:
    host: str
    port: int
    user: str
    ssh_key: str
    base_path: str
    strict_host_key_checking: str = "accept-new"
    connect_timeout: int = 10


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 5.0


@dataclass
class Config:
    remote: RemoteConfig
    retry: RetryConfig
    exclude_patterns: list
    db_path: Path
    log_dir: Path
    rsync_extra_args: list = field(default_factory=list)
    config_path: Path = None

    def build_exclude_matcher(self) -> IgnoreMatcher:
        # Size/hidden-file filtering already happened upstream in the
        # collector; the transfer-time matcher only applies exclude_patterns.
        # IgnoreMatcher casts max_file_size_mb * 1024 * 1024 to int, so a
        # true float("inf") overflows — use a very large finite bound
        # (100 TB) instead of disabling the size check entirely.
        return IgnoreMatcher(
            patterns=self.exclude_patterns,
            max_file_size_mb=100_000_000,
            ignore_hidden=False,
        )


def _resolve(base_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def load_config(path: str) -> Config:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Copy config.example.yaml to config.yaml and edit remote connection details."
        )

    with config_path.open("r") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = config_path.parent

    remote_raw = raw.get("remote", {})
    for required in ("host", "user", "base_path"):
        if not remote_raw.get(required):
            raise ValueError(f"config.yaml: remote.{required} is required")
    remote = RemoteConfig(
        host=remote_raw["host"],
        port=int(remote_raw.get("port", 22)),
        user=remote_raw["user"],
        ssh_key=remote_raw.get("ssh_key", ""),
        base_path=remote_raw["base_path"].rstrip("/"),
        strict_host_key_checking=remote_raw.get("strict_host_key_checking", "accept-new"),
        connect_timeout=int(remote_raw.get("connect_timeout", 10)),
    )

    retry_raw = raw.get("retry", {})
    retry = RetryConfig(
        max_attempts=int(retry_raw.get("max_attempts", 3)),
        backoff_seconds=float(retry_raw.get("backoff_seconds", 5)),
    )

    db_raw = raw.get("database", {}).get("path", "./transfer.db")
    log_raw = raw.get("logs", {}).get("dir", "./logs")

    return Config(
        remote=remote,
        retry=retry,
        exclude_patterns=list(raw.get("exclude_patterns", [])),
        db_path=_resolve(base_dir, db_raw),
        log_dir=_resolve(base_dir, log_raw),
        rsync_extra_args=list(raw.get("rsync", {}).get("extra_args", [])),
        config_path=config_path,
    )
