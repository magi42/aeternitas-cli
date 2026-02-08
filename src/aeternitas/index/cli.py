from __future__ import annotations

import argparse
from pathlib import Path

from aeternitas.common.config import resolve_db_path
from aeternitas.index.db.connection import db_connect
from aeternitas.index.ingest.ingest import ingest_file
from aeternitas.index.timeline.build import rebuild_timeline


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
