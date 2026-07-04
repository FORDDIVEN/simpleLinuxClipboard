import sys

from ipc import CommandServer, send_command


def main() -> None:
    args = set(sys.argv[1:])
    start_visible = "--background" not in args
    force_global_hotkey = "--global-hotkey" in args
    disable_global_hotkey = "--no-global-hotkey" in args
    command = "toggle" if "--toggle" in args else "show"

    if args & {"--toggle", "--show", "--hide", "--quit"}:
        if "--hide" in args:
            command = "hide"
            start_visible = False
        elif "--quit" in args:
            command = "quit"
            start_visible = False

        if send_command(command):
            return
    elif send_command("noop" if "--background" in args else "show"):
        return

    run_app(start_visible, force_global_hotkey, disable_global_hotkey)


def run_app(
    start_visible: bool,
    force_global_hotkey: bool = False,
    disable_global_hotkey: bool = False,
) -> None:
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from clipboard import ClipboardWatcher
    from history import HistoryStore
    from settings import load_settings, save_settings
    from ui import ClipboardWindow

    class CommandBridge(QObject):
        command_received = Signal(str)

    class TrayController(QObject):
        def __init__(self, app: QApplication, window: ClipboardWindow) -> None:
            super().__init__()
            self.app = app
            self.window = window
            self.tray = QSystemTrayIcon(make_tray_icon(), self)
            self.tray.setToolTip("Portapapeles")
            self.tray.activated.connect(self._on_activated)
            self.tray.setContextMenu(self._build_menu())
            self.tray.show()

        def _build_menu(self) -> QMenu:
            menu = QMenu()

            toggle_action = QAction("Mostrar/Ocultar", self)
            toggle_action.triggered.connect(self.window.toggle)

            quit_action = QAction("Salir", self)
            quit_action.triggered.connect(self.app.quit)

            menu.addAction(toggle_action)
            menu.addSeparator()
            menu.addAction(quit_action)
            return menu

        def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason in {
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            }:
                self.window.toggle()

    def run_command(command: str) -> None:
        if command == "toggle":
            window.toggle()
        elif command == "show":
            if not window.isVisible():
                window.toggle()
        elif command == "hide":
            window.hide()
        elif command == "quit":
            app.quit()
        elif command == "noop":
            return

    def make_tray_icon() -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(
                QPen(QColor("#f3f4f6"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.setBrush(QColor("#2563eb"))
            painter.drawRoundedRect(7, 8, 18, 19, 4, 4)
            painter.setBrush(QColor("#f3f4f6"))
            painter.drawRoundedRect(11, 5, 10, 6, 2, 2)
            painter.setPen(
                QPen(QColor("#dbeafe"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(11, 15, 21, 15)
            painter.drawLine(11, 20, 18, 20)
        finally:
            painter.end()

        return QIcon(pixmap)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = load_settings()
    hotkey_enabled = bool(settings.get("global_hotkey_enabled", False))
    if force_global_hotkey:
        hotkey_enabled = True
    if disable_global_hotkey:
        hotkey_enabled = False

    store = HistoryStore()
    watcher = ClipboardWatcher(app.clipboard(), store)
    window = ClipboardWindow(
        store,
        app.clipboard(),
        before_clipboard_write=watcher.ignore_next_change,
        hotkey_enabled=hotkey_enabled,
        hotkey=str(settings.get("global_hotkey", "Meta+V")),
    )
    watcher.item_added.connect(lambda item: window.refresh())

    bridge = CommandBridge()
    bridge.command_received.connect(run_command)
    command_server = CommandServer(bridge.command_received.emit)
    command_server.start()
    app.aboutToQuit.connect(command_server.close)
    hotkey = None
    if hotkey_enabled:
        from hotkey import GlobalHotkey

        hotkey = GlobalHotkey(
            lambda: bridge.command_received.emit("toggle"),
            str(settings.get("global_hotkey", "Meta+V")),
        )
        hotkey.start()

    def apply_hotkey_settings(enabled: bool, shortcut: str) -> None:
        nonlocal hotkey
        settings["global_hotkey_enabled"] = enabled
        settings["global_hotkey"] = shortcut
        save_settings(settings)

        if not enabled:
            if hotkey is not None:
                hotkey.unregister()
            return

        if hotkey is None:
            from hotkey import GlobalHotkey

            hotkey = GlobalHotkey(lambda: bridge.command_received.emit("toggle"), shortcut)
            hotkey.start()
            return

        hotkey.update_shortcut(shortcut)

    window.hotkey_settings_changed.connect(apply_hotkey_settings)
    app.aboutToQuit.connect(lambda: hotkey.close() if hotkey is not None else None)

    tray = TrayController(app, window)

    print(f"Clipboard history loaded: {len(store.items)} item(s)")
    if start_visible:
        window.toggle()

    _keep_alive = (watcher, command_server, bridge, hotkey, tray)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
