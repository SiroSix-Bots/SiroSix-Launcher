"""Benutzergebundene Windows-Verschlüsselung und ausschließlich gehashte PC-Kennung."""
import ctypes
import hashlib
import json
import os
from pathlib import Path


def data_dir():
    path = Path(os.environ["LOCALAPPDATA"]) / "SiroSix"
    path.mkdir(parents=True, exist_ok=True)
    return path


class SecureStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "sitzung.dpapi"

    def save(self, value):
        import win32crypt
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        protected = win32crypt.CryptProtectData(raw, "SiroSix", b"SiroSix-v1", None, None, 1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(protected)
        os.replace(tmp, self.path)

    def load(self):
        import win32crypt
        import pywintypes
        try:
            raw = win32crypt.CryptUnprotectData(self.path.read_bytes(), b"SiroSix-v1", None, None, 1)[1]
            result = json.loads(raw)
            return result if isinstance(result, dict) else None
        except (OSError, ValueError, pywintypes.error):
            return None

    def clear(self):
        self.path.unlink(missing_ok=True)


def hardware_id():
    import winreg
    import pythoncom
    import win32com.client
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0].strip().upper()
    volume = ctypes.c_uint32()
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    if not machine_guid or not ctypes.windll.kernel32.GetVolumeInformationW(
        drive, None, 0, ctypes.byref(volume), None, None, None, 0
    ):
        raise RuntimeError("Die PC-Kennung konnte nicht gelesen werden.")
    board = ""
    service = None
    pythoncom.CoInitialize()
    try:
        service = win32com.client.GetObject(r"winmgmts:root\cimv2")
        serials = [str(x.SerialNumber or "").strip().upper() for x in
                   service.ExecQuery("SELECT SerialNumber FROM Win32_BaseBoard")]
        invalid = {"", "DEFAULT STRING", "TO BE FILLED BY O.E.M.", "NONE", "UNKNOWN"}
        board = "|".join(sorted(s for s in serials if s not in invalid))
    except Exception:
        pass  # MachineGuid und Laufwerk bleiben verfügbar, auch wenn WMI nicht antwortet.
    finally:
        service = None
        pythoncom.CoUninitialize()
    raw = json.dumps([board, machine_guid, f"{volume.value:08X}"], separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def short_hwid(value):
    return value[:4].upper() + "..." + value[-4:].upper()
