from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def remove_file(path: str | Path) -> None:
    target = Path(path)
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
