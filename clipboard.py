from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QClipboard, QImage

from config import CACHE_DIR, IMAGE_EXTENSIONS
from history import HistoryStore
from utils import ensure_dir, file_sha256, new_id


class ClipboardWatcher(QObject):
    item_added = Signal(dict)

    def __init__(
        self,
        clipboard: QClipboard,
        history: HistoryStore,
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        super().__init__()
        self.clipboard = clipboard
        self.history = history
        self.cache_dir = cache_dir
        self._last_signature: tuple[Any, ...] | None = None
        self._ignore_next_change = False

        ensure_dir(self.cache_dir)
        self.clipboard.dataChanged.connect(self.handle_change)

    def ignore_next_change(self) -> None:
        self._ignore_next_change = True

    def handle_change(self) -> None:
        if self._ignore_next_change:
            self._ignore_next_change = False
            return

        mime_data = self.clipboard.mimeData()

        if mime_data.hasImage():
            image = self.clipboard.image()
            self._add_image(image)
            return

        if mime_data.hasUrls():
            for url in mime_data.urls():
                if self._add_image_url(url):
                    return

        if mime_data.hasText():
            text = mime_data.text().strip()
            if self._looks_like_image_reference(text):
                self._add_image_reference(text)
                return

            self._add_text(text)

    def _add_text(self, text: str) -> None:
        signature = ("text", text)
        if self._is_duplicate(signature):
            return

        item = self.history.add_text(text)
        if item is not None:
            self._last_signature = signature
            self.item_added.emit(item)

    def _add_image(self, image: QImage) -> None:
        if image.isNull():
            return

        signature = ("image", image.width(), image.height(), image.cacheKey())
        if self._is_duplicate(signature):
            return

        path = self.cache_dir / f"{new_id()}.png"
        if not image.save(str(path), "PNG"):
            return

        item = self.history.add_image(path, fingerprint=file_sha256(path))
        self._last_signature = signature
        self.item_added.emit(item)

    def _add_image_url(self, url: QUrl) -> bool:
        if not url.isLocalFile():
            return False

        return self._add_image_path(Path(url.toLocalFile()))

    def _add_image_reference(self, value: str) -> bool:
        url = QUrl(value)
        if url.isLocalFile():
            return self._add_image_url(url)

        return self._add_image_path(Path(value).expanduser())

    def _add_image_path(self, path: Path) -> bool:
        if path.suffix.casefold() not in IMAGE_EXTENSIONS:
            return False

        image = QImage(str(path))
        if image.isNull():
            return False

        self._add_image(image)
        return True

    def _looks_like_image_reference(self, value: str) -> bool:
        if not value:
            return False

        url = QUrl(value)
        if url.isLocalFile():
            return Path(url.toLocalFile()).suffix.casefold() in IMAGE_EXTENSIONS

        return Path(value).suffix.casefold() in IMAGE_EXTENSIONS

    def _is_duplicate(self, signature: tuple[Any, ...]) -> bool:
        return signature == self._last_signature
