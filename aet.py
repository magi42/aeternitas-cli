#!/usr/bin/env python3
"""
arkistointi_mvp.py — minimalistinen proto paikalliseen, päivitettävään arkistointiin.

Ominaisuudet (MVP):
- Ingestoi tiedostoja SQLiteen (lähde + revisio + purettu teksti).
- Tukee .txt, .odt, .pdf sekä kuittikuvat (.jpg/.png) OCR:llä (tesseract).
- Luo aikajanan (päiväkirjamerkinnät ja kuitit) + FTS5-haku.

Riippuvuudet:
  pip install pypdf odfpy pillow pytesseract
  (sekä tesseract + fin-kielipaketti järjestelmään)

Käyttö:
  python arkistointi_mvp.py ingest arkisto.db /polku/tiedostoihin...
  python arkistointi_mvp.py timeline arkisto.db --limit 50
  python arkistointi_mvp.py search arkisto.db "Kati"
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Optional imports (only used when needed)
try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    PdfReader = None

try:
    from odf.opendocument import load as odf_load  # type: ignore
    from odf import teletype  # type: ignore
except Exception:
    odf_load = None
    teletype = None

try:
    from PIL import Image, ImageOps, ImageEnhance  # type: ignore
except Exception:
    Image = None

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None


# -------------------------
# DB
# -------------------------

SCHEMA_SQL = r"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS source (
  id INTEGER PRIMARY KEY,
  uri TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,     -- file, gmail, etc (MVP: file)
  scan_root TEXT,                -- esim. /home/user/data (MVP: vapaa)
  rel_path TEXT,                 -- suhteellinen polku (suositus)
  mime TEXT,
  current_revision_id INTEGER,   -- latest revision for "current view"
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revision (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL,
  observed_at TEXT NOT NULL,
  size INTEGER,
  mtime REAL,
  sha256 TEXT,
  content_encoding TEXT,
  extractor TEXT,                -- txt/pdf/odt/ocr
  extractor_version TEXT,        -- tool/extractor version
  status TEXT NOT NULL,          -- ok/error
  error TEXT,
  FOREIGN KEY(source_id) REFERENCES source(id)
);

CREATE TABLE IF NOT EXISTS doc (
  id INTEGER PRIMARY KEY,
  revision_id INTEGER NOT NULL UNIQUE,
  title TEXT,
  text TEXT,
  json TEXT,                      -- lisämetat (esim. kuitin kentät)
  FOREIGN KEY(revision_id) REFERENCES revision(id)
);

-- Full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
  title, text,
  content='doc', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS doc_ai AFTER INSERT ON doc BEGIN
  INSERT INTO doc_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS doc_au AFTER UPDATE ON doc BEGIN
  INSERT INTO doc_fts(doc_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
  INSERT INTO doc_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS doc_ad AFTER DELETE ON doc BEGIN
  INSERT INTO doc_fts(doc_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
END;

CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL,
  date TEXT NOT NULL,            -- ISO yyyy-mm-dd
  kind TEXT NOT NULL,            -- diary_entry | receipt | other
  title TEXT,
  snippet TEXT,
  json TEXT,
  FOREIGN KEY(doc_id) REFERENCES doc(id)
);

CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date);
"""

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
    cur.execute("""
        UPDATE source
        SET current_revision_id = (
            SELECT r.id FROM revision r
            WHERE r.source_id = source.id
            ORDER BY r.id DESC
            LIMIT 1
        )
        WHERE current_revision_id IS NULL
    """)
    con.commit()
    return con


# -------------------------
# Utilities
# -------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def guess_encoding(data: bytes) -> str:
    """
    MVP: yritä utf-8, muuten latin-1.
    (Tämä estää 'surrogates not allowed' -tyyppiset ongelmat JSON:issa.)
    """
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

def iso_date(d: dt.date) -> str:
    return d.isoformat()

def infer_year_from_path(path: Path) -> Optional[int]:
    m = re.search(r"(19|20)\d{2}", path.name)
    return int(m.group(0)) if m else None

def normalize_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()

EXTRACTOR_VERSION = "aet.py/1"
CONFIG_DIR = Path.home() / ".aeternitas"
CONFIG_PATH = CONFIG_DIR / "config.json"

