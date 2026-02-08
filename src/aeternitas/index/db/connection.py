from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import SCHEMA_SQL


def db_connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA_SQL)
    # Backfill columns if DB already existed without them
    cur = con.cursor()
    try:
        cur.execute("ALTER TABLE source ADD COLUMN current_revision_id INTEGER;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE revision ADD COLUMN extractor_version TEXT;")
    except sqlite3.OperationalError:
        pass
    # Populate current_revision_id for existing sources if missing
    cur.execute(
        """
        UPDATE source
        SET current_revision_id = (
            SELECT r.id FROM revision r
            WHERE r.source_id = source.id
            ORDER BY r.id DESC
            LIMIT 1
        )
        WHERE current_revision_id IS NULL
    """
    )
    con.commit()
    return con
