from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple


def guess_encoding(data: bytes) -> str:
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def safe_read_text(path: Path) -> Tuple[str, str]:
    data = path.read_bytes()
    enc = guess_encoding(data)
    text = data.decode(enc, errors="replace")
    return text, enc


def normalize_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()


def infer_year_from_path(path: Path) -> Optional[int]:
    m = re.search(r"(19|20)\d{2}", path.name)
    return int(m.group(0)) if m else None