def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def resolve_db_path(cli_db: Optional[str]) -> Path:
    if cli_db:
        return Path(cli_db)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    cfg = load_config()
    db = cfg.get("db_path") if isinstance(cfg, dict) else None
    if not db:
        default_db = CONFIG_DIR / "aeternitas.db"
        try:
            if not CONFIG_PATH.exists():
                CONFIG_PATH.write_text(
                    json.dumps({"db_path": str(default_db)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            pass
        return default_db
    return Path(str(db))

# -------------------------
# Text extractors
# -------------------------

def extract_text_from_pdf(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf puuttuu (pip install pypdf)")
    reader = PdfReader(str(path))
    pages = []
    for p in reader.pages:
        t = p.extract_text() or ""
        pages.append(t)
    return "\n\n".join(pages)

def extract_text_from_odt(path: Path) -> str:
    if odf_load is None or teletype is None:
        raise RuntimeError("odfpy puuttuu (pip install odfpy)")
    doc = odf_load(str(path))
    return teletype.extractText(doc.text)

def extract_text_from_image_ocr(path: Path, lang: str = "fin") -> str:
    if Image is None or pytesseract is None:
        raise RuntimeError("pillow/pytesseract puuttuu (pip install pillow pytesseract)")
    img = Image.open(str(path))
    # Perus-esikäsittely: harmaasävy + kontrasti
    g = ImageOps.grayscale(img)
    g = ImageEnhance.Contrast(g).enhance(2.0)
    # Tesseract toimii usein paremmin ilman binarointia; käytä psm 6 (yhtenäinen tekstialue)
    config = "--psm 6"
    return pytesseract.image_to_string(g, lang=lang, config=config)


def extract_text(path: Path) -> Tuple[str, str, str]:
    """
    Returns: (text, encoding, extractor_name)
    """
    suf = path.suffix.lower()
    if suf in (".txt", ".md", ".csv", ".log"):
        t, enc = safe_read_text(path)
        return t, enc, "txt"
    if suf == ".odt":
        t = extract_text_from_odt(path)
        return t, "utf-8", "odt"
    if suf == ".pdf":
        t = extract_text_from_pdf(path)
        return t, "utf-8", "pdf"
    if suf in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        t = extract_text_from_image_ocr(path)
        return t, "utf-8", "ocr"
    # fallback: yritä tekstiä
    t, enc = safe_read_text(path)
    return t, enc, "txt-fallback"


# -------------------------
# Parsers (timeline)
# -------------------------

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

    def flush():
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
            d = int(m.group(1)); mo = int(m.group(2))
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


# -------------------------
# Ingest
# -------------------------

def upsert_source(con: sqlite3.Connection, uri: str, source_type: str, scan_root: Optional[str], rel_path: Optional[str], mime: Optional[str]) -> int:
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    cur = con.execute("SELECT id FROM source WHERE uri=?", (uri,))
    row = cur.fetchone()
    if row:
        con.execute(
            "UPDATE source SET mime=COALESCE(?, mime), scan_root=COALESCE(?, scan_root), rel_path=COALESCE(?, rel_path) WHERE id=?",
            (mime, scan_root, rel_path, row["id"])
        )
        return int(row["id"])
    cur = con.execute(
        "INSERT INTO source(uri, source_type, scan_root, rel_path, mime, created_at) VALUES(?,?,?,?,?,?)",
        (uri, source_type, scan_root, rel_path, mime, now)
    )
    return int(cur.lastrowid)

def latest_revision(con: sqlite3.Connection, source_id: int) -> Optional[sqlite3.Row]:
    cur = con.execute(
        "SELECT id, size, mtime, sha256, status FROM revision WHERE source_id=? ORDER BY id DESC LIMIT 1",
        (source_id,)
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
    status: str="ok",
    error: Optional[str]=None,
    sha256: Optional[str]=None,
    st: Optional[os.stat_result]=None,
    compute_sha: bool=True,
) -> int:
    st = st or path.stat()
    observed_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sha = sha256 if not compute_sha else (sha256 or sha256_file(path))
    cur = con.execute(
        "INSERT INTO revision(source_id, observed_at, size, mtime, sha256, content_encoding, extractor, extractor_version, status, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (source_id, observed_at, st.st_size, st.st_mtime, sha, encoding, extractor, EXTRACTOR_VERSION, status, error)
    )
    rev_id = int(cur.lastrowid)
    cur2 = con.execute(
        "INSERT INTO doc(revision_id, title, text, json) VALUES (?,?,?,?)",
        (rev_id, title, text, json.dumps(extra_json, ensure_ascii=False))
    )
    con.execute("UPDATE source SET current_revision_id=? WHERE id=?", (rev_id, source_id))
    return int(cur2.lastrowid)

def ingest_file(con: sqlite3.Connection, path: Path, scan_root: Optional[Path]=None) -> None:
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
    source_id = upsert_source(con, uri=uri, source_type="file", scan_root=str(scan_root) if scan_root else None, rel_path=rel, mime=mime)
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
                    y = int(path.name[m.start():m.start()+4])
                    mo = int(m.group(2)); d = int(m.group(3))
                    extra_json["receipt"]["date"] = f"{y:04d}-{mo:02d}-{d:02d}"
        title = path.name
        add_revision_and_doc(con, source_id, path, title=title, text=text, encoding=enc, extractor=extractor, extra_json=extra_json, status="ok", sha256=sha, st=st)
    except Exception as e:
        add_revision_and_doc(con, source_id, path, title=path.name, text="", encoding="utf-8", extractor="error", extra_json={"mime": mime, "path": str(path), "rel_path": rel}, status="error", error=str(e), sha256=sha, st=st)


def rebuild_timeline(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM timeline")
    # Create timeline items for each doc
    cur = con.execute("""
        SELECT d.id AS doc_id, d.title, d.text, d.json
        FROM doc d
        JOIN revision r ON r.id = d.revision_id
        JOIN source s ON s.current_revision_id = r.id
        WHERE r.status = 'ok'
    """)
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
                (doc_id, d, "receipt", title, snippet[:300], json.dumps(receipt, ensure_ascii=False))
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
                (doc_id, d, "diary_entry", ent["title"], snip, json.dumps({}, ensure_ascii=False))
            )


# -------------------------
# CLI
# -------------------------

def cmd_ingest(args: argparse.Namespace) -> None:
    db = resolve_db_path(args.db)
    con = db_connect(db)
    scan_root = Path(args.scan_root).resolve() if args.scan_root else None
    with con:
        for p in args.paths:
            ingest_file(con, Path(p), scan_root=scan_root)
        rebuild_timeline(con)
    print(f"OK: ingest + timeline -> {db}")

def cmd_timeline(args: argparse.Namespace) -> None:
    con = db_connect(resolve_db_path(args.db))
    q = "SELECT date, kind, title, snippet FROM timeline ORDER BY date LIMIT ?"
    rows = con.execute(q, (args.limit,)).fetchall()
    for r in rows:
        print(f"{r['date']} [{r['kind']}] {r['title']}")
        if r["snippet"]:
            print(f"  {r['snippet']}")
        print()

def cmd_search(args: argparse.Namespace) -> None:
    con = db_connect(resolve_db_path(args.db))
    q = """
    SELECT d.title, snippet(doc_fts, 1, '[', ']', '…', 12) AS snip
    FROM doc_fts
    JOIN doc d ON d.id = doc_fts.rowid
    JOIN revision r ON r.id = d.revision_id
    JOIN source s ON s.current_revision_id = r.id
    WHERE doc_fts MATCH ?
      AND r.status = 'ok'
    LIMIT ?
    """
    rows = con.execute(q, (args.query, args.limit)).fetchall()
    for r in rows:
        print(f"- {r['title']}: {r['snip']}")

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Ingestoi tiedostot ja rakentaa aikajanan")
    p_ing.add_argument("--db", dest="db", default=None, help="SQLite-tiedosto (optionaalinen, muuten config)")
    p_ing.add_argument("paths", nargs="+", help="Tiedostopolut")
    p_ing.add_argument("--scan-root", dest="scan_root", help="Juuri, jonka alle rel_path lasketaan (suositus)")
    p_ing.set_defaults(func=cmd_ingest)

    p_tl = sub.add_parser("timeline", help="Tulostaa aikajanan")
    p_tl.add_argument("--db", dest="db", default=None, help="SQLite-tiedosto (optionaalinen, muuten config)")
    p_tl.add_argument("--limit", type=int, default=50)
    p_tl.set_defaults(func=cmd_timeline)

    p_s = sub.add_parser("search", help="FTS-haku")
    p_s.add_argument("--db", dest="db", default=None, help="SQLite-tiedosto (optionaalinen, muuten config)")
    p_s.add_argument("query")
    p_s.add_argument("--limit", type=int, default=20)
    p_s.set_defaults(func=cmd_search)

    return p

def main() -> None:
    p = build_parser()
    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
