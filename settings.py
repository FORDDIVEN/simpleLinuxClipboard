from __future__ import annotations

import json
from typing import Any

from config import SETTINGS_FILE
from utils import ensure_dir


DEFAULT_SETTINGS = {
    "global_hotkey_enabled": False,
    "global_hotkey": "Meta+V",
}


def load_settings() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)

    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        settings.update(data)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    ensure_dir(SETTINGS_FILE.parent)
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
