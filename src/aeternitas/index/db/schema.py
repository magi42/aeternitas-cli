from __future__ import annotations

SCHEMA_SQL = r"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS source (
  id INTEGER PRIMARY KEY,
  uri TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,     -- file, gmail, etc (MVP: file)
  scan_root TEXT,                -- esim. /home/user/data (MVP: vapaa)
  rel_path TEXT,                 -- suhteellinen polku (suositus)
  mime TEXT,
  current_revision_id INTEGER,   -- latest revision for "current view"
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revision (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL,
  observed_at TEXT NOT NULL,
  size INTEGER,
  mtime REAL,
  sha256 TEXT,
  content_encoding TEXT,
  extractor TEXT,                -- txt/pdf/odt/ocr
  extractor_version TEXT,        -- tool/extractor version
  status TEXT NOT NULL,          -- ok/error
  error TEXT,
  FOREIGN KEY(source_id) REFERENCES source(id)
);

CREATE TABLE IF NOT EXISTS doc (
  id INTEGER PRIMARY KEY,
  revision_id INTEGER NOT NULL UNIQUE,
  title TEXT,
  text TEXT,
  json TEXT,                      -- lisämetat (esim. kuitin kentät)
  FOREIGN KEY(revision_id) REFERENCES revision(id)
);

-- Full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
  title, text,
  content='doc', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS doc_ai AFTER INSERT ON doc BEGIN
  INSERT INTO doc_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS doc_au AFTER UPDATE ON doc BEGIN
  INSERT INTO doc_fts(doc_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
  INSERT INTO doc_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS doc_ad AFTER DELETE ON doc BEGIN
  INSERT INTO doc_fts(doc_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
END;

CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL,
  date TEXT NOT NULL,            -- ISO yyyy-mm-dd
  kind TEXT NOT NULL,            -- diary_entry | receipt | other
  title TEXT,
  snippet TEXT,
  json TEXT,
  FOREIGN KEY(doc_id) REFERENCES doc(id)
);

CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date);
"""
