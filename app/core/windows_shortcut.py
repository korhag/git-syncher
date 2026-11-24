"""Read and persist desktop shell links using the Windows Shell COM interfaces."""

from __future__ import annotations

import ctypes as ct
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID


class _GUID(ct.Structure):
    _fields_ = [("data1", ct.c_uint32), ("data2", ct.c_uint16),
                ("data3", ct.c_uint16), ("data4", ct.c_ubyte * 8)]

    @classmethod
    def parse(cls, guid):
        return cls.from_buffer_copy(UUID(guid).bytes_le)


class _PropertyKey(ct.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ct.c_uint32)]


class _Value(ct.Union):
    # The largest ordinary PROPVARIANT union members are counted pointer pairs.
    _fields_ = [("string", ct.c_wchar_p), ("storage", ct.c_void_p * 2)]


class _PropVariant(ct.Structure):
    _fields_ = [("type", ct.c_uint16), ("reserved", ct.c_uint16 * 3), ("value", _Value)]


_SHELL_LINK = _GUID.parse("00021401-0000-0000-c000-000000000046")
_I_SHELL_LINK_W = _GUID.parse("000214f9-0000-0000-c000-000000000046")
_I_PERSIST_FILE = _GUID.parse("0000010b-0000-0000-c000-000000000046")
_I_PROPERTY_STORE = _GUID.parse("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
_APP_ID = _PropertyKey(_GUID.parse("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), 5)
_PROGRAMS_FOLDER = _GUID.parse("a77f5d77-2e2b-44c3-a6a2-aba601054a51")
_VT_LPWSTR = 31


@dataclass(frozen=True)
class Link:
    target: Path
    working_directory: Path
    arguments: str
    icon: Path
    description: str
    app_id: str
    icon_index: int = 0


def _check(result: int) -> None:
    if result < 0:
        raise ct.WinError(result)


@contextmanager
def _apartment():
    ole = ct.windll.ole32
    result = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    # An embedding host may have already initialized this thread as MTA.
    if result != -2147417850:  # RPC_E_CHANGED_MODE
        _check(result)
    try:
        yield
    finally:
        if result >= 0:
            ole.CoUninitialize()


class _Interface:
    """An owned COM pointer. Slots follow the interfaces in shobjidl_core.h."""

    def __init__(self):
        self.ptr = ct.c_void_p()

    def call(self, slot, types, *args):
        table = ct.cast(self.ptr, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        method = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *types)(table[slot])
        _check(method(self.ptr, *args))

    def query(self, iid):
        result = _Interface()
        self.call(0, [ct.POINTER(_GUID), ct.POINTER(ct.c_void_p)],
                  ct.byref(iid), ct.byref(result.ptr))  # QueryInterface
        return result

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.call(2, [])  # IUnknown::Release


def programsFolder() -> Path:
    """Honor redirected or customized per-user Start Menu Programs folders."""
    path = ct.c_wchar_p()
    with _apartment():
        _check(ct.windll.shell32.SHGetKnownFolderPath(
            ct.byref(_PROGRAMS_FOLDER), 0, None, ct.byref(path)
        ))
        try:
            return Path(path.value)
        finally:
            ct.windll.ole32.CoTaskMemFree(path)


def _shell_link() -> _Interface:
    link = _Interface()
    _check(ct.windll.ole32.CoCreateInstance(
        ct.byref(_SHELL_LINK), None, 1, ct.byref(_I_SHELL_LINK_W), ct.byref(link.ptr)
    ))
    return link


def _get_text(link, slot, *extra):
    buffer = ct.create_unicode_buffer(32768)
    types = [ct.c_wchar_p, ct.c_int] + [typ for typ, arg in extra]
    link.call(slot, types, buffer, len(buffer), *(arg for typ, arg in extra))
    return buffer.value


def readLink(path: Path) -> Link:
    with _apartment(), _shell_link() as link, link.query(_I_PERSIST_FILE) as file:
        file.call(5, [ct.c_wchar_p, ct.c_uint32], str(path), 0)  # Load, STGM_READ
        with link.query(_I_PROPERTY_STORE) as properties:
            value = _PropVariant()
            properties.call(5, [ct.POINTER(_PropertyKey), ct.POINTER(_PropVariant)],
                            ct.byref(_APP_ID), ct.byref(value))  # GetValue
            try:
                app_id = value.value.string if value.type == _VT_LPWSTR else ""
            finally:
                ct.windll.ole32.PropVariantClear(ct.byref(value))
        index = ct.c_int()
        return Link(
            target=Path(_get_text(link, 3, (ct.c_void_p, None), (ct.c_uint32, 4))),
            working_directory=Path(_get_text(link, 8)),
            arguments=_get_text(link, 10),
            icon=Path(_get_text(link, 16, (ct.POINTER(ct.c_int), ct.byref(index)))),
            description=_get_text(link, 6),
            app_id=app_id,
            icon_index=index.value,
        )


def _save_link(path: Path, expected: Link) -> None:
    with _apartment(), _shell_link() as link:
        link.call(20, [ct.c_wchar_p], str(expected.target))  # SetPath
        link.call(9, [ct.c_wchar_p], str(expected.working_directory))
        link.call(11, [ct.c_wchar_p], expected.arguments)
        link.call(7, [ct.c_wchar_p], expected.description)
        link.call(17, [ct.c_wchar_p, ct.c_int], str(expected.icon), expected.icon_index)
        with link.query(_I_PROPERTY_STORE) as properties:
            value = _PropVariant()
            value.type = _VT_LPWSTR
            value.value.string = expected.app_id  # Python owns this input string.
            properties.call(6, [ct.POINTER(_PropertyKey), ct.POINTER(_PropVariant)],
                            ct.byref(_APP_ID), ct.byref(value))  # SetValue
            properties.call(7, [])  # Commit
        with link.query(_I_PERSIST_FILE) as file:
            file.call(6, [ct.c_wchar_p, ct.c_int], str(path), True)  # Save


def ensureLink(path: Path, expected: Link) -> None:
    exists = path.exists()
    if exists:
        try:
            if readLink(path) == expected:
                return
        except OSError:
            # A corrupt or incomplete shell link can be replaced in place.
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".lnk", delete=False) as temp:
        staged = Path(temp.name)
    try:
        _save_link(staged, expected)
        if readLink(staged) != expected:
            raise OSError("Windows did not save the expected shortcut target or identity.")
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)
    # SHCNE_UPDATEITEM or SHCNE_CREATE, SHCNF_PATHW.
    ct.windll.shell32.SHChangeNotify(0x2000 if exists else 2, 5, str(path), None)
