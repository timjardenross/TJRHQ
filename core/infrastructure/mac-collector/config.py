"""Config loading for the Mac File Collector Agent (USS-TJR-MSN-0205A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Source:
    name: str
    path: Path
    enabled: bool = True


@dataclass
class IgnoreConfig:
    patterns: list = field(default_factory=list)
    max_file_size_mb: float = 500.0
    ignore_hidden: bool = True
    # MSN-0206J-3: cloud-only placeholders (OneDrive Files On-Demand, iCloud
    # Drive) are excluded by default — see cloud_detection.py. Setting this
    # True is a deliberate operator override to hash/track them anyway; doing
    # so will likely trigger an OS-level download of the placeholder's real
    # content the moment it's hashed.
    include_cloud_only: bool = False


@dataclass
class Config:
    sources: list
    ignore: IgnoreConfig
    db_path: Path
    manifest_dir: Path
    config_path: Path


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
            f"Copy config.example.yaml to config.yaml and edit source paths."
        )

    with config_path.open("r") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = config_path.parent

    sources = [
        Source(
            name=s["name"],
            path=Path(s["path"]).expanduser(),
            enabled=s.get("enabled", True),
        )
        for s in raw.get("sources", [])
    ]

    ignore_raw = raw.get("ignore", {})
    ignore = IgnoreConfig(
        patterns=list(ignore_raw.get("patterns", [])),
        max_file_size_mb=float(ignore_raw.get("max_file_size_mb", 500)),
        ignore_hidden=bool(ignore_raw.get("ignore_hidden", True)),
        include_cloud_only=bool(ignore_raw.get("include_cloud_only", False)),
    )

    db_raw = raw.get("database", {}).get("path", "./collector.db")
    manifest_raw = raw.get("manifest", {}).get("output_dir", "./manifests")

    return Config(
        sources=sources,
        ignore=ignore,
        db_path=_resolve(base_dir, db_raw),
        manifest_dir=_resolve(base_dir, manifest_raw),
        config_path=config_path,
    )
