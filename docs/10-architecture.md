# docs/10-architecture.md

## architecture: pipeline and boundaries

Aeternitas indexing follows a pipeline pattern:

1) **Connector**: produces `SourceItem` objects from sources (reference to the file/item, mime, mtime, size, metadata)
2) **Extractor**: converts a source into text + structured metadata (and optionally preliminary events)
3) **Enrich**: enriches results (dates, receipt fields, entities/topics)
4) **DB**: stores sources, revisions, extracted text, full-text index (FTS), and timeline events

## provenance and revisions

- Each source has one or more revisions.
- A revision is defined by keys like: `sha256`, `mtime`, `size` (plus extractor version).
- If `sha256` matches the latest revision → ingest may skip (no-op).
- If changed → create a new revision and write new extracted outputs.

All derived facts/events should link to a revision, not just “the file”.

## paths

Paths must follow this rule:

- store `scan_root` separately (e.g., "machine1:/home/user" or "backupdisk_2026")
- store the item path as `rel_path` relative to that root

This enables comparing snapshots across machines/drives and avoids accidental dependence on a specific mount point.

## symlinks (no-follow by default)

- Connectors and manifest scanning must not follow symlinks by default.
- Record symlinks as separate items and store `symlink_target`.
- Optional dereference behavior may exist as opt-in, but default must be off.

## modularization direction (later refactor)

Initially the repo can remain simple (two scripts).
When refactoring, keep strict boundaries:

- index tool: `aet.py ...`
- manifest tool: `manifest.py ...`

Refactors must not break CLI usage nor re-ingestion semantics.
