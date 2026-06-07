"""Persistent settings and local progress storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


APP_DIR = Path.home() / "Library" / "Application Support" / "ProductFormFiller"
SETTINGS_PATH = APP_DIR / "settings.json"
PROGRESS_PATH = APP_DIR / "progress.json"
LOG_PATH = APP_DIR / "filled_rows.log"


@dataclass(slots=True)
class AppSettings:
    last_csv_path: str = ""
    last_completed_row: int = -1
    typing_profile: str = "normal"
    auto_advance: bool = False
    dark_mode: bool = True


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_settings() -> AppSettings:
    ensure_app_dir()
    data = _read_json(SETTINGS_PATH)
    defaults = asdict(AppSettings())
    defaults.update({key: value for key, value in data.items() if key in defaults})
    return AppSettings(**defaults)


def save_settings(settings: AppSettings) -> None:
    ensure_app_dir()
    SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_progress() -> dict[str, Any]:
    ensure_app_dir()
    return _read_json(PROGRESS_PATH)


def save_progress(csv_path: str, last_completed_row: int) -> None:
    ensure_app_dir()
    payload = {
        "csv_path": csv_path,
        "last_completed_row": last_completed_row,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    PROGRESS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_fill_log(csv_path: str, row_index: int, sku: str) -> None:
    ensure_app_dir()
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp}\trow={row_index + 1}\tsku={sku}\tcsv={csv_path}\n"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
