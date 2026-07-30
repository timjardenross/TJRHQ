"""CSV/XLSX extraction via pandas + openpyxl (USS-TJR-MSN-0205C).

Renders each sheet as CSV text (bounded to MAX_ROWS_PREVIEW rows so a huge
spreadsheet doesn't blow up chunking/embedding cost) for downstream
chunking, classification, and summarisation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ExtractionResult, ExtractionError

MAX_ROWS_PREVIEW = 500


def extract(path) -> ExtractionResult:
    path = Path(path)
    ext = path.suffix.lower()
    try:
        if ext == ".csv":
            sheets = {"Sheet1": pd.read_csv(path)}
        else:
            sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except Exception as exc:
        raise ExtractionError(f"failed to read tabular file: {exc}") from exc

    parts = []
    total_rows = 0
    truncated = False
    for name, df in sheets.items():
        total_rows += len(df)
        if len(df) > MAX_ROWS_PREVIEW:
            truncated = True
        preview = df.head(MAX_ROWS_PREVIEW)
        parts.append(f"## {name} ({len(df)} rows x {len(df.columns)} cols)\n{preview.to_csv(index=False)}")

    text = "\n\n".join(parts)
    return ExtractionResult(
        text=text.strip(), needs_ocr=False, page_count=len(sheets),
        metadata={"sheet_count": len(sheets), "total_rows": total_rows, "truncated": truncated},
    )
