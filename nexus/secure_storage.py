from __future__ import annotations

import base64
import ctypes
import sys


def _encrypt(value: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI unavailable")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    data = value.encode("utf-8")
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    src = Blob(len(data), buf)
    dst = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)):
        raise OSError("CryptProtectData failed")
    try:
        return base64.b64encode(ctypes.string_at(dst.pbData, dst.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(dst.pbData)


def _decrypt(value: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI unavailable")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value)
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src = Blob(len(raw), buf)
    dst = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(dst.pbData)


def save_secret(settings, key: str, value: str) -> None:
    if sys.platform == "win32" and value:
        try:
            settings.setValue("secure/" + key, _encrypt(value))
            settings.remove("plain/" + key)
            settings.sync()
            return
        except Exception:
            pass
    settings.setValue("plain/" + key, value)
    settings.sync()


def load_secret(settings, key: str, default: str = "") -> str:
    if sys.platform == "win32":
        encoded = settings.value("secure/" + key, "")
        if encoded:
            try:
                return _decrypt(str(encoded))
            except Exception:
                pass
    return str(settings.value("plain/" + key, default) or default)


def clear_secret(settings, key: str) -> None:
    settings.remove("secure/" + key)
    settings.remove("plain/" + key)
    settings.sync()
