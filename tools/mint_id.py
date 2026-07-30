#!/usr/bin/env python3
"""
MSN-0147: CLI wrapper — python3 tools/mint_id.py <PREFIX>

Delegates to id_registry.next_id() so Python is the single counter writer.
Called by lcars-portal/src/lib/id-registry.ts via child_process.execFile.

Usage:
    python3 tools/mint_id.py MSN       → USS-TJR-MSN-0148
    python3 tools/mint_id.py BREQ      → BREQ-0018
    python3 tools/mint_id.py DEC       → DEC-0032
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import id_registry

prefix = sys.argv[1].upper() if len(sys.argv) > 1 else "MSN"
print(id_registry.next_id(prefix))
