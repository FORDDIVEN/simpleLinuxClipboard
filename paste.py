from __future__ import annotations

import ctypes


PASTE_DELAY_MS = 120


def paste_clipboard() -> bool:
    x11, xtst = _load_x11_and_xtst()
    if x11 is None or xtst is None:
        return False

    display = x11.XOpenDisplay(None)
    if not display:
        return False

    try:
        control_keycode = _keycode_for(x11, display, b"Control_L")
        v_keycode = _keycode_for(x11, display, b"V")
        if not control_keycode or not v_keycode:
            return False

        for keycode, pressed in (
            (control_keycode, True),
            (v_keycode, True),
            (v_keycode, False),
            (control_keycode, False),
        ):
            xtst.XTestFakeKeyEvent(display, keycode, pressed, 0)

        x11.XFlush(display)
        return True
    finally:
        x11.XCloseDisplay(display)


def _keycode_for(x11, display: ctypes.c_void_p, key_name: bytes) -> int:
    keysym = x11.XStringToKeysym(key_name)
    if not keysym:
        return 0
    return int(x11.XKeysymToKeycode(display, keysym))


def _load_x11_and_xtst():
    try:
        x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
        xtst = ctypes.cdll.LoadLibrary("libXtst.so.6")
    except OSError:
        return None, None

    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_uint
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XFlush.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int

    xtst.XTestFakeKeyEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_bool,
        ctypes.c_ulong,
    ]
    xtst.XTestFakeKeyEvent.restype = ctypes.c_int

    return x11, xtst
