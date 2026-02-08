from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List

from aeternitas.common.text import normalize_ws


def parse_receipt_fields(text: str) -> Dict[str, Any]:
    """
    Very heuristic receipt parser for Finnish receipts.
    Extracts merchant, date, total, items.
    """
    # Normalize OCR noise a bit
    t = text.replace("\u00a0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    lines = [normalize_ws(x) for x in t.splitlines() if normalize_ws(x)]
    joined = "\n".join(lines)

    # merchant: take first line that looks like COMPANY + oy/oyj/ab, else first non-empty
    merchant = None
    for ln in lines[:10]:
        if re.search(r"\b(oyj|oy|ab|ltd|inc)\b", ln, flags=re.IGNORECASE):
            merchant = ln
            break
    if merchant is None and lines:
        merchant = lines[0]

    # date: dd.mm.yyyy
    date = None
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", joined)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            date = dt.date(y, mo, d)
        except ValueError:
            date = None

    # total: prefer "Maksettava", fallback to "Yhteensä"
    total = None
    m = re.search(r"Maksettava\s+([0-9]+[,.][0-9]{2})", joined, flags=re.IGNORECASE)
    if m:
        total = m.group(1).replace(",", ".")
    else:
        m = re.search(r"Yhteens[aä].{0,20}\s+([0-9]+[,.][0-9]{2})", joined, flags=re.IGNORECASE)
        if m:
            total = m.group(1).replace(",", ".")
        else:
            # fallback: last EUR amount
            m2 = re.findall(r"\b([0-9]+[,.][0-9]{2})\s*(?:EUR|e)\b", joined, flags=re.IGNORECASE)
            if m2:
                total = m2[-1].replace(",", ".")

    # items: look for lines with product-ish and amount
    items: List[Dict[str, Any]] = []
    for ln in lines:
        # skip obvious totals
        if re.search(r"\b(maksettava|yhteens|alennus|veroton|vero|alv)\b", ln, flags=re.IGNORECASE):
            continue
        m = re.search(r"^([A-ZÅÄÖ0-9][A-ZÅÄÖ0-9 \-\/]{2,})\s+([0-9]+[,.][0-9]{2})\b", ln)
        if m:
            name = normalize_ws(m.group(1))
            price = m.group(2).replace(",", ".")
            # avoid addresses/phones
            if re.search(r"\b(TURKU|HELSINKI|puh|www)\b", name, flags=re.IGNORECASE):
                continue
            items.append({"name": name[:120], "price": price})

    return {
        "merchant": merchant,
        "date": date.isoformat() if date else None,
        "total": total,
        "items": items[:30],
        "raw_lines": lines[:200],
    }
