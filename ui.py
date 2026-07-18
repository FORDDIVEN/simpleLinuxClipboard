from __future__ import annotations

import math
from getpass import getuser
from pathlib import Path
from string import Template
from typing import Any, Callable

from PySide6.QtCore import QEvent, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QClipboard,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from history import HistoryStore
from paste import PASTE_DELAY_MS, paste_clipboard


class ClipboardWindow(QWidget):
    hotkey_settings_changed = Signal(bool, str)

    def __init__(
        self,
        history: HistoryStore,
        clipboard: QClipboard,
        before_clipboard_write: Callable[[], None] | None = None,
        hotkey_enabled: bool = True,
        hotkey: str = "Meta+V",
    ) -> None:
        super().__init__()
        self.history = history
        self.clipboard = clipboard
        self.before_clipboard_write = before_clipboard_write
        self.hotkey_enabled = hotkey_enabled
        self.hotkey = hotkey
        self.search_box = QLineEdit()
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.list_layout = QVBoxLayout()
        self.item_widgets: list[HistoryItemWidget] = []
        self.scroll_area: QScrollArea | None = None
        self.selected_index = -1
        self.current_filter = "all"
        self._settings_open = False
        self._suppress_auto_hide = False

        self.setObjectName("ClipboardWindow")
        self.setWindowTitle("Clipboard")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(360, 480)

        self._build_ui()
        self._apply_styles()
        self._setup_shortcuts()
        self.refresh()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return

        self.selected_index = 0
        self.refresh(auto_scroll=False)
        self._suppress_auto_hide = True
        self.show()
        self._move_to_bottom_right()
        self.raise_()
        self.activateWindow()
        self.search_box.setFocus()
        self._scroll_to_top()
        QTimer.singleShot(0, self._scroll_to_top)
        QTimer.singleShot(250, self._allow_auto_hide)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._move_to_bottom_right()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        if (
            event.type() == QEvent.Type.ActivationChange
            and not self.isActiveWindow()
            and not self._settings_open
            and not self._suppress_auto_hide
        ):
            self.hide()
        super().changeEvent(event)

    def refresh(self, auto_scroll: bool = True) -> None:
        previous_index = self.selected_index
        self._clear_items()
        self.item_widgets = []
        items = self._filtered_items()

        if not items:
            self.list_layout.addStretch(1)
            empty_label = QLabel("Sin elementos")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setObjectName("EmptyLabel")
            self.list_layout.addWidget(empty_label)
            self.list_layout.addStretch(1)
            return

        for item in items:
            widget = HistoryItemWidget(item, self)
            self.item_widgets.append(widget)
            self.list_layout.addWidget(widget)

        self.list_layout.addStretch(1)
        if self.item_widgets:
            self.set_selected_index(
                min(max(previous_index, 0), len(self.item_widgets) - 1),
                auto_scroll=auto_scroll,
            )
        else:
            self.selected_index = -1

    def copy_item(self, item: dict[str, Any]) -> None:
        if self.before_clipboard_write is not None:
            self.before_clipboard_write()

        if item.get("type") == "text":
            self.clipboard.setText(str(item.get("content", "")))
        elif item.get("type") == "image" and item.get("path"):
            image = QImage(str(item["path"]))
            if not image.isNull():
                self.clipboard.setImage(image)

        self.hide()
        QTimer.singleShot(PASTE_DELAY_MS, paste_clipboard)

    def toggle_pin(self, item: dict[str, Any]) -> None:
        scroll_value = self._scroll_value()
        self.history.pin(str(item["id"]), not item.get("pinned", False))
        self.refresh(auto_scroll=False)
        self._restore_scroll_value(scroll_value)

    def delete_item(self, item: dict[str, Any]) -> None:
        self.history.delete(str(item["id"]))
        self.refresh()

    def clear_history(self) -> None:
        self.history.clear(include_pinned=False)
        self.refresh()

    def _allow_auto_hide(self) -> None:
        self._suppress_auto_hide = False

    def set_filter(self, item_type: str) -> None:
        self.current_filter = item_type
        self.selected_index = 0
        self.refresh()

    def _setup_shortcuts(self) -> None:
        close_shortcut = QShortcut(QKeySequence.StandardKey.Cancel, self)
        close_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        close_shortcut.activated.connect(self.hide)

        down_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Down), self)
        down_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        down_shortcut.activated.connect(lambda: self.move_selection(1))

        up_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Up), self)
        up_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        up_shortcut.activated.connect(lambda: self.move_selection(-1))

        return_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        return_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        return_shortcut.activated.connect(self.copy_selected_item)

        enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        enter_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        enter_shortcut.activated.connect(self.copy_selected_item)

    def move_selection(self, delta: int) -> None:
        if not self.item_widgets:
            return

        if self.selected_index < 0:
            self.set_selected_index(0)
            return

        next_index = max(0, min(self.selected_index + delta, len(self.item_widgets) - 1))
        self.set_selected_index(next_index)

    def set_selected_index(self, index: int, auto_scroll: bool = True) -> None:
        if not self.item_widgets:
            self.selected_index = -1
            return

        self.selected_index = max(0, min(index, len(self.item_widgets) - 1))
        for current_index, widget in enumerate(self.item_widgets):
            widget.set_selected(current_index == self.selected_index)

        if auto_scroll and self.scroll_area is not None:
            self.scroll_area.ensureWidgetVisible(self.item_widgets[self.selected_index])

    def _scroll_value(self) -> int:
        if self.scroll_area is None:
            return 0
        return self.scroll_area.verticalScrollBar().value()

    def _restore_scroll_value(self, value: int) -> None:
        if self.scroll_area is None:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(value)
        QTimer.singleShot(0, lambda: scrollbar.setValue(value))

    def _scroll_to_top(self) -> None:
        if self.scroll_area is None:
            return
        self.scroll_area.verticalScrollBar().setValue(0)

    def copy_selected_item(self) -> None:
        if 0 <= self.selected_index < len(self.item_widgets):
            self.copy_item(self.item_widgets[self.selected_index].item)

    def _build_ui(self) -> None:
        root = QFrame()
        root.setObjectName("Panel")

        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(f"Portapapeles de {display_user_name()}")
        title.setObjectName("Title")

        clear_button = QToolButton()
        clear_button.setText("Borrar")
        clear_button.setToolTip("Limpiar historial no fijado")
        clear_button.setObjectName("HeaderButton")
        clear_button.clicked.connect(self.clear_history)

        settings_button = QToolButton()
        settings_button.setIcon(make_action_icon("settings", self.icon_color()))
        settings_button.setIconSize(QSize(17, 17))
        settings_button.setToolTip("Configurar atajo de teclado")
        settings_button.setObjectName("HeaderButton")
        settings_button.clicked.connect(self.open_settings)

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(settings_button)
        header.addWidget(clear_button)

        self.search_box.setPlaceholderText("Buscar")
        self.search_box.textChanged.connect(self.refresh)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.addWidget(self._make_filter_button("Todo", "all", checked=True))
        filter_row.addWidget(self._make_filter_button("Texto", "text"))
        filter_row.addWidget(self._make_filter_button("Imágenes", "image"))

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        list_widget = QWidget()
        self.list_layout = QVBoxLayout(list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)

        self.scroll_area.setWidget(list_widget)

        layout.addLayout(header)
        layout.addWidget(self.search_box)
        layout.addLayout(filter_row)
        layout.addWidget(self.scroll_area)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

    def _clear_items(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def open_settings(self) -> None:
        dialog = HotkeySettingsDialog(self.hotkey_enabled, self.hotkey, self)
        dialog.adjustSize()
        dialog.move(
            self.x() + (self.width() - dialog.width()) // 2,
            self.y() + 68,
        )

        self._settings_open = True
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        finally:
            self._settings_open = False
            self.raise_()
            self.activateWindow()

        enabled, hotkey = dialog.values()
        self.hotkey_enabled = enabled
        self.hotkey = hotkey
        self.hotkey_settings_changed.emit(enabled, hotkey)

    def _filtered_items(self) -> list[dict[str, Any]]:
        query = self.search_box.text().strip().casefold()
        items = self.history.items

        if self.current_filter != "all":
            items = [item for item in items if item.get("type") == self.current_filter]

        if not query:
            return list(items)

        return [
            item for item in items
            if item.get("type") == "text"
            and query in str(item.get("content", "")).casefold()
        ]

    def _make_filter_button(
        self,
        text: str,
        item_type: str,
        checked: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setObjectName("FilterButton")
        button.clicked.connect(lambda: self.set_filter(item_type))
        self.filter_group.addButton(button)
        return button

    def _move_to_bottom_right(self) -> None:
        screen = self.screen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        x = geometry.right() - self.width() - 18
        y = geometry.bottom() - self.height() - 42
        self.move(max(geometry.left(), x), max(geometry.top(), y))

    def _apply_styles(self) -> None:
        if self._is_dark_theme():
            panel = "#17191d"
            input_bg = "#202226"
            item_bg = "#222936"
            item_hover = "#283246"
            item_selected = "#2b4f82"
            button_bg = "#2b3038"
            button_hover = "#374151"
            checked_bg = "#2563eb"
            border = "#333842"
            text = "#f3f4f6"
            muted = "#9ca3af"
            scrollbar = "#4b5563"
        else:
            panel = "#f7f8fa"
            input_bg = "#ffffff"
            item_bg = "#ffffff"
            item_hover = "#edf2ff"
            item_selected = "#dbeafe"
            button_bg = "#eef2f7"
            button_hover = "#e2e8f0"
            checked_bg = "#2563eb"
            border = "#cbd5e1"
            text = "#111827"
            muted = "#64748b"
            scrollbar = "#94a3b8"

        stylesheet = Template("""
            QWidget#ClipboardWindow {
                color: $text;
                font-family: Inter, Segoe UI, Ubuntu, sans-serif;
                font-size: 13px;
            }

            QFrame#Panel {
                background: $panel;
                border: 1px solid $border;
                border-radius: 14px;
            }

            QLabel#Title {
                font-size: 14px;
                font-weight: 700;
            }

            QLineEdit {
                background: $input_bg;
                border: 1px solid $border;
                border-radius: 7px;
                padding: 7px 9px;
                color: $text;
                selection-background-color: #2563eb;
            }

            QToolButton {
                background: $button_bg;
                border: 1px solid $border;
                border-radius: 6px;
                color: $text;
                padding: 5px 8px;
            }

            QToolButton:hover {
                background: $button_hover;
            }

            QToolButton#HeaderButton {
                min-height: 24px;
            }

            QToolButton#FilterButton {
                min-height: 28px;
                min-width: 96px;
            }

            QToolButton#FilterButton:checked {
                background: $checked_bg;
                border-color: $checked_bg;
                color: #ffffff;
            }

            QFrame#HistoryItem {
                background: $item_bg;
                border: 1px solid $border;
                border-radius: 7px;
            }

            QFrame#HistoryItem:hover {
                background: $item_hover;
            }

            QFrame#HistoryItem[selected="true"] {
                background: $item_selected;
                border-color: $checked_bg;
            }

            QLabel#PreviewText {
                color: $text;
                font-size: 13px;
            }

            QLabel#MetaText,
            QLabel#EmptyLabel {
                color: $muted;
                font-size: 12px;
            }

            QToolButton#ItemAction {
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                padding: 0;
            }

            QToolButton#ItemAction[pinned="true"] {
                background: $checked_bg;
                border-color: $checked_bg;
            }

            QScrollArea {
                background: transparent;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }

            QScrollBar::handle:vertical {
                background: $scrollbar;
                border-radius: 4px;
            }
        """).substitute(
            panel=panel,
            input_bg=input_bg,
            item_bg=item_bg,
            item_hover=item_hover,
            item_selected=item_selected,
            button_bg=button_bg,
            button_hover=button_hover,
            checked_bg=checked_bg,
            border=border,
            text=text,
            muted=muted,
            scrollbar=scrollbar,
        )
        self.setStyleSheet(stylesheet)

    def _is_dark_theme(self) -> bool:
        color = self.palette().window().color()
        return color.lightness() < 128

    def icon_color(self) -> QColor:
        return QColor("#f3f4f6" if self._is_dark_theme() else "#111827")


class HistoryItemWidget(QFrame):
    def __init__(self, item: dict[str, Any], window: ClipboardWindow) -> None:
        super().__init__()
        self.item = item
        self.window = window

        self.setObjectName("HistoryItem")
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self._build_ui()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.copy_item(self.item)
            return
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(8)

        preview = self._make_preview()
        content = QVBoxLayout()
        content.setSpacing(2)
        content.addWidget(preview)

        pin_button = QToolButton()
        pin_color = QColor("#ffffff") if self.item.get("pinned") else self.window.icon_color()
        pin_button.setIcon(
            make_action_icon(
                "pin-filled" if self.item.get("pinned") else "pin",
                pin_color,
            )
        )
        pin_button.setIconSize(QSize(15, 15))
        pin_button.setToolTip("Desfijar" if self.item.get("pinned") else "Fijar")
        pin_button.setObjectName("ItemAction")
        pin_button.setProperty("pinned", self.item.get("pinned", False))
        pin_button.clicked.connect(lambda: self.window.toggle_pin(self.item))

        delete_button = QToolButton()
        delete_button.setIcon(make_action_icon("delete", self.window.icon_color()))
        delete_button.setIconSize(QSize(15, 15))
        delete_button.setToolTip("Eliminar")
        delete_button.setObjectName("ItemAction")
        delete_button.clicked.connect(lambda: self.window.delete_item(self.item))

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(pin_button)
        actions.addWidget(delete_button)

        layout.addLayout(content, 1)
        layout.addLayout(actions)

    def _make_preview(self) -> QLabel:
        label = QLabel()
        label.setObjectName("PreviewText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        label.setMinimumHeight(24)
        label.setMaximumHeight(40)

        if self.item.get("type") == "image":
            pixmap = QPixmap(str(Path(str(self.item.get("path", "")))))
            if pixmap.isNull():
                label.setText("Imagen no disponible")
                return label

            label.setPixmap(
                pixmap.scaled(
                    74,
                    48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return label

        content = str(self.item.get("content", ""))
        if len(content) > 130:
            content = f"{content[:130]}..."
        label.setText(content)
        return label


def make_action_icon(name: str, color: QColor) -> QIcon:
    theme_names = {
        "copy": ["edit-copy", "edit-paste"],
        "delete": ["edit-delete", "user-trash", "edit-clear"],
        "pin": [],
        "pin-filled": [],
    }

    for theme_name in theme_names.get(name, []):
        icon = QIcon.fromTheme(theme_name)
        if not icon.isNull():
            return icon

    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        if name == "copy":
            painter.drawRoundedRect(5, 3, 9, 11, 2, 2)
            painter.drawRoundedRect(3, 6, 9, 10, 2, 2)
        elif name == "delete":
            painter.drawLine(5, 6, 13, 6)
            painter.drawLine(7, 6, 7, 14)
            painter.drawLine(11, 6, 11, 14)
            painter.drawRoundedRect(6, 6, 6, 9, 1, 1)
            painter.drawLine(7, 4, 11, 4)
        elif name == "settings":
            center = 9
            painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for step in range(8):
                angle = math.radians(step * 45)
                x = center + math.cos(angle) * 6.2
                y = center + math.sin(angle) * 6.2
                painter.save()
                painter.translate(x, y)
                painter.rotate(step * 45)
                painter.drawRoundedRect(-1, -2, 2, 4, 1, 1)
                painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawEllipse(4, 4, 10, 10)
            painter.drawEllipse(7, 7, 4, 4)
        else:
            if name == "pin-filled":
                painter.setBrush(color)
            painter.drawLine(7, 3, 13, 9)
            painter.drawLine(10, 6, 5, 11)
            painter.drawLine(4, 10, 8, 14)
            painter.drawLine(6, 12, 3, 15)
    finally:
        painter.end()
    return QIcon(pixmap)


def display_user_name() -> str:
    username = getuser().replace("_", " ").replace(".", " ").strip()
    return username.title() if username else "Usuario"


class HotkeySettingsDialog(QDialog):
    def __init__(self, enabled: bool, hotkey: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setModal(True)

        self.enabled_box = QCheckBox("Activar atajo")
        self.enabled_box.setChecked(enabled)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(hotkey))
        self.hotkey_edit.setEnabled(enabled)
        self.enabled_box.toggled.connect(self.hotkey_edit.setEnabled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.enabled_box.toggled.connect(self._sync_ok_state)
        self.hotkey_edit.keySequenceChanged.connect(self._sync_ok_state)

        form = QFormLayout(self)
        form.addRow(self.enabled_box)
        form.addRow("Atajo", self.hotkey_edit)
        form.addRow(buttons)
        self._sync_ok_state()

    def values(self) -> tuple[bool, str]:
        return self.enabled_box.isChecked(), self.hotkey_edit.keySequence().toString()

    def _sync_ok_state(self, *_args: object) -> None:
        if self.ok_button is None:
            return
        enabled = self.enabled_box.isChecked()
        has_shortcut = bool(self.hotkey_edit.keySequence().toString().strip())
        self.ok_button.setEnabled(not enabled or has_shortcut)
