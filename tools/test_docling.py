#!/usr/bin/env python3
"""Smoke test for Docling document extraction."""
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.knowledge.docling_processor import extract_document


def main():
    # Find a test file
    repo_root = Path(__file__).parent.parent
    candidates = list(repo_root.glob("*.md"))[:1] + list(repo_root.glob("**/*.pdf"))[:1]

    if not candidates:
        print("No .md or .pdf files found to test")
        sys.exit(1)

    test_file = candidates[0]
    print(f"Testing extraction on: {test_file}")

    result = extract_document(test_file)

    if result is None:
        print("Extraction returned None (docling may not be installed)")
        sys.exit(1)

    print(f"Extracted text (first 200 chars):\n{result['text'][:200]}")
    print(f"Tables found: {len(result.get('tables', []))}")
    print("SUCCESS")
    sys.exit(0)


if __name__ == "__main__":
    main()
