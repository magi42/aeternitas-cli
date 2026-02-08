#!/usr/bin/env python3
"""
aet.py — CLI entry point for the indexing tool.

Implementation lives under src/aeternitas/index.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aeternitas.index.cli import main


if __name__ == "__main__":
    main()
