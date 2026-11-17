"""Lizenzgesteuerter Einstieg für die beiden separat kompilierten Produkte."""
import ctypes
from pathlib import Path
import threading
import sys
from .api import Api
from .license import LicenseGuard, LeaseError
from .windows import SecureStore, data_dir, hardware_id

_guard = None


def input_allowed():
    return _guard is not None and _guard.valid()


def permitted_call(function, *args, **kwargs):
    if _guard is None:
        return None
    # Die Sperrentscheidung und ein neuer Tastendruck dürfen sich nicht überholen.
    with _guard.lock:
        if _guard.valid():
            return function(*args, **kwargs)


def protect_inputs(bot):
    def mouse(flags, dx=0, dy=0, data=0, extra=0):
        if not input_allowed():
            flags &= 0x0004 | 0x0010 | 0x0040
            return original_mouse(flags, dx, dy, data, extra)
        return permitted_call(original_mouse, flags, dx, dy, data, extra)
    original_mouse = bot.win32api.mouse_event
    bot.win32api.mouse_event = mouse
    original_key = bot.win32api.keybd_event
    def key(vk, scan=0, flags=0, extra=0):
        if flags & 2:
            return original_key(vk, scan, flags, extra)
        return permitted_call(original_key, vk, scan, flags, extra)
    bot.win32api.keybd_event = key
    original_position = bot.win32api.SetCursorPos
    bot.win32api.SetCursorPos = lambda point: permitted_call(original_position, point)
    for name in ("keyDown", "press"):
        original = getattr(bot.pydirectinput, name)
        def protected(*args, _original=original, **kwargs):
            return permitted_call(_original, *args, **kwargs)
        setattr(bot.pydirectinput, name, protected)
    if hasattr(bot, "HidBruecke"):
        command = bot.HidBruecke.befehl
        def hid_command(self, text):
            if text.split(" ")[0] in ("rel", "q", "ku", "bu"):
                return command(self, text)
            return permitted_call(command, self, text)
        bot.HidBruecke.befehl = hid_command


def release_all(bot, app):
    app.stop_event.set()
    hid = getattr(bot, "HID", None)
    if hid is not None:
        hid.befehl("rel")
    for key in ("w", "a", "s", "d", "q", "e", "r", "f", "t", "g", "shift", "ctrl", "alt", "space"):
        try:
            bot.pydirectinput.keyUp(key)
        except Exception:
            pass
    for flags in (0x0004, 0x0010, 0x0040):
        try:
            bot.win32api.mouse_event(flags, 0, 0, 0, 0)
        except Exception:
            pass


def main(product):
    global _guard
    import auto_clicker as bot
    if "--self-test" in sys.argv:
        import json
        # Interner Build-Test: keine Anmeldung, keine Spielfenstersuche, keine Eingaben.
        target = Path(sys.executable).parent / "self-test.json"
        target.write_text(json.dumps({"product": product, "imports": True, "input_allowed": input_allowed()}), "utf-8")
        return
    app_holder = []
    try:
        saved = SecureStore().load()
        if not saved or not saved.get("token"):
            raise LeaseError("Bitte zuerst im SiroSix Launcher mit Discord anmelden.")
        api = Api(saved["token"])
        identity = api.me()["nutzer"]["id"]
        def stop(message):
            if app_holder:
                app = app_holder[0]
                release_all(bot, app)
                app._ui(lambda: app.stop())
                app.log("[LIZENZ] " + message)
        def status(message):
            if app_holder:
                app_holder[0].log("[LIZENZ] " + message)
        _guard = LicenseGuard(api, product, hardware_id(), identity, stop, status)
        _guard.start()
        protect_inputs(bot)
        resource_dir = Path(bot._ORDNER)
        state_dir = data_dir() / "bots" / product
        state_dir.mkdir(parents=True, exist_ok=True)
        bot.RESOURCE_DIR = str(resource_dir)
        bot._ORDNER = str(state_dir)
        bot.LOGFILE = str(state_dir / "log.txt")
        bot.CONFIGFILE = str(state_dir / "config.json")
        bot.STEINE_DIR = str(resource_dir / "steine")
        original_start = bot.App.start_klick
        def licensed_start(self):
            if not input_allowed():
                self.log("[LIZENZ] Keine gültige Freigabe. Bitte den Bot über den Launcher neu öffnen.")
                return
            return original_start(self)
        bot.App.start_klick = licensed_start
        # Entwicklungs-Fernsteuerung wird in Produktbuilds vollständig deaktiviert.
        bot.App._test_befehl = lambda self: None
        bot.ctk.set_appearance_mode("dark")
        if bot._schon_eine_instanz_offen():
            raise RuntimeError("Dieser SiroSix Bot läuft bereits.")
        root = bot.ctk.CTk()
        app = bot.App(root)
        app_holder.append(app)
        root.mainloop()
    except Exception as e:
        # Netzwerk- und Lizenzfehler enthalten keine Zugangsdaten.
        message = str(e) if e.__class__.__module__.startswith("sirosix") or isinstance(e, RuntimeError) else "Der Bot konnte nicht sicher gestartet werden. Bitte im Launcher erneut versuchen."
        ctypes.windll.user32.MessageBoxW(None, message, "SiroSix", 0x10)
    finally:
        if _guard is not None:
            _guard.close()
        if app_holder:
            release_all(bot, app_holder[0])
        if getattr(bot, "HID", None) is not None:
            bot.HID.stop()
