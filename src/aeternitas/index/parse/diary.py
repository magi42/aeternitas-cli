from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional

from aeternitas.common.text import normalize_ws

WEEKDAYS_FI = r"(?:ma|ti|ke|to|pe|la|su|Ma|Ti|Ke|To|Pe|La|Su)"
DATE_LINE_RE = re.compile(rf"^(?:{WEEKDAYS_FI}\s+)?(\d{{1,2}})\.(\d{{1,2}})\.(?:\s*(\d{{4}}))?\s*\.?\s*$")


def parse_diary_entries(text: str, default_year: Optional[int]) -> List[Dict[str, Any]]:
    """
    Splits diary-like text into entries by date lines.
    Returns list of {date, title, body}.
    """
    lines = text.splitlines()
    entries: List[Dict[str, Any]] = []
    cur_date: Optional[dt.date] = None
    cur_lines: List[str] = []

    def flush() -> None:
        nonlocal cur_date, cur_lines
        if cur_date is None:
            return
        body = "\n".join(cur_lines).strip()
        title = normalize_ws(body.splitlines()[0]) if body else f"Merkintä {cur_date.isoformat()}"
        entries.append({
            "date": cur_date,
            "title": title[:160],
            "body": body,
        })
        cur_lines = []

    for line in lines:
        m = DATE_LINE_RE.match(line.strip())
        if m:
            # new entry
            flush()
            d = int(m.group(1))
            mo = int(m.group(2))
            y = int(m.group(3)) if m.group(3) else default_year
            if y is None:
                # fallback: nykyvuosi
                y = dt.date.today().year
            try:
                cur_date = dt.date(y, mo, d)
            except ValueError:
                # ignore bogus
                cur_date = None
            continue
        # regular line
        if cur_date is not None:
            cur_lines.append(line)

    flush()
    return entries
