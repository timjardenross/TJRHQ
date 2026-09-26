#!/usr/bin/env python3
"""Generate docs/LIVE-WORKBENCHES.md from the TypeScript registry."""
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = (root / 'lcars-portal/src/lib/workbenches.ts').read_text().split('export const LIVE_WORKBENCHES', 1)[1].split('\n];', 1)[0]
rows = re.findall(r"href: '([^']+)',\s+title: '([^']+)'(?:,|\n).*?description: '([^']*)'", source, re.DOTALL)
rows = [(href, title, desc.replace("\\'", "'")) for href, title, desc in rows]
out = [
    '# Live Workbenches — Master List', '',
    '> Generated from `lcars-portal/src/lib/workbenches.ts` by `tools/generate_workbench_doc.py`. Do not hand-edit.', '',
    f'## The {len(rows)} live workbenches', '',
    '| Route | Title | Description |', '|---|---|---|',
]
out += [f'| `{href}` | {title} | {desc} |' for href, title, desc in rows]
out += ['', 'Regenerate after changing `LIVE_WORKBENCHES`: `python3 tools/generate_workbench_doc.py`.', '']
(root / 'docs/LIVE-WORKBENCHES.md').write_text('\n'.join(out))
