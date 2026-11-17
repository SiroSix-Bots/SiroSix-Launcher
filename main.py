def _protokoll(text):
    """Start- und Fehlerprotokoll unter %LOCALAPPDATA%\\SiroSix\\launcher.log (ohne Zugangsdaten)."""
    try:
        import os, time
        from pathlib import Path
        ordner = Path(os.environ.get("LOCALAPPDATA", ".")) / "SiroSix"
        ordner.mkdir(parents=True, exist_ok=True)
        datei = ordner / "launcher.log"
        if datei.exists() and datei.stat().st_size > 512 * 1024:
            datei.replace(datei.with_suffix(".log.alt"))
        with open(datei, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except Exception:
        pass


def _fehler_melden(titel):
    import traceback
    _protokoll(titel + "\n" + traceback.format_exc())
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, titel + "\n\nDetails stehen in %LOCALAPPDATA%\\SiroSix\\launcher.log.", "SiroSix Launcher", 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    from pathlib import Path
    if len(sys.argv) == 5 and sys.argv[1] == "--apply-update":
        try:
            _protokoll("Update wird installiert")
            from sirosix.updates import apply_update
            apply_update(Path(sys.argv[0]), sys.argv[2], int(sys.argv[3]), sys.argv[4])
            _protokoll("Update installiert")
        except Exception:
            _fehler_melden("Das Launcher-Update konnte nicht installiert werden. Die bisherige Version wurde soweit möglich wiederhergestellt.")
    else:
        try:
            from sirosix import VERSION
            _protokoll(f"Start {VERSION} ({sys.argv[0]})")
            from sirosix.gui import main
            main()
            _protokoll("Beendet")
        except SystemExit:
            raise
        except BaseException:
            _fehler_melden("Der SiroSix Launcher konnte nicht starten.")
