#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import gzip
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable, Tuple
import getpass
import stat as statmod

def fs_safe_text(s: str) -> str:
    """
    Tee filesystem-str:stä JSON/UTF-8-turvallinen.
    - säilyttää validit UTF-8-merkit
    - säilyttää surrogateescape-merkit (ei kaadu kirjoituksessa)
    """
    b = os.fsencode(s)
    return b.decode("utf-8", "surrogateescape")

def fs_bytes(p: Path) -> bytes:
    return os.fsencode(str(p))

def fs_display_from_bytes(b: bytes) -> str:
    return b.decode("utf-8", "surrogateescape")

def b64_bytes(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def rel_path_bytes(p: Path, root: Path) -> bytes:
    try:
        r = os.path.relpath(fs_bytes(p), fs_bytes(root))
        if r in (b"", b"."):
            return b"."
        return r.replace(os.sep.encode(), b"/")
    except Exception:
        r = os.path.relpath(str(p), str(root)).replace(os.sep, "/")
        return os.fsencode(r)

def rel_path(p: Path, root: Path) -> str:
    """
    Palauta polku suhteessa rootiin ilman root-prefixiä.
    Käytä POSIX-muotoa (/) jotta se on vakio Linuxissa.
    """
    try:
        r = p.relative_to(root)
        return "." if str(r) == "" else r.as_posix()
    except Exception:
        return os.path.relpath(str(p), str(root)).replace(os.sep, "/")

@dataclass
class Options:
    disk_id: str
    root: Path
    outdir: Path
    include_dirs: bool
    hash_alg: str      # "none" or "sha256"
    btime_mode: str    # "none" or "auto" or "stat"
    sqlite_fast: bool
    json_pretty: bool
    progress_every: int


def utc_ts() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def default_root(disk_id: str) -> Path:
    user = getpass.getuser()
    return Path("/media") / user / disk_id


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def compute_hash(path: Path, alg: str) -> Optional[str]:
    if alg == "none":
        return None
    if alg != "sha256":
        raise ValueError(f"Unsupported hash alg: {alg}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def has_st_birthtime() -> bool:
    try:
        st = os.stat(__file__, follow_symlinks=False)
        return hasattr(st, "st_birthtime")
    except Exception:
        return False


def btime_from_stat_cmd(path: Path) -> Optional[float]:
    """
    GNU coreutils: stat --printf=%W file  -> birth time as epoch seconds, 0 if unknown
    """
    try:
        out = subprocess.check_output(
            ["stat", "--printf=%W", "--", str(path)],
            stderr=subprocess.DEVNULL,
        )
        s = out.decode("utf-8", "replace").strip()
        if not s:
            return None
        v = int(s)
        if v <= 0:
            return None
        return float(v)
    except Exception:
        return None


def get_btime(path: Path, st: os.stat_result, mode: str) -> Optional[float]:
    if mode == "none":
        return None
    if mode == "auto":
        if hasattr(st, "st_birthtime"):
            try:
                bt = float(getattr(st, "st_birthtime"))
                return bt if bt > 0 else None
            except Exception:
                return None
        return None
    if mode == "stat":
        return btime_from_stat_cmd(path)
    raise ValueError(f"Unknown btime mode: {mode}")


def iter_entries(root: Path, include_dirs: bool) -> Iterable[Tuple[Path, str, Optional[str]]]:
    """
    Yield (path, kind, link_target).
    kind ∈ {"file","dir","symlink"}.
    Never follows symlinks, never traverses into symlinked dirs.
    """
    stack = [root]

    while stack:
        d = stack.pop()

        # Optionally include the directory itself as an entry
        if include_dirs:
            yield (Path(d), "dir", None)

        try:
            with os.scandir(d) as it:
                for entry in it:
                    p = Path(entry.path)

                    # Symlink: record, but do not traverse.
                    try:
                        if entry.is_symlink():
                            try:
                                target = os.readlink(p)
                            except OSError:
                                target = None
                            yield (p, "symlink", target)
                            continue
                    except OSError:
                        # Can't even determine; skip.
                        continue

                    # Real directory (not symlink)
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(p)
                            continue
                    except OSError:
                        continue

                    # Real file (not symlink)
                    try:
                        if entry.is_file(follow_symlinks=False):
                            yield (p, "file", None)
                    except OSError:
                        continue

        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue


def sqlite_set_pragmas(con: sqlite3.Connection, fast: bool) -> None:
    cur = con.cursor()
    if fast:
        cur.execute("PRAGMA journal_mode=OFF;")
        cur.execute("PRAGMA synchronous=OFF;")
    else:
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")
    con.commit()


def sqlite_init(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scans (
      scan_id       INTEGER PRIMARY KEY,
      disk_id       TEXT NOT NULL,
      root          TEXT NOT NULL,
      started_utc   TEXT NOT NULL,
      finished_utc  TEXT,
      host          TEXT,
      user          TEXT,
      platform      TEXT,
      hash_alg      TEXT,
      include_dirs  INTEGER,
      btime_mode    TEXT,
      tool_version  TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS entries (
      scan_id     INTEGER NOT NULL,
      path        TEXT NOT NULL,
      path_b64    TEXT,           -- raw bytes (base64)
      name        TEXT NOT NULL,
      name_b64    TEXT,           -- raw bytes (base64)
      kind        TEXT NOT NULL,    -- 'file' | 'dir' | 'symlink'
      bytes       INTEGER,          -- regular files only
      link_target TEXT,             -- symlinks only (readlink text)
      link_target_b64 TEXT,         -- symlinks only (raw bytes, base64)
      link_len    INTEGER,          -- symlinks only (usually length of link text)
      mtime       REAL NOT NULL,
      ctime       REAL NOT NULL,
      btime       REAL,             -- epoch seconds if available
      sha256      TEXT,             -- files only (optional)
      PRIMARY KEY (scan_id, path)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_name ON entries(name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_mtime ON entries(mtime);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_sha256 ON entries(sha256);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_link_target ON entries(link_target);")
    con.commit()
    # Backfill columns if DB already existed without them
    try:
        cur.execute("ALTER TABLE entries ADD COLUMN path_b64 TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE entries ADD COLUMN name_b64 TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE entries ADD COLUMN link_target_b64 TEXT;")
    except sqlite3.OperationalError:
        pass
    con.commit()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create file manifest as JSONL.gz + SQLite. Symlinks recorded, never followed."
    )
    ap.add_argument("disk_id", help="Disk identifier, e.g. SGBP5TB2018A")
    ap.add_argument("path", nargs="?", default=None,
                    help="Optional override root path. Default: /media/$USER/<disk_id>")
    ap.add_argument("--outdir", default=".", help="Output directory (default: current)")
    ap.add_argument("--include-dirs", action="store_true", help="Include directories as entries")
    ap.add_argument("--hash", choices=["none", "sha256"], default="none",
                    help="Optional checksum for regular files (default: none)")
    ap.add_argument("--btime", choices=["none", "auto", "stat"], default="none",
                    help=("Birth/creation time: none | auto (uses st_birthtime if available) | "
                          "stat (slow: runs GNU stat per entry)"))
    ap.add_argument("--sqlite-fast", action="store_true",
                    help="Faster SQLite writes (riskier if power loss during scan)")
    ap.add_argument("--json-pretty", action="store_true", help="Pretty JSON (bigger files)")
    ap.add_argument("--progress-every", type=int, default=20000,
                    help="Print progress every N entries (default: 20000)")
    args = ap.parse_args()

    disk_id = args.disk_id
    root = Path(args.path) if args.path else default_root(disk_id)
    outdir = Path(args.outdir)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        return 1

    ensure_dir(outdir)

    ts = utc_ts()
    json_path = outdir / f"manifest_{disk_id}_{ts}.jsonl.gz"
    sql_path = outdir / f"manifest_{disk_id}_{ts}.sqlite"
    err_path = outdir / f"manifest_{disk_id}_{ts}.errors.log"

    opt = Options(
        disk_id=disk_id,
        root=root,
        outdir=outdir,
        include_dirs=args.include_dirs,
        hash_alg=args.hash,
        btime_mode=args.btime,
        sqlite_fast=args.sqlite_fast,
        json_pretty=args.json_pretty,
        progress_every=max(1, args.progress_every),
    )

    if opt.btime_mode == "auto" and not has_st_birthtime():
        print("Note: btime=auto likely unavailable here; btime will be NULL.", file=sys.stderr)
    if opt.btime_mode == "stat":
        print("Note: btime=stat is slow (runs GNU stat per entry).", file=sys.stderr)

    started = time.time()
    host = platform.node()
    user = getpass.getuser()
    plat = platform.platform()

    con = sqlite3.connect(str(sql_path))
    sqlite_set_pragmas(con, opt.sqlite_fast)
    sqlite_init(con)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO scans(disk_id, root, started_utc, host, user, platform, hash_alg,
                          include_dirs, btime_mode, tool_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opt.disk_id, str(opt.root), ts, host, user, plat, opt.hash_alg,
        1 if opt.include_dirs else 0,
        opt.btime_mode,
        "manifest.py/2",
    ))
    scan_id = cur.lastrowid
    con.commit()

    errf = err_path.open("w", encoding="utf-8", errors="replace")
    gz = gzip.open(str(json_path), "wt", encoding="utf-8", errors="surrogateescape", newline="\n", compresslevel=9)

    def log_err(kind: str, path: Path, msg: str) -> None:
        errf.write(f"{kind}\t{fs_safe_text(str(path))}\t{msg}\n")

    batch = []
    BATCH_N = 2000

    count = 0
    files = 0
    dirs = 0
    syms = 0

    try:
        for p, kind, link_target in iter_entries(opt.root, opt.include_dirs):
            count += 1
            name = p.name

            # Always lstat: never follow symlinks
            try:
                st = os.stat(p, follow_symlinks=False)
            except OSError as e:
                log_err("STAT_FAIL", p, repr(e))
                continue

            mode = st.st_mode

            # Classify safely by st_mode
            if kind == "dir":
                if not statmod.S_ISDIR(mode):
                    continue
                size = None
                sha = None
                link_len = None
                dirs += 1

            elif kind == "file":
                if not statmod.S_ISREG(mode):
                    # skip non-regular files (fifo, socket, device, etc.)
                    continue
                size = int(st.st_size)
                link_len = None
                sha = None
                if opt.hash_alg != "none":
                    try:
                        sha = compute_hash(p, opt.hash_alg)
                    except OSError as e:
                        log_err("HASH_FAIL", p, repr(e))
                        sha = None
                files += 1

            elif kind == "symlink":
                if not statmod.S_ISLNK(mode):
                    continue
                size = None  # avoid confusion: symlink does not have "target file size"
                sha = None
                link_len = int(st.st_size) if st.st_size is not None else None
                syms += 1

            else:
                continue

            mtime = float(st.st_mtime)
            ctime = float(st.st_ctime)
            btime = get_btime(p, st, opt.btime_mode)

            path_rel_b = rel_path_bytes(p, opt.root)
            path_txt = fs_display_from_bytes(path_rel_b)
            path_b64 = b64_bytes(path_rel_b)

            name_b = os.path.basename(path_rel_b) if path_rel_b not in (b"", b".") else os.path.basename(fs_bytes(p))
            name_txt = fs_display_from_bytes(name_b)
            name_b64 = b64_bytes(name_b)

            # symlink target: tee se mieluummin byteinä suoraan, jotta et saa surrogaatteja
            target_txt = None
            target_b64 = None
            if kind == "symlink":
                try:
                    target_b = os.readlink(fs_bytes(p))  # bytes in
                    if isinstance(target_b, str):
                        target_txt = fs_safe_text(target_b)
                        target_b64 = b64_bytes(os.fsencode(target_b))
                    else:
                        target_txt = fs_display_from_bytes(target_b)
                        target_b64 = b64_bytes(target_b)
                except OSError:
                    target_txt = None
                    target_b64 = None

            rec = {
                "disk_id": opt.disk_id,
                "root": fs_safe_text(str(opt.root)),
                "root_b64": b64_bytes(fs_bytes(opt.root)),
                "scan_started_utc": ts,
                "path": path_txt,                      # <-- RELATIIVINEN
                "path_b64": path_b64,
                "name": name_txt,
                "name_b64": name_b64,
                "kind": kind,
                "bytes": size,
                "link_target": target_txt,
                "link_target_b64": target_b64,
                "link_len": link_len,
                "mtime": mtime,
                "ctime": ctime,
                "btime": btime,
                "sha256": sha,
            }
            if opt.json_pretty:
                gz.write(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
            else:
                gz.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

            batch.append((scan_id, path_txt, path_b64, name_txt, name_b64, kind, size, target_txt, target_b64, link_len, mtime, ctime, btime, sha))

            if len(batch) >= BATCH_N:
                cur.executemany("""
                    INSERT OR REPLACE INTO entries
                    (scan_id, path, path_b64, name, name_b64, kind, bytes, link_target, link_target_b64, link_len, mtime, ctime, btime, sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                con.commit()
                batch.clear()

            if opt.progress_every and (count % opt.progress_every == 0):
                elapsed = time.time() - started
                print(f"{count} entries ({files} files, {dirs} dirs, {syms} symlinks) in {elapsed:.1f}s ...",
                      file=sys.stderr)

        if batch:
            cur.executemany("""
                INSERT OR REPLACE INTO entries
                (scan_id, path, path_b64, name, name_b64, kind, bytes, link_target, link_target_b64, link_len, mtime, ctime, btime, sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            con.commit()
            batch.clear()

        finished = utc_ts()
        cur.execute("UPDATE scans SET finished_utc=? WHERE scan_id=?", (finished, scan_id))
        con.commit()

    finally:
        try: gz.close()
        except Exception: pass
        try: errf.close()
        except Exception: pass
        try: con.close()
        except Exception: pass

    elapsed = time.time() - started
    print(f"Wrote: {json_path}")
    print(f"Wrote: {sql_path}")
    print(f"Errors: {err_path}")
    print(f"Root: {opt.root}")
    if opt.include_dirs:
        print(f"Entries: {count} ({files} files, {dirs} dirs, {syms} symlinks) in {elapsed:.1f}s")
    else:
        print(f"Entries: {count} ({files} files, {syms} symlinks) in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
