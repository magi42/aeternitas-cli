# docs/40-manifest-tool.md

## manifest tool (backups and missing-content forensics)

The manifest tool is a separate utility for:

- taking “snapshots” of directory trees or backup drives
- diffing snapshots
- locating missing content and identifying where the same hash exists elsewhere

This tool remains separate from the indexing database for now.

## principles

- **No-follow symlinks**: record symlinks as their own entries and store `symlink_target`.
- Record items with:
  - `type`: file/dir/symlink
  - `size`, `mtime`
  - `sha256` (files only)
  - `rel_path` (relative to snapshot root)
- Each snapshot has a `root_label` (e.g., "backup_2025_12_usb").

## critical Unicode/encoding issue (surrogateescape)

File systems can contain names that are not valid UTF-8.
In Python these may appear as surrogate characters (`\udc..`), and naive UTF-8 encoding or JSON writing can crash.

Requirement: snapshot writing must never crash due to such paths.

Recommended storage strategy:
- store both:
  - `path` (display path, `os.fsdecode`, may contain surrogates)
  - `path_b64` or `path_hex` (raw bytes from `os.fsencode`)
- when writing gzip+JSONL:
  - write using `errors="surrogateescape"` or byte-preserving logic that guarantees output

Add a test that injects a surrogate path and ensures output is produced.

## diff approach

When comparing snapshot A and B:
- added (new path)
- removed (missing path)
- changed (same path, different sha256/size)

Missing-content search:
- if removed/changed → search the same sha256 in other snapshots (“which drive still has it”).
