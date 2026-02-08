from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional

from aeternitas.common.text import normalize_ws

WEEKDAYS_FI = r"(?:ma|ti|ke|to|pe|la|su|Ma|Ti|Ke|To|Pe|La|Su)"
# Date token used for robust scanning within text, not just line-starts.
DATE_TOKEN_RE = re.compile(
    rf"(?:{WEEKDAYS_FI}\s+)?(\d{{1,2}})\.(\d{{1,2}})\.(?:\s*(\d{{4}}))?\s*\.?",
    flags=re.UNICODE,
)


def parse_diary_entries(text: str, default_year: Optional[int]) -> List[Dict[str, Any]]:
    """
    Splits diary-like text into entries by date lines.
    Returns list of {date, title, body}.
    """
    entries: List[Dict[str, Any]] = []
    matches = list(DATE_TOKEN_RE.finditer(text))
    if not matches:
        return entries

    for i, m in enumerate(matches):
        d = int(m.group(1))
        mo = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else default_year
        if y is None:
            y = dt.date.today().year
        try:
            cur_date = dt.date(y, mo, d)
        except ValueError:
            continue

        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        title = normalize_ws(body.splitlines()[0]) if body else f"Merkintä {cur_date.isoformat()}"
        entries.append({
            "date": cur_date,
            "title": title[:160],
            "body": body,
        })

    return entries
