# docs/20-index-sqlite.md

## index data store (SQLite + FTS)

The indexing tool stores extracted information in a local SQLite database to provide:

- easy installation (no server)
- full-text search (FTS5)
- revision history (re-ingestion support)
- timeline generation

## minimal tables (directional)

- `source`
  - `id`
  - `source_uri` (e.g., file://, digikam://)
  - `scan_root` (label/id)
  - `rel_path`
  - `mime`, etc.

- `revision`
  - `id`, `source_id`
  - `sha256`, `mtime`, `size`
  - `extractor` / `extractor_version`
  - `ingested_at`

- `doc`
  - `id`, `revision_id`
  - `text` (extracted text)
  - `meta_json` (receipt fields, EXIF, tags, etc.)
  - `lang` (optional)

- `doc_fts` (FTS5)
  - `doc_id`, `text` (mirrors doc.text)

- `timeline`
  - `id`, `revision_id`
  - `ts` (ISO8601 or epoch)
  - `kind` (diary_entry / receipt / email / photo / ...)
  - `title`, `snippet`
  - `data_json` (person/place/tags/amount/currency/etc.)

## timeline generation (MVP approach)

In MVP, timeline events are built from two main paths:

1) “explicit dates present in the source”
- receipts: date + amount + merchant
- photos: datetime + tags/caption

2) “diary entries”
- when text contains diary date headings (e.g., "Mon 24.2." or "24.2.2025"), create one event per entry

Later improvements (better segmentation, entity extraction, geolocation) belong in the enrich stage.

## search

- use FTS for the extracted text corpus
- results show title/snippet + pointer back to the source (scan_root + rel_path)
- provenance is preserved so users can always open the original document

## growth notes

SQLite is sufficient for a long time. If the dataset grows significantly, PostgreSQL (and optionally vector search) can be introduced later, but it is not required for MVP.
