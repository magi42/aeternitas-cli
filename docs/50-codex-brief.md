# docs/50-codex-brief.md

## Codex brief: aeternitas (paste into Codex if needed)

### project

- Project name: `aeternitas`
- Current repo root contains two primary scripts:
  - `aet.py` (index/timeline/search)
  - `manifest.py` (backup snapshots/diff)
- Management CLI: run scripts directly (symlink from `bin/` if desired)

### strict requirements

1) Symlinks: no-follow by default. Record symlinks separately and store `symlink_target`.
2) Paths: do not persist absolute drive roots; use `scan_root` + `rel_path`.
3) Revisions: changed source → new revision; newest is default; old revisions remain.
4) Provenance: all events/facts must link to source + revision.
5) Manifest: handle non-UTF-8 paths (surrogateescape); store raw bytes as `path_b64/path_hex`.

### sources / formats (incremental support)

- txt/md/html
- odt (diaries)
- pdf (receipts/documents)
- scanned receipts (OCR; VueScan OCR is imperfect; accept uncertainty)
- Transkribus OCR exports (handwritten diaries)
- photos: **digiKam** (metadata: datetime, GPS, hierarchical tags, caption/comment)

### near-term tasks

- keep existing functionality working
- add `aet` wrapper + README + .gitignore
- add tests:
  - symlink no-follow
  - manifest surrogateescape write
  - re-indexing creates new revision
- refactor into modules/packages only after the above is stable
