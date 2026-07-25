from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _state_path() -> Path:
    runtime = Path(os.getenv("OVERLAY_RUNTIME_DIR", Path.cwd()))
    return runtime / "state.json"


def save_state(**kwargs: Any) -> None:
    """Speichert beliebige Werte in state.json (inkrementell)."""
    path = _state_path()
    try:
        existing: dict = {}
        if path.exists():
            existing = json.loads(path.read_text("utf-8"))
        existing.update(kwargs)
        existing["_saved_at"] = time.time()
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        log.exception("state.json speichern fehlgeschlagen")


def load_state() -> dict:
    """Lädt die gesamte state.json. Gibt leeres dict bei Fehler."""
    path = _state_path()
    try:
        if path.exists():
            data = json.loads(path.read_text("utf-8"))
            data.pop("_saved_at", None)
            return data
    except Exception:
        log.exception("state.json laden fehlgeschlagen")
    return {}
