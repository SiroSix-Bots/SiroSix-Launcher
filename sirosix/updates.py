"""Manuelle Prüfung offizieller GitHub-Releases, Downloads nur mit veröffentlichtem Hash."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from . import VERSION

REPO = "SiroSix-Bots/SiroSix-Launcher"
ASSET_NAME = "SiroSix-Launcher.exe"
MAX_EXE = 100 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Ungültige Launcher-Version.")
    return tuple(int(p) for p in value.lstrip("v").split("."))


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != "https" or url.hostname not in ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
            raise RuntimeError("Der Update-Download wurde unerwartet weitergeleitet.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_release():
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "SiroSix-Launcher/" + VERSION, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(1024 * 1024)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise RuntimeError(f"Launcher-Updates konnten nicht geprüft werden (HTTP {e.code}).") from None
    release = json.loads(raw)
    if release.get("draft") or release.get("prerelease") or version_tuple(release["tag_name"]) <= version_tuple(VERSION):
        return None
    asset = next((a for a in release.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest") or ""):
        raise RuntimeError("Das Launcher-Update enthält keine verifizierbare Windows-Datei.")
    if type(asset.get("size")) is not int or not 0 < asset["size"] <= MAX_EXE:
        raise RuntimeError("Die Update-Datei ist zu groß.")
    url = urllib.parse.urlsplit(asset["browser_download_url"])
    expected = f"/{REPO}/releases/download/{release['tag_name']}/{ASSET_NAME}"
    if url.scheme != "https" or url.netloc != "github.com" or url.path != expected or url.query or url.fragment:
        raise RuntimeError("Die Update-Adresse ist ungültig.")
    return {"version": release["tag_name"], "url": asset["browser_download_url"], "sha256": asset["digest"][7:], "size": asset["size"]}


def download_release(release, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="launcher-update-", dir=root))
    target = stage / ASSET_NAME
    request = urllib.request.Request(release["url"], headers={"User-Agent": "SiroSix-Launcher/" + VERSION})
    try:
        digest = hashlib.sha256()
        count = 0
        opener = urllib.request.build_opener(ReleaseRedirect())
        with opener.open(request, timeout=30) as response, target.open("wb") as f:
            while block := response.read(256 * 1024):
                count += len(block)
                if count > MAX_EXE or count > release["size"]:
                    raise RuntimeError("Das Launcher-Update ist größer als angekündigt.")
                digest.update(block)
                f.write(block)
        if count != release["size"] or digest.hexdigest() != release["sha256"]:
            raise RuntimeError("Die Prüfsumme des Launcher-Updates stimmt nicht.")
        if target.read_bytes()[:2] != b"MZ":
            raise RuntimeError("Das Launcher-Update ist kein Windows-Programm.")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        stage.rmdir()
        raise


def apply_update(source, target, previous_pid, expected_sha):
    """Läuft aus der geprüften neuen EXE, nachdem der alte Launcher beendet wird."""
    import ctypes
    import shutil
    import subprocess
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or target.name != ASSET_NAME or source.name != ASSET_NAME or not target.is_file():
        raise RuntimeError("Ungültiges Launcher-Updateziel.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha:
        raise RuntimeError("Die Update-Datei wurde nach dem Download verändert.")
    # DLL- und GUI-Import prüfen, bevor die bestehende EXE ersetzt wird.
    import win32crypt
    import cryptography.hazmat.primitives.asymmetric.ed25519
    import sirosix.gui
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, int(previous_pid))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 30000) != 0:
                raise RuntimeError("Der bisherige Launcher wurde noch nicht beendet.")
        finally:
            kernel.CloseHandle(handle)
    backup = target.with_name("SiroSix-Launcher.previous.exe")
    temporary = target.with_name(".SiroSix-Launcher.update.tmp")
    old_moved = False
    try:
        shutil.copy2(source, temporary)
        os.replace(target, backup)
        old_moved = True
        os.replace(temporary, target)
        subprocess.Popen([str(target)], cwd=target.parent, close_fds=True)
    except Exception:
        if old_moved and backup.exists():
            os.replace(backup, target)
        raise
    finally:
        temporary.unlink(missing_ok=True)
