"""Config loading for the VM Knowledge Processing Engine (USS-TJR-MSN-0205C).

Operational tuning (inbox path, chunk sizes, model router URL) comes from
config.yaml, matching the MSN-0205A/B config style. Secrets (Supabase URL +
service role key) come from the repo-root .env, matching every other
worker in this repo (e.g. core/capture/enrichment_worker.py) — they are
never written to a YAML file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_dotenv(repo_root: Path) -> None:
    """This worker only needs SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY, which
    live in the repo-root .env — platform-runtime/.env is a different
    service's secrets file and intentionally not readable by this worker's
    runtime user, hence the fallback path list. 2026-08-29: migrated onto
    core/platform/configuration_service.py's load_dotenv_files() — this
    file's own PermissionError-skip behavior is literally what that
    module's docstring says it was modeled on (see tools/check_config_loaders.py)."""
    from core.platform.configuration_service import load_dotenv_files

    load_dotenv_files([repo_root / ".env", repo_root / "platform-runtime" / ".env"])


@dataclass
class SupabaseConfig:
    url: str
    service_role_key: str


@dataclass
class ModelRouterConfig:
    url: str
    timeout_seconds: int = 300


@dataclass
class ProcessingConfig:
    batch_limit: int = 20
    chunk_chars: int = 1200
    chunk_overlap_chars: int = 150
    low_text_chars_per_page: int = 50
    # USS-TJR-MSN-0206J-4: cap on `worker.py retry` calls per document
    # before it moves from `failed` to the `permanently_failed` terminal
    # state instead of `retry_pending`. Enforced at the moment a retry is
    # requested, not silently during processing — see worker.py's retry().
    max_retries: int = 3


@dataclass
class Config:
    inbox_base_path: Path
    supabase: SupabaseConfig
    model_router: ModelRouterConfig
    processing: ProcessingConfig
    ocr_workdir: Path
    ocr_language: str
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
            f"Copy config.example.yaml to config.yaml and edit inbox.base_path."
        )

    _load_dotenv(_REPO_ROOT)

    with config_path.open("r") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = config_path.parent

    inbox_raw = raw.get("inbox", {})
    if not inbox_raw.get("base_path"):
        raise ValueError("config.yaml: inbox.base_path is required")

    router_raw = raw.get("model_router", {})
    proc_raw = raw.get("processing", {})
    ocr_raw = raw.get("ocr", {})

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    return Config(
        inbox_base_path=Path(inbox_raw["base_path"]).expanduser(),
        supabase=SupabaseConfig(url=supabase_url, service_role_key=supabase_key),
        model_router=ModelRouterConfig(
            url=router_raw.get("url", "http://127.0.0.1:8891").rstrip("/"),
            timeout_seconds=int(router_raw.get("timeout_seconds", 300)),
        ),
        processing=ProcessingConfig(
            batch_limit=int(proc_raw.get("batch_limit", 20)),
            chunk_chars=int(proc_raw.get("chunk_chars", 1200)),
            chunk_overlap_chars=int(proc_raw.get("chunk_overlap_chars", 150)),
            low_text_chars_per_page=int(proc_raw.get("low_text_chars_per_page", 50)),
            max_retries=int(proc_raw.get("max_retries", 3)),
        ),
        ocr_workdir=_resolve(base_dir, ocr_raw.get("workdir", "./ocr-work")),
        ocr_language=str(ocr_raw.get("language", "eng")),
        config_path=config_path,
    )
