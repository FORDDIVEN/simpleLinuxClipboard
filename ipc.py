from __future__ import annotations

import os
import socket
import tempfile
import threading
from pathlib import Path
from typing import Callable

from config import APP_NAME


SOCKET_PATH = Path(tempfile.gettempdir()) / f"{APP_NAME}-{os.getuid()}.sock"


def send_command(command: str, timeout: float = 0.15) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(SOCKET_PATH))
            client.sendall(command.encode("utf-8"))
        return True
    except OSError:
        return False


class CommandServer:
    def __init__(self, handler: Callable[[str], None]) -> None:
        self.handler = handler
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._thread: threading.Thread | None = None

        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        self._server.bind(str(SOCKET_PATH))
        self._server.listen(8)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        try:
            self._server.close()
        finally:
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return

            with connection:
                command = connection.recv(128).decode("utf-8").strip()
                if command:
                    self.handler(command)
