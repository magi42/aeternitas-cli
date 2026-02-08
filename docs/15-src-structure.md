# docs/15-src-structure.md

## Proposed `src/` substructure

Goal: keep `aet.py` and `manifest.py` as thin CLIs while moving implementation into
well-scoped modules. This keeps the codebase extensible as new file types and
connectors are added.

### Top-level layout

```
src/
  aeternitas/
    __init__.py
    common/
      __init__.py
      config.py
      paths.py
      hash.py
      time.py
      errors.py

    index/
      __init__.py
      cli.py
      db/
        __init__.py
        schema.py
        queries.py
      ingest/
        __init__.py
        pipeline.py
        source.py
        revision.py
      extractors/
        __init__.py
        base.py
        text.py
        odt.py
        pdf.py
        ocr.py
        image.py
      parse/
        __init__.py
        diary.py
        receipt.py
      timeline/
        __init__.py
        build.py
      connectors/
        __init__.py
        filetree.py
        digikam.py

    manifest/
      __init__.py
      cli.py
      scan.py
      sqlite.py
      jsonl.py
      diff.py
```

### Module responsibilities

- `aeternitas/common/`
  - Shared utilities: config resolution, path normalization, hashing, time helpers,
    safe JSON writing, error types.

- `aeternitas/index/`
  - Indexing pipeline and SQLite+FTS.
  - `cli.py` contains argument parsing and delegates to pipeline.
  - `extractors/` contains per-format extraction logic.
  - `parse/` contains receipt/diary parsing heuristics.
  - `timeline/` builds timeline rows from extracted data.
  - `connectors/` produce `SourceItem` objects (file tree now; digiKam later).

- `aeternitas/manifest/`
  - Manifest scanning, encoding-safe JSONL output, and SQLite storage.
  - `diff.py` reserved for snapshot comparison.

### Migration path

1. Create `src/` and move helpers out of `aet.py` into `aeternitas_index/` modules.
2. Keep `aet.py` as a thin wrapper that imports and calls `aeternitas_index.cli`.
3. Keep `manifest.py` as a thin wrapper that imports and calls `aeternitas_manifest.cli`.
4. Add tests for revisioning, symlink no-follow, and surrogate-safe JSONL.

This structure keeps both tools separate while enabling growth per file type and connector.
