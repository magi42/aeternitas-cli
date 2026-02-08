from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aeternitas.common.text import infer_year_from_path, normalize_ws
from aeternitas.common.timeutil import iso_date
from aeternitas.index.parse.diary import parse_diary_entries


def rebuild_timeline(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM timeline")
    # Create timeline items for each doc (current revisions only)
    cur = con.execute(
        """
        SELECT d.id AS doc_id, d.title, d.text, d.json
        FROM doc d
        JOIN revision r ON r.id = d.revision_id
        JOIN source s ON s.current_revision_id = r.id
        WHERE r.status = 'ok'
    """
    )
    for row in cur.fetchall():
        doc_id = int(row["doc_id"])
        title = row["title"] or ""
        text = row["text"] or ""
        meta = json.loads(row["json"] or "{}")

        # Receipts
        receipt = meta.get("receipt") if isinstance(meta, dict) else None
        if isinstance(receipt, dict) and receipt.get("date"):
            d = receipt["date"]
            snippet = f"{receipt.get('merchant','')} total {receipt.get('total','')}"
            con.execute(
                "INSERT INTO timeline(doc_id, date, kind, title, snippet, json) VALUES(?,?,?,?,?,?)",
                (doc_id, d, "receipt", title, snippet[:300], json.dumps(receipt, ensure_ascii=False)),
            )
            continue

        # Diary-like split
        default_year = infer_year_from_path(Path(title))
        entries = parse_diary_entries(text, default_year)
        for ent in entries[:2000]:
            d = iso_date(ent["date"])
            snip = normalize_ws(ent["body"][:300])
            con.execute(
                "INSERT INTO timeline(doc_id, date, kind, title, snippet, json) VALUES(?,?,?,?,?,?)",
                (doc_id, d, "diary_entry", ent["title"], snip, json.dumps({}, ensure_ascii=False)),
            )
