"""Prüft externe Laufzeitvoraussetzungen ohne Installation oder Spiel-Eingaben."""
import os
from pathlib import Path
import re
import shutil
import subprocess


def check_requirements(product):
    if product != "verzum":
        return
    standard = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "dotnet/dotnet.exe"
    dotnet = str(standard) if standard.is_file() else shutil.which("dotnet")
    missing = "Für Verzum fehlt Microsoft .NET Runtime 10 (x64). Bitte installiere die .NET-10-Laufzeit von Microsoft und starte das Tool erneut."
    if not dotnet:
        raise RuntimeError(missing)
    try:
        result = subprocess.run([dotnet, "--list-runtimes"], capture_output=True, text=True,
                                timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Die .NET-Laufzeit konnte nicht geprüft werden. Bitte prüfe deine .NET-10-Installation und versuche es erneut.") from None
    if result.returncode != 0 or not re.search(r"(?m)^Microsoft\.NETCore\.App 10\.\d+\.\d+ \[", result.stdout):
        raise RuntimeError(missing)
