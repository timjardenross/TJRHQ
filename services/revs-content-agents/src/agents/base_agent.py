from pathlib import Path
from typing import Protocol

from src.parsing.schemas import DesignBrief


class BaseAgent(Protocol):
    """Contract shared by every format agent (article, poster, worksheet, ...)."""

    format_name: str

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        """Render `brief` into this agent's format under output_dir/<format_name>/.

        Returns a manifest fragment: {"format": format_name, "files": [str, ...]}.
        """
        ...
