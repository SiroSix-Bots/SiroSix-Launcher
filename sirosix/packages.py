"""Geprüfte Produktdownloads und atomare Installation in Versionsordnern."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

MAX_DOWNLOAD = 200 * 1024 * 1024
MAX_EXTRACTED = 512 * 1024 * 1024
EXECUTABLES = {"verzum": "SiroSix-Verzum-Bot.exe", "rubinum": "SiroSix-Rubinum-Bot.exe"}
VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:-[A-Za-z0-9.]+)?\Z")


class PackageError(Exception):
    pass


def digest_file(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def safe_members(bundle):
    total = 0
    names = set()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}
    for item in bundle.infolist():
        if "\\" in item.orig_filename or "\x00" in item.orig_filename:
            raise PackageError("Das Paket enthält einen unzulässigen Dateipfad.")
        path = PurePosixPath(item.filename)
        parts = item.filename.rstrip("/").split("/")
        kind = stat.S_IFMT(item.external_attr >> 16)
        if (path.is_absolute() or not parts or any(p in ("", ".", "..") for p in parts)
                or any(any(c in p for c in '\\:<>"|?*') or p.endswith((" ", "."))
                       or p.split(".")[0].upper() in reserved for p in parts)
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise PackageError("Das Paket enthält einen unzulässigen Dateipfad.")
        normalized = "/".join(parts).casefold()
        if normalized in names:
            raise PackageError("Das Paket enthält doppelte Dateinamen.")
        names.add(normalized)
        total += item.file_size
        if total > MAX_EXTRACTED or len(names) > 10000:
            raise PackageError("Das entpackte Paket ist zu groß.")
    return bundle.infolist()


def install_archive(archive, root, product, version, expected_sha):
    if product not in EXECUTABLES or not VERSION_RE.fullmatch(version):
        raise PackageError("Unbekanntes Produkt oder ungültige Version.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha or "") or digest_file(archive) != expected_sha:
        raise PackageError("Die SHA-256-Prüfsumme des Downloads stimmt nicht.")
    parent = Path(root) / product
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / version
    if target.exists():
        receipt = target / ".installed.json"
        try:
            current = json.loads(receipt.read_text("utf-8"))
            if current["sha256"] == expected_sha:
                return checked_executable(target, product)
        except (OSError, ValueError, KeyError):
            pass
        raise PackageError("Diese Version ist bereits mit anderem oder beschädigtem Inhalt installiert.")
    stage = Path(tempfile.mkdtemp(prefix=".installation-", dir=parent))
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = safe_members(bundle)
            manifest_entry = next((x for x in members if x.filename == "sirosix-product.json"), None)
            if manifest_entry is None or manifest_entry.file_size > 16384:
                raise PackageError("Das Produktmanifest fehlt oder ist zu groß.")
            manifest = json.loads(bundle.read(manifest_entry))
            expected = {"schema": 1, "product": product, "version": version, "executable": EXECUTABLES[product]}
            if any(manifest.get(k) != v for k, v in expected.items()):
                raise PackageError("Das Paket gehört nicht zum gewählten Produkt oder zur Version.")
            bundle.extractall(stage, members)
        exe = stage / EXECUTABLES[product]
        if not exe.is_file():
            raise PackageError("Das Paket enthält kein gültiges Windows-Programm.")
        with exe.open("rb") as binary:
            if binary.read(2) != b"MZ":
                raise PackageError("Das Paket enthält kein gültiges Windows-Programm.")
        hashes = {str(p.relative_to(stage)).replace("\\", "/"): digest_file(p)
                  for p in stage.rglob("*") if p.is_file()}
        (stage / ".installed.json").write_text(json.dumps({"sha256": expected_sha, "files": hashes}), "utf-8")
        os.replace(stage, target)
        carry_user_files(parent, target)
        prune_old_versions(parent, target)
        return target / EXECUTABLES[product]
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        raise PackageError("Das Produktpaket konnte nicht sicher installiert werden.") from e
    finally:
        if stage.exists():
            shutil.rmtree(stage)


USER_FILES = ("config.json",)
KEEP_VERSIONS = 2


def _version_dirs(parent, exclude):
    dirs = [d for d in Path(parent).iterdir()
            if d.is_dir() and d != exclude and VERSION_RE.fullmatch(d.name)]
    return sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)


def carry_user_files(parent, target):
    """Einstellungen aus der zuletzt genutzten Version in die neue übernehmen."""
    try:
        for name in USER_FILES:
            if (target / name).exists():
                continue
            for old in _version_dirs(parent, target):
                src = old / name
                if src.is_file() and src.stat().st_size <= 1024 * 1024:
                    shutil.copy2(src, target / name)
                    break
    except OSError:
        pass


def prune_old_versions(parent, target):
    """Nur die neue und die vorherige Version behalten, ältere entfernen."""
    try:
        for old in _version_dirs(parent, target)[KEEP_VERSIONS - 1:]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass


def checked_executable(directory, product):
    directory = Path(directory)
    try:
        receipt = json.loads((directory / ".installed.json").read_text("utf-8"))
        if not isinstance(receipt.get("files"), dict) or not {EXECUTABLES[product], "sirosix-product.json"} <= receipt["files"].keys():
            raise PackageError("Der Installationsnachweis ist unvollständig. Bitte die Version neu installieren.")
        for name, expected in receipt["files"].items():
            path = directory / name
            if not path.resolve().is_relative_to(directory.resolve()) or digest_file(path) != expected:
                raise PackageError("Installierte Dateien wurden verändert. Bitte die Version neu installieren.")
        return directory / EXECUTABLES[product]
    except (KeyError, OSError, ValueError):
        raise PackageError("Die installierten Dateien konnten nicht geprüft werden.") from None


def download_product(api, root, product, progress=lambda done, total: None,
                     phase=lambda name, detail: None):
    phase("updates", "Aktuelle Produktversion wird beim Server abgefragt.")
    info = api.download_info(product)
    version, sha = info.get("version"), info.get("sha256")
    if (product not in EXECUTABLES or not isinstance(version, str) or not VERSION_RE.fullmatch(version)
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)):
        raise PackageError("Die Produktinformationen sind ungültig.")
    if not isinstance(info.get("groesse"), int) or not 0 < info["groesse"] <= MAX_DOWNLOAD:
        raise PackageError("Die angegebene Downloadgröße ist ungültig.")
    phase("files", "Installierte Dateien und benötigte Programmdateien werden geprüft.")
    installed = Path(root) / product / version
    if installed.exists():
        try:
            receipt = json.loads((installed / ".installed.json").read_text("utf-8"))
            if receipt["sha256"] != sha:
                raise PackageError("Die installierte Version stimmt nicht mit dem Server überein.")
            exe = checked_executable(installed, product)
            phase("verify", "Version " + version + " ist vollständig und geprüft. Kein Download nötig.")
            return exe
        except (KeyError, OSError, ValueError):
            raise PackageError("Die vorhandene Installation ist beschädigt. Bitte den Support kontaktieren.") from None
    path = api.file_path(info["url"])
    parts = info.get("teile", 0)
    if not isinstance(parts, int) or not 0 <= parts <= 400:
        raise PackageError("Die Produktinformationen sind ungültig.")
    Path(root).mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".download-", suffix=".zip", dir=root)
    try:
        phase("download", "Version " + version + " wird heruntergeladen.")
        with os.fdopen(fd, "wb") as target:
            done = 0
            if parts:
                # Große Pakete kommen Stück für Stück als Base64 (Server-Limit pro Anfrage).
                for nr in range(parts):
                    block = api.file_part(path, nr)
                    done += len(block)
                    if done > info["groesse"] or done > MAX_DOWNLOAD:
                        raise PackageError("Der Download ist größer als angekündigt.")
                    target.write(block)
                    progress(done, info["groesse"])
            else:
                with api.open(path) as response:
                    while block := response.read(256 * 1024):
                        done += len(block)
                        if done > info["groesse"] or done > MAX_DOWNLOAD:
                            raise PackageError("Der Download ist größer als angekündigt.")
                        target.write(block)
                        progress(done, info["groesse"])
        if done != info["groesse"]:
            raise PackageError("Der Download ist unvollständig.")
        phase("verify", "Prüfsumme, Paketinhalt und Installation werden geprüft.")
        return install_archive(filename, root, product, info["version"], info["sha256"])
    finally:
        Path(filename).unlink(missing_ok=True)
