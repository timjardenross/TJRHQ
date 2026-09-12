from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yml"


def load_config(path: str | Path = _DEFAULT_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
