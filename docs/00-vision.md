# docs/00-vision.md

## aeternitas: vision and purpose

Aeternitas is a local-first system for extracting and organizing personal-history information from heterogeneous sources (files, directory trees, diaries, receipts, PDF/ODT/HTML, photo databases, emails, etc.) so it can be explored:

- **chronologically** (timeline: what happened when)
- **by topic and entities** (people, places, objects/things, organizations)

A core requirement is **provenance**: every extracted fact/event must always link back to the original source and a specific revision of that source.

## two separate tools (kept separate on purpose)

This repository contains two tools that are intentionally kept separate (at least initially):

1) **Indexing and analysis** (`aet.py`)
- extracts text + metadata from multiple formats
- builds full-text search and a timeline
- stores data in a local SQLite database (with FTS)

2) **Backup/drive manifests** (`manifest.py`)
- snapshots directory trees / backup drives
- helps locate missing content (where a given hash still exists)
- uses its own storage format (e.g., JSONL.GZ and/or its own SQLite), **not merged** with the index DB at this stage

## non-negotiable requirements

- **Symlinks**: do not follow symlinks by default. Record symlinks as their own entries and store `symlink_target`.
- **Paths**: do not persist absolute “drive root” paths. Store `scan_root` separately and store `rel_path` relative to that root.
- **Revisions & re-ingestion**: if a source changes, a new revision is created; the newest revision is the default view; older revisions remain for history.
- **Provenance**: preserve the chain doc/event → source → revision at all times.

## local-first, extensible

Initial target environment is Kubuntu Linux. The system should be designed so the same pipeline can later support Windows/macOS, Android data sources, and online services (Drive/Photos/social platforms) via separate connectors.

