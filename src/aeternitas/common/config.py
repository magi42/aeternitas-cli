from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".aeternitas"
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_DB_NAME = "aeternitas.db"


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_db_path(cli_db: Optional[str]) -> Path:
    if cli_db:
        return Path(cli_db)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    cfg = load_config()
    db = cfg.get("db_path") if isinstance(cfg, dict) else None
    if not db:
        default_db = CONFIG_DIR / DEFAULT_DB_NAME
        try:
            if not CONFIG_PATH.exists():
                CONFIG_PATH.write_text(
                    json.dumps({"db_path": str(default_db)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            pass
        return default_db
    return Path(str(db))
