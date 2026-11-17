"""Prüfschritte vor jedem Start; unabhängig von der Oberfläche testbar."""
import subprocess
from .packages import download_product
from .windows import data_dir
from .prerequisites import check_requirements


class ElevatedProcess:
    def __init__(self, handle):
        self.handle = handle
        self.returncode = None

    def poll(self):
        if self.handle is not None:
            import win32process
            code = win32process.GetExitCodeProcess(self.handle)
            if code != 259:  # STILL_ACTIVE
                self.returncode = code
                self.handle.Close()
                self.handle = None
        return self.returncode


def launch_tool(args, cwd, close_fds=True):
    try:
        return subprocess.Popen(args, cwd=cwd, close_fds=close_fds)
    except OSError as error:
        if getattr(error, "winerror", None) != 740:
            raise
    # Windows zeigt die UAC-Abfrage selbst an; keine automatische Bestätigung.
    from win32com.shell import shell, shellcon
    try:
        result = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
                                     lpVerb="runas", lpFile=args[0], lpDirectory=str(cwd), nShow=1)
        return ElevatedProcess(result["hProcess"])
    except Exception as error:
        if getattr(error, "winerror", None) == 1223:
            raise RuntimeError("Der Start wurde in der Windows-Abfrage abgebrochen.") from None
        raise RuntimeError("Windows konnte das Tool nicht öffnen. Bitte erneut versuchen.") from error

STEPS = (
    ("license", "Lizenz & PC-Bindung"),
    ("updates", "Nach Aktualisierungen suchen"),
    ("files", "Installation & Voraussetzungen prüfen"),
    ("download", "Benötigte Dateien laden"),
    ("verify", "Dateien verifizieren"),
    ("launch", "Tool öffnen"),
)


def start_product(api, key, hwid, phase, progress, root=None, launch=None):
    phase("license", "Lizenz und Freigabe für diesen PC werden beim Server geprüft.")
    api.grant(key, hwid)
    def on_phase(name, detail):
        phase(name, detail)
        if name == "files":
            phase(name, "Installierte Dateien und Systemvoraussetzungen werden geprüft.")
            check_requirements(key)
    exe = download_product(api, root or data_dir() / "products", key, progress, on_phase)
    phase("launch", "Alle Prüfungen abgeschlossen. Das Tool wird geöffnet. Falls Windows nachfragt, bestätige den Start selbst.")
    # Sitzung ausschließlich über DPAPI, niemals über Prozessargumente.
    process = (launch or launch_tool)([str(exe)], cwd=exe.parent, close_fds=True)
    return process
