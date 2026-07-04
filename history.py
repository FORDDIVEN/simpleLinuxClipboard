from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from config import (
    CACHE_DIR,
    HISTORY_FILE,
    IMAGE_EXTENSIONS,
    MAX_HISTORY_ITEMS,
    SUPPORTED_TYPES,
)
from utils import ensure_dir, new_id, remove_file, utc_now_iso


class HistoryStore:
    def __init__(
        self,
        history_file: Path = HISTORY_FILE,
        cache_dir: Path = CACHE_DIR,
        max_items: int = MAX_HISTORY_ITEMS,
    ) -> None:
        self.history_file = history_file
        self.cache_dir = cache_dir
        self.max_items = max_items
        self.items: list[dict[str, Any]] = []

        ensure_dir(self.history_file.parent)
        ensure_dir(self.cache_dir)
        self.load()
        self.cleanup_orphan_images()

    def load(self) -> None:
        if not self.history_file.exists():
            self.items = []
            self.save()
            return

        try:
            data = json.loads(self.history_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.items = []
            self.save()
            return

        raw_items = data if isinstance(data, list) else data.get("items", [])
        self.items = [
            item for item in raw_items
            if isinstance(item, dict) and self._is_valid_item(item)
        ]
        self._enforce_limit()
        self.save()

    def save(self) -> None:
        ensure_dir(self.history_file.parent)
        payload = {"items": self.items}
        self.history_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_text(self, text: str) -> dict[str, Any] | None:
        value = text.strip()
        if not value:
            return None
        if self._is_image_reference_text(value):
            return None

        existing = self._find_text_duplicate(value)
        if existing is not None:
            return self._move_to_top(existing)

        item = {
            "id": new_id(),
            "type": "text",
            "content": value,
            "pinned": False,
            "created_at": utc_now_iso(),
        }
        self._prepend(item)
        return item

    def add_image(self, path: str | Path, fingerprint: str | None = None) -> dict[str, Any]:
        image_path = str(Path(path).expanduser())
        existing = self._find_image_duplicate(image_path, fingerprint)
        if existing is not None:
            remove_file(image_path)
            return self._move_to_top(existing)

        item = {
            "id": new_id(),
            "type": "image",
            "path": image_path,
            "pinned": False,
            "created_at": utc_now_iso(),
        }
        if fingerprint is not None:
            item["fingerprint"] = fingerprint

        self._prepend(item)
        return item

    def pin(self, item_id: str, pinned: bool = True) -> bool:
        item = self.get(item_id)
        if item is None:
            return False

        item["pinned"] = pinned
        self.save()
        return True

    def unpin(self, item_id: str) -> bool:
        return self.pin(item_id, False)

    def delete(self, item_id: str) -> bool:
        for index, item in enumerate(self.items):
            if item.get("id") == item_id:
                removed = self.items.pop(index)
                self._delete_image_file(removed)
                self.save()
                return True
        return False

    def clear(self, include_pinned: bool = False) -> None:
        kept: list[dict[str, Any]] = []

        for item in self.items:
            if item.get("pinned") and not include_pinned:
                kept.append(item)
            else:
                self._delete_image_file(item)

        self.items = kept

        if include_pinned:
            self._clear_cache_dir()

        self.save()

    def search(self, query: str) -> list[dict[str, Any]]:
        value = query.strip().casefold()
        if not value:
            return list(self.items)

        return [
            item for item in self.items
            if item.get("type") == "text"
            and value in str(item.get("content", "")).casefold()
        ]

    def get(self, item_id: str) -> dict[str, Any] | None:
        return next((item for item in self.items if item.get("id") == item_id), None)

    def cleanup_orphan_images(self) -> None:
        referenced = {
            Path(item["path"]).resolve()
            for item in self.items
            if item.get("type") == "image" and item.get("path")
        }

        for path in self.cache_dir.iterdir():
            if path.is_file() and path.resolve() not in referenced:
                remove_file(path)

    def _prepend(self, item: dict[str, Any]) -> None:
        self.items.insert(0, item)
        self._enforce_limit(protected_id=item["id"])
        self.save()

    def _move_to_top(self, item: dict[str, Any]) -> dict[str, Any]:
        self.items.remove(item)
        item["created_at"] = utc_now_iso()
        self.items.insert(0, item)
        self.save()
        return item

    def _find_text_duplicate(self, value: str) -> dict[str, Any] | None:
        return next(
            (
                item for item in self.items
                if item.get("type") == "text" and item.get("content") == value
            ),
            None,
        )

    def _find_image_duplicate(
        self,
        image_path: str,
        fingerprint: str | None = None,
    ) -> dict[str, Any] | None:
        if fingerprint is not None:
            by_fingerprint = next(
                (
                    item for item in self.items
                    if item.get("type") == "image"
                    and item.get("fingerprint") == fingerprint
                ),
                None,
            )
            if by_fingerprint is not None:
                return by_fingerprint

        return next(
            (
                item for item in self.items
                if item.get("type") == "image" and item.get("path") == image_path
            ),
            None,
        )

    def _enforce_limit(self, protected_id: str | None = None) -> None:
        while len(self.items) > self.max_items:
            remove_index = self._oldest_unpinned_index(protected_id)
            if remove_index is None:
                break

            removed = self.items.pop(remove_index)
            self._delete_image_file(removed)

    def _oldest_unpinned_index(self, protected_id: str | None = None) -> int | None:
        for index in range(len(self.items) - 1, -1, -1):
            item = self.items[index]
            if item.get("id") == protected_id:
                continue
            if not item.get("pinned", False):
                return index
        return None

    def _delete_image_file(self, item: dict[str, Any]) -> None:
        if item.get("type") == "image" and item.get("path"):
            remove_file(item["path"])

    def _clear_cache_dir(self) -> None:
        ensure_dir(self.cache_dir)
        for path in self.cache_dir.iterdir():
            if path.is_file():
                remove_file(path)

    def _is_valid_item(self, item: dict[str, Any]) -> bool:
        item_type = item.get("type")
        if item_type not in SUPPORTED_TYPES:
            return False

        if not item.get("id") or not item.get("created_at"):
            return False

        if item_type == "text":
            content = item.get("content")
            return isinstance(content, str) and not self._is_image_reference_text(content)

        if item_type == "image":
            image_path = item.get("path")
            return isinstance(image_path, str) and Path(image_path).is_file()

        return False

    def _is_image_reference_text(self, value: str) -> bool:
        parsed = urlparse(value)
        if parsed.scheme == "file":
            suffix = Path(unquote(parsed.path)).suffix.casefold()
            return suffix in IMAGE_EXTENSIONS

        return Path(value).suffix.casefold() in IMAGE_EXTENSIONS
