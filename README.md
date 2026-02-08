# Aeternitas Command-line Tools

Personal history tooling for creating chronologies, as well as summaries about activity topics.

Two tools (kept separate):
- `aet.py` (archive/index): builds SQLite + FTS index, timeline, and keeps revision history.
- `manifest.py` (manifest): snapshots directory trees, detects missing content and duplicates by hash.

Implementation code lives under `src/aeternitas/`, with `aet.py` as a thin CLI wrapper.

## Quick start

Indexing (archive/index):

```bash
./aet.py ingest --db arkisto.db /path/to/files... --scan-root /path/to
./aet.py timeline --db arkisto.db --limit 50
./aet.py search --db arkisto.db "mother"
```

Manifest snapshot:

```bash
./manifest.py <DISK_ID> /path/to/root --outdir . --hash sha256
```

## Notes

- Symlinks are recorded but never followed.
- Index stores `scan_root` separately; file paths are stored as `rel_path`.
- Re-ingest creates new revisions only when content changes.
- Manifest output writes both display paths and raw bytes paths (`*_b64`) to avoid UTF-8 crashes.

## Config

`aet.py` reads the DB path from `~/.aeternitas/config.json`. If the config
directory or file is missing, they are created automatically and the default
DB path is set to `~/.aeternitas/aeternitas.db`:

```json
{
  "db_path": "/full/path/to/arkisto.db"
}
```

If not set, pass the DB path on the CLI as before.
