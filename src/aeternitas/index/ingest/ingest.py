from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from aeternitas.common.hashing import sha256_file
from aeternitas.index.extractors.text_extractors import EXTRACTOR_VERSION, extract_text
from aeternitas.index.parse.receipt import parse_receipt_fields


def upsert_source(
    con: sqlite3.Connection,
    uri: str,
    source_type: str,
    scan_root: Optional[str],
    rel_path: Optional[str],
    mime: Optional[str],
) -> int:
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    cur = con.execute("SELECT id FROM source WHERE uri=?", (uri,))
    row = cur.fetchone()
    if row:
        con.execute(
            "UPDATE source SET mime=COALESCE(?, mime), scan_root=COALESCE(?, scan_root), rel_path=COALESCE(?, rel_path) WHERE id=?",
            (mime, scan_root, rel_path, row["id"]),
        )
        return int(row["id"])
    cur = con.execute(
        "INSERT INTO source(uri, source_type, scan_root, rel_path, mime, created_at) VALUES(?,?,?,?,?,?)",
        (uri, source_type, scan_root, rel_path, mime, now),
    )
    return int(cur.lastrowid)


def latest_revision(con: sqlite3.Connection, source_id: int) -> Optional[sqlite3.Row]:
    cur = con.execute(
        "SELECT id, size, mtime, sha256, status FROM revision WHERE source_id=? ORDER BY id DESC LIMIT 1",
        (source_id,),
    )
    return cur.fetchone()


def add_revision_and_doc(
    con: sqlite3.Connection,
    source_id: int,
    path: Path,
    title: str,
    text: str,
    encoding: str,
    extractor: str,
    extra_json: Dict[str, Any],
    status: str = "ok",
    error: Optional[str] = None,
    sha256: Optional[str] = None,
    st: Optional[os.stat_result] = None,
    compute_sha: bool = True,
) -> int:
    st = st or path.stat()
    observed_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sha = sha256 if not compute_sha else (sha256 or sha256_file(path))
    cur = con.execute(
        "INSERT INTO revision(source_id, observed_at, size, mtime, sha256, content_encoding, extractor, extractor_version, status, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (source_id, observed_at, st.st_size, st.st_mtime, sha, encoding, extractor, EXTRACTOR_VERSION, status, error),
    )
    rev_id = int(cur.lastrowid)
    cur2 = con.execute(
        "INSERT INTO doc(revision_id, title, text, json) VALUES (?,?,?,?)",
        (rev_id, title, text, json.dumps(extra_json, ensure_ascii=False)),
    )
    con.execute("UPDATE source SET current_revision_id=? WHERE id=?", (rev_id, source_id))
    return int(cur2.lastrowid)


def ingest_file(con: sqlite3.Connection, path: Path, scan_root: Optional[Path] = None) -> None:
    path = path.absolute()
    is_symlink = path.is_symlink()
    mime, _ = mimetypes.guess_type(str(path))
    if is_symlink:
        st = path.lstat()
        sha = None
    else:
        st = path.stat()
        sha = sha256_file(path)

    if scan_root:
        try:
            rel = str(path.relative_to(scan_root.resolve()))
        except Exception:
            rel = path.name
    else:
        rel = path.name

    uri = f"file://{rel}" if scan_root else f"file://{path}"
    source_id = upsert_source(
        con,
        uri=uri,
        source_type="file",
        scan_root=str(scan_root) if scan_root else None,
        rel_path=rel,
        mime=mime,
    )
    latest = latest_revision(con, source_id)
    if latest and latest["size"] == st.st_size and latest["mtime"] == st.st_mtime:
        if sha is not None and latest["sha256"] != sha:
            pass
        elif sha is None and latest["sha256"] is not None:
            pass
        elif latest["status"] == "ok":
            return

    if is_symlink:
        try:
            target = os.readlink(path)
        except OSError:
            target = None
        extra_json = {"mime": mime, "path": str(path), "rel_path": rel, "symlink_target": target}
        add_revision_and_doc(
            con,
            source_id,
            path,
            title=path.name,
            text="",
            encoding="utf-8",
            extractor="symlink",
            extra_json=extra_json,
            status="ok",
            sha256=None,
            st=st,
            compute_sha=False,
        )
        return

    # Extract text
    try:
        text, enc, extractor = extract_text(path)
        extra_json: Dict[str, Any] = {"mime": mime, "path": str(path), "rel_path": rel, "extractor": extractor}
        # If looks like receipt, parse fields
        if extractor in ("pdf", "ocr") or "kuitti" in path.name.lower():
            extra_json["receipt"] = parse_receipt_fields(text)
            # fallback: päivämäärä tiedostonimestä (esim. kuitti-2010-07-30-....jpg)
            if isinstance(extra_json.get("receipt"), dict) and not extra_json["receipt"].get("date"):
                m = re.search(r"(19|20)\d{2}[-_.](\d{2})[-_.](\d{2})", path.name)
                if m:
                    y = int(path.name[m.start() : m.start() + 4])
                    mo = int(m.group(2))
                    d = int(m.group(3))
                    extra_json["receipt"]["date"] = f"{y:04d}-{mo:02d}-{d:02d}"
        title = path.name
        add_revision_and_doc(
            con,
            source_id,
            path,
            title=title,
            text=text,
            encoding=enc,
            extractor=extractor,
            extra_json=extra_json,
            status="ok",
            sha256=sha,
            st=st,
        )
    except Exception as e:
        add_revision_and_doc(
            con,
            source_id,
            path,
            title=path.name,
            text="",
            encoding="utf-8",
            extractor="error",
            extra_json={"mime": mime, "path": str(path), "rel_path": rel},
            status="error",
            error=str(e),
            sha256=sha,
            st=st,
        )
