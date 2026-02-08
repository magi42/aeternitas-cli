# docs/30-sources-and-digikam.md

## sources and connectors

Indexing starts with file-based sources and expands later.

### files and directory trees (file://)

- record paths as `rel_path` relative to a `scan_root`
- handle symlinks (no-follow)
- detect mime (extension and/or magic)

Supported formats in MVP:
- txt / md
- html
- odt (ODF)
- pdf (text, and OCR when needed)
- images (OCR for receipts initially, broader OCR later)

### scans and OCR

- VueScan OCR can be inaccurate → the system should accept imperfect text and still store it (with provenance).
- Transkribus outputs (handwritten diary OCR) can be ingested as text exports (e.g., .txt/.xml) in the first iteration.

## digiKam (photo management)

digiKam is the photo manager. The connector should:

- read the digiKam database (often SQLite; sometimes MySQL/MariaDB depending on setup)
- extract photo metadata:
  - caption/comment
  - datetime (EXIF or digiKam fields)
  - GPS (if present)
  - hierarchical tags
  - file path (mapped into scan_root + rel_path model)

The connector outputs `SourceItem` objects (file references + metadata).
Full image content extraction is not required by default (except OCR-specific cases such as scanned receipts), because photos’ primary value is metadata + tags + captions.

## future sources

- Maildir/MBOX (local email)
- cloud services (Drive/Photos/Dropbox)
- social platforms (X, Facebook, Instagram)

These will be implemented as separate connectors with their own authentication and rate-limit handling.
