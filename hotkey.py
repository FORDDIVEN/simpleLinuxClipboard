from __future__ import annotations

import ctypes
import threading
from typing import Callable


KEY_PRESS = 2
GRAB_MODE_ASYNC = 1
SHIFT_MASK = 1
LOCK_MASK = 1 << 1
CONTROL_MASK = 1 << 2
MOD1_MASK = 1 << 3
MOD2_MASK = 1 << 4
MOD4_MASK = 1 << 6

MODIFIER_ALIASES = {
    "ctrl": CONTROL_MASK,
    "control": CONTROL_MASK,
    "alt": MOD1_MASK,
    "shift": SHIFT_MASK,
    "meta": MOD4_MASK,
    "super": MOD4_MASK,
    "win": MOD4_MASK,
    "windows": MOD4_MASK,
}


class XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xkey", XKeyEvent),
        ("pad", ctypes.c_long * 24),
    ]


class GlobalHotkey:
    def __init__(self, callback: Callable[[], None], shortcut: str = "Meta+V") -> None:
        self.callback = callback
        self._display: ctypes.c_void_p | None = None
        self._keycode = 0
        self._modifiers = 0
        self._shortcut = shortcut
        self._registered = False
        self._thread: threading.Thread | None = None
        self._x11 = self._load_x11()

    def start(self) -> bool:
        if self._x11 is None:
            return False

        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            return False

        if not self.update_shortcut(self._shortcut):
            return False

        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()
        return True

    def update_shortcut(self, shortcut: str) -> bool:
        if not self._display:
            self._shortcut = shortcut
            return True

        parsed = parse_shortcut(shortcut)
        if parsed is None:
            return False

        modifiers, key_name = parsed
        keysym = self._x11.XStringToKeysym(key_name.encode("ascii"))
        keycode = self._x11.XKeysymToKeycode(self._display, keysym)
        if not keycode:
            return False

        root = self._x11.XDefaultRootWindow(self._display)
        self.unregister()

        self._keycode = keycode
        self._modifiers = modifiers
        self._shortcut = shortcut
        for modifier in self._modifier_variants(self._modifiers):
            self._x11.XGrabKey(
                self._display,
                self._keycode,
                modifier,
                root,
                True,
                GRAB_MODE_ASYNC,
                GRAB_MODE_ASYNC,
            )

        self._registered = True
        self._x11.XFlush(self._display)
        return True

    def unregister(self) -> None:
        if not self._display or not self._registered:
            return

        root = self._x11.XDefaultRootWindow(self._display)
        if self._keycode:
            for modifier in self._modifier_variants(self._modifiers):
                self._x11.XUngrabKey(self._display, self._keycode, modifier, root)
            self._x11.XFlush(self._display)

        self._keycode = 0
        self._modifiers = 0
        self._registered = False

    def close(self) -> None:
        self.unregister()

    def _event_loop(self) -> None:
        event = XEvent()
        while self._display:
            self._x11.XNextEvent(self._display, ctypes.byref(event))
            if not self._registered:
                continue
            if event.type != KEY_PRESS:
                continue
            if event.xkey.keycode != self._keycode:
                continue
            clean_state = event.xkey.state & ~(LOCK_MASK | MOD2_MASK)
            if clean_state != self._modifiers:
                continue

            self.callback()

    def _modifier_variants(self, modifiers: int) -> tuple[int, ...]:
        return (
            modifiers,
            modifiers | LOCK_MASK,
            modifiers | MOD2_MASK,
            modifiers | LOCK_MASK | MOD2_MASK,
        )

    def _load_x11(self):
        try:
            x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
        except OSError:
            return None

        try:
            x11.XInitThreads()
        except AttributeError:
            pass

        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        x11.XStringToKeysym.restype = ctypes.c_ulong
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XKeysymToKeycode.restype = ctypes.c_uint
        x11.XGrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_ulong,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_int,
        ]
        x11.XGrabKey.restype = ctypes.c_int
        x11.XUngrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_ulong,
        ]
        x11.XUngrabKey.restype = ctypes.c_int
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XFlush.restype = ctypes.c_int
        x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
        x11.XNextEvent.restype = ctypes.c_int
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.restype = ctypes.c_int
        return x11


def parse_shortcut(shortcut: str) -> tuple[int, str] | None:
    parts = [part.strip() for part in shortcut.split(",")[0].split("+") if part.strip()]
    if not parts:
        return None

    modifiers = 0
    key = ""
    for part in parts:
        value = part.casefold()
        if value in MODIFIER_ALIASES:
            modifiers |= MODIFIER_ALIASES[value]
        else:
            key = normalize_key_name(part)

    if not key:
        return None

    return modifiers, key


def normalize_key_name(key: str) -> str:
    aliases = {
        " ": "space",
        "space": "space",
        "return": "Return",
        "enter": "Return",
        "esc": "Escape",
        "escape": "Escape",
    }
    value = key.strip()
    alias = aliases.get(value.casefold())
    if alias is not None:
        return alias
    if len(value) == 1:
        return value.upper()
    return value
