"""Local stubs matching the Batch 1 section-2 interfaces (WP2 production status, WP3 claim gate, WP5 PIR tagging).
Used until those work packages are integrated; the renderer reads them only through duck-typing (dict / attributes)."""
from dataclasses import dataclass, field


@dataclass
class ClaimGateResult:           # WP3 shape (subset)
    passed: bool
    mode: str = "shadow"
    failures: list = field(default_factory=list)


@dataclass
class PirMatch:                  # WP5 shape
    pir_id: str
    priority: str
    basis: str = ""


@dataclass
class PirTagResult:              # WP5 shape
    matches: list = field(default_factory=list)
    unmatched_high_severity: bool = False
    emerging: bool = False


def pir_dict(res: PirTagResult) -> dict:
    return {"matches": [vars(m) for m in res.matches], "unmatched_high_severity": res.unmatched_high_severity, "emerging": res.emerging}


def status_dict(status: str, reasons=()):   # WP2 StatusResult -> dict the renderer accepts
    return {"status": status, "reasons": list(reasons)}
