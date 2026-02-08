# Aeternitas AI Context

Project: `aeternitas`

Goals:
- Local-first system that extracts structured, chronological and topical personal-history data from heterogeneous sources.
- Keep archive/index DB separate from manifest/snapshot output DBs.
- Support re-indexing with revision history (no data loss).
- Preserve provenance: every extracted doc/event must link to its source + revision.

Tools:
- `aet.py` (archive/index)
  - SQLite + FTS index from files.
  - Timeline from diaries/receipts.
  - Revisions on change (sha256, mtime, size, extractor version).
  - Symlinks must be recorded but never followed.
- `manifest.py` (backup/manifest)
  - Snapshot directory trees; detect missing content and duplicates by hash.
  - Output JSONL.GZ and/or SQLite.
  - Must be encoding-safe: paths may contain invalid UTF-8 bytes.
  - Store display path plus raw bytes as base64 (`*_b64`).

Config:
- `aet.py` can read DB path from `~/.aeternitas/config.json` (`db_path`).

Non-goals (for now):
- Merging manifest output into archive/index DB.
- Heavy refactor into packages (planned later).

Data sources (incremental):
- Text files: `.txt`, `.md`
- ODT diaries
- PDF receipts/documents: text extraction; OCR for scanned PDFs/images
- Images of receipts: OCR; handle imperfect outputs
- Handwritten diaries: treat Transkribus exports as text input initially
- Photos (later): digiKam DB connector (datetime, GPS, tags, captions, file paths)
