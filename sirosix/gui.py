"""Windows-Oberfläche. Netz- und Dateioperationen laufen außerhalb des UI-Threads."""
from datetime import datetime
import io
import json
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
from . import VERSION
from .api import Api, ApiError, NetworkError, DISCORD_URL
from .windows import SecureStore, data_dir, hardware_id, short_hwid
from .packages import PackageError, EXECUTABLES, VERSION_RE
from .startup import start_product, STEPS
from .updates import check_release, download_release

BG, PANEL, BORDER = "#0b1018", "#131d2a", "#25354a"
TEXT, MUTED, BLUE, GREEN = "#e7eef9", "#8c9eb8", "#5679f8", "#42d7ac"


class Launcher(ctk.CTk):
    def report_callback_exception(self, exc, val, tb):
        # Fehler in Tk-Callbacks nicht still verschlucken, sondern protokollieren
        try:
            import traceback
            from .windows import data_dir
            with open(data_dir() / "launcher.log", "a", encoding="utf-8") as f:
                f.write("Fehler in der Oberfläche:\n" + "".join(traceback.format_exception(exc, val, tb)))
        except Exception:
            pass

    def __init__(self, demo=False):
        super().__init__()
        self.title("SiroSix Launcher · Vorschau" if demo else "SiroSix Launcher")
        icon = Path(__file__).resolve().parent.parent / "assets" / "sirosix.ico"
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.geometry("1120x780")
        self.minsize(950, 700)
        self.configure(fg_color=BG)
        self.demo = demo
        self.api = Api()
        self.store = SecureStore()
        self.events = queue.Queue()
        self.cancel_login = threading.Event()
        self.busy = False
        self.snapshot = None
        self.hwid = None
        self.avatar_image = None
        self.children_running = {}
        self.products = []
        self.selected_key = None
        self.starting_key = None
        self.loading_overlay = None
        self.last_sync = None
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._layout()
        self.after(50, self._pump)
        if demo:
            self._show_demo()
        else:
            self.run(self._restore)

    def _layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=244, corner_radius=0, fg_color="#101925")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(sidebar, text="S6", font=("Segoe UI", 38, "bold"), text_color=BLUE).grid(row=0, column=0, sticky="w", padx=26, pady=(25, 0))
        ctk.CTkLabel(sidebar, text="SIROSIX", font=("Segoe UI", 21, "bold"), text_color=TEXT).grid(row=1, column=0, sticky="w", padx=26)
        ctk.CTkLabel(sidebar, text="DEINE TOOLS", font=("Segoe UI", 10, "bold"), text_color=MUTED).grid(row=2, column=0, sticky="w", padx=27, pady=(27, 10))
        self.tool_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent", corner_radius=0)
        self.tool_list.grid(row=3, column=0, sticky="nsew", padx=12)
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", padx=18, pady=(12, 20))
        ctk.CTkButton(bottom, text="Discord & Support", anchor="w", height=36, fg_color="transparent", hover_color=PANEL,
                      command=lambda: webbrowser.open(DISCORD_URL)).pack(fill="x")
        ctk.CTkButton(bottom, text="Datenschutz", anchor="w", height=36, fg_color="transparent", hover_color=PANEL,
                      command=self._privacy).pack(fill="x")
        self.update_button = ctk.CTkButton(bottom, text="Launcher-Update prüfen", anchor="w", height=36, fg_color="transparent", hover_color=PANEL,
                                           command=lambda: self.run(self._check_update))
        self.update_button.pack(fill="x")
        ctk.CTkLabel(bottom, text=f"Launcher {VERSION}" + (" · VORSCHAU" if self.demo else ""), text_color=MUTED,
                     font=("Segoe UI", 11)).pack(anchor="w", padx=8, pady=(16, 0))
        self.main_area = main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(top, text="Tool-Bibliothek", font=("Segoe UI", 25, "bold"), text_color=TEXT).pack(side="left")
        self.refresh_button = ctk.CTkButton(top, text="Aktualisieren", width=120, fg_color=PANEL, border_width=1,
                                             border_color=BORDER, command=lambda: self.run(self._refresh))
        self.refresh_button.pack(side="right")
        account = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        account.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        account.grid_columnconfigure(1, weight=1)
        self.account_avatar = ctk.CTkLabel(account, text="S6", font=("Segoe UI", 20, "bold"), width=46, height=46,
                                           fg_color="#223454", corner_radius=12, text_color=TEXT)
        self.account_avatar.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=(17, 8))
        self.account_title = ctk.CTkLabel(account, text="Willkommen bei SiroSix", font=("Segoe UI", 16, "bold"), text_color=TEXT, anchor="w")
        self.account_title.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=(17, 0))
        self.account_sub = ctk.CTkLabel(account, text="Melde dich an, um deine Lizenzen zu laden.", text_color=MUTED, anchor="w", font=("Segoe UI", 12))
        self.account_sub.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=(0, 8))
        row = ctk.CTkFrame(account, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 16))
        self.login_button = ctk.CTkButton(row, text="Mit Discord anmelden", fg_color=BLUE, hover_color="#4467dc",
                                         command=lambda: self.run(self._login))
        self.login_button.pack(side="left")
        self.remember = ctk.BooleanVar(value=False)
        self.remember_check = ctk.CTkCheckBox(row, text="Angemeldet bleiben", variable=self.remember, text_color=MUTED,
                                             checkbox_width=19, checkbox_height=19)
        self.remember_check.pack(side="left", padx=18)
        self.logout_button = ctk.CTkButton(row, text="Abmelden", width=96, fg_color="#25354a",
                                          command=lambda: self.run(self._logout))
        self.copy_hwid_button = ctk.CTkButton(row, text="HWID kopieren", width=116, fg_color="#25354a", command=self._copy_hwid)
        self.pc_label = ctk.CTkLabel(row, text="", text_color=MUTED, font=("Consolas", 12))
        self.product_area = ctk.CTkScrollableFrame(main, fg_color="transparent", corner_radius=0)
        self.product_area.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        self._products([])
        # Start bleibt auch bei kleinen Fenstern sichtbar; nur die Informationen scrollen.
        self.action_area.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.progress = ctk.CTkProgressBar(main, height=4, progress_color=BLUE, fg_color=PANEL)
        self.progress.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        self.progress.set(0)
        self.status = ctk.CTkLabel(main, text="Bereit", text_color=MUTED, anchor="w", justify="left", wraplength=620, font=("Segoe UI", 11))
        self.status.grid(row=5, column=0, sticky="ew")

    def run(self, fn):
        if self.busy or self.demo:
            return
        self.busy = True
        self.remember_value = self.remember.get()
        self._enable(False)
        def work():
            try:
                fn()
            except (ApiError, NetworkError, PackageError, OSError, RuntimeError, ValueError) as e:
                self.events.put(("error", str(e)))
            except Exception:
                self.events.put(("error", "Der Vorgang konnte nicht abgeschlossen werden. Bitte erneut versuchen."))
            finally:
                self.events.put(("ready", None))
        threading.Thread(target=work, daemon=True, name="SiroSix-Auftrag").start()

    def _enable(self, enabled):
        state = "normal" if enabled and not self.demo else "disabled"
        for button in (self.login_button, self.logout_button, self.refresh_button, self.remember_check, self.update_button, self.copy_hwid_button):
            button.configure(state=state)
        for button in getattr(self, "tool_buttons", {}).values():
            button.configure(state="normal" if enabled or self.demo else "disabled")
        self._refresh_action_state()

    def _pump(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status.configure(text=value, text_color=MUTED)
                elif kind == "error":
                    self.status.configure(text=value, text_color="#fa8d94")
                    self._finish_loading(value)
                elif kind == "account":
                    self._account(value)
                elif kind == "progress":
                    self.progress.set(value)
                    if self.loading_overlay:
                        self.loading_progress.set(value)
                elif kind == "start_phase":
                    self._loading_phase(*value)
                elif kind == "started":
                    self._finish_loading()
                    self._select_product(self.selected_key)
                elif kind == "avatar":
                    try:
                        image = Image.open(io.BytesIO(value))
                        if image.width <= 512 and image.height <= 512:
                            self.avatar_image = ctk.CTkImage(image.convert("RGB"), size=(46, 46))
                            self.account_avatar.configure(image=self.avatar_image, text="")
                    except Exception:
                        pass
                elif kind == "update_ready":
                    release, downloaded = value
                    current = Path(sys.argv[0]).resolve()
                    if current.name == "SiroSix-Launcher.exe" and messagebox.askyesno("SiroSix Update", "Version " + release["version"] + " ist geprüft und bereit. Launcher jetzt neu starten und aktualisieren?", parent=self):
                        subprocess.Popen([str(downloaded), "--apply-update", str(current), str(os.getpid()), release["sha256"]], close_fds=True)
                        self._close()
                        return
                    self.status.configure(text="Geprüftes Launcher-Update bereit: " + str(downloaded))
                elif kind == "ready":
                    self.busy = False
                    self._enable(True)
        except queue.Empty:
            pass
        for key, process in list(self.children_running.items()):
            if process.poll() is not None:
                del self.children_running[key]
                if key == self.selected_key:
                    self._refresh_action_state()
                if key in self.tool_buttons:
                    product = next((p for p in self.products if p["kuerzel"] == key), {})
                    badge, _ = self._license_status(product, self.snapshot is not None)
                    self.tool_buttons[key].configure(text=product.get("name", key).removeprefix("SiroSix ") + "\n" + badge)
        self.after(80, self._pump)

    def _refresh_action_state(self):
        if not hasattr(self, "start_button") or not self.start_button.winfo_exists():
            return
        product = next((p for p in self.products if p["kuerzel"] == self.selected_key), {})
        license = product.get("lizenz") or {}
        process = self.children_running.get(self.selected_key)
        running = bool(process and process.poll() is None)
        allowed = bool(self.snapshot and license.get("aktiv") and product.get("version") and not running)
        self.start_button.configure(text="Tool läuft" if running else "Starten",
                                    state="normal" if allowed and not self.busy and not self.demo else "disabled")
        self.change_button.configure(state="normal" if license.get("aktiv") and license.get("pc")
                                     and license.get("pc_wechsel_frei") and not self.busy and not self.demo else "disabled")

    def _restore(self):
        saved = self.store.load()
        if saved and isinstance(saved.get("token"), str):
            self.api.token = saved["token"]
            try:
                self._refresh()
                return
            except ApiError as e:
                if e.status != 401:
                    raise
                self.api.token = None
                self.store.clear()
        self.events.put(("status", "Melde dich mit Discord an. Dein Passwort bleibt bei Discord."))

    def _login(self):
        self.cancel_login.clear()
        login_id = secrets.token_urlsafe(32)
        url = self.api.base_url + "/auth/start?" + urllib.parse.urlencode({"id": login_id, "bleiben": int(self.remember_value)})
        self.events.put(("status", "Bestätige die Anmeldung im Browser. Zum Abbrechen den Launcher schließen."))
        webbrowser.open(url)
        deadline = time.monotonic() + 15 * 60
        while time.monotonic() < deadline and not self.cancel_login.wait(2):
            try:
                reply = self.api.request("/auth/poll", {"id": login_id})
            except ApiError as e:
                if e.status == 404:  # Browser kann /auth/start noch nicht erreicht haben.
                    continue
                raise
            if reply.get("status") == "fertig":
                token = reply.get("token")
                if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{30,100}", token):
                    raise RuntimeError("Die Anmeldung hat keine gültige Sitzung geliefert.")
                self.api.token = token
                self.store.save({"token": token})
                self._refresh()
                return
        if not self.cancel_login.is_set():
            raise RuntimeError("Die Anmeldung ist abgelaufen. Bitte erneut versuchen.")

    def _refresh(self):
        if not self.api.token:
            self.events.put(("status", "Bitte zuerst mit Discord anmelden."))
            return
        try:
            snapshot = self.api.me()
        except ApiError as e:
            if e.status == 401:
                self.api.token = None
                self.store.clear()
                self.snapshot = None
                self.events.put(("account", None))
            raise
        if self.hwid is None:
            self.hwid = hardware_id()
        self.snapshot = snapshot
        self.last_sync = datetime.now()
        self.events.put(("account", snapshot))
        self.events.put(("status", "Lizenzen aktualisiert. PC " + short_hwid(self.hwid)))
        user = snapshot.get("nutzer", {})
        if re.fullmatch(r"\d{5,25}", user.get("id", "")) and re.fullmatch(r"(?:a_)?[0-9a-f]{32}", user.get("avatar") or ""):
            try:
                import urllib.request
                url = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=64"
                request = urllib.request.Request(url, headers={"User-Agent": "SiroSix-Launcher/" + VERSION})
                with urllib.request.urlopen(request, timeout=5) as response:
                    raw = response.read(256 * 1024 + 1)
                if len(raw) <= 256 * 1024:
                    self.events.put(("avatar", raw))
            except Exception:
                pass

    def _account(self, snapshot):
        self.snapshot = snapshot
        if snapshot is None:
            self.account_title.configure(text="Willkommen bei SiroSix")
            self.account_sub.configure(text="Melde dich an, um deine Lizenzen zu laden.")
            self.login_button.pack(side="left")
            self.remember_check.pack(side="left", padx=18)
            self.logout_button.pack_forget()
            self.copy_hwid_button.pack_forget()
            self.pc_label.pack_forget()
            self.account_avatar.configure(text="S6", image=None)
            self._products([])
            return
        user = snapshot["nutzer"]
        self.account_title.configure(text="Hallo, " + user["name"])
        self.account_sub.configure(text="Discord verbunden · ID " + user["id"])
        self.login_button.pack_forget()
        self.remember_check.pack_forget()
        self.logout_button.pack(side="left")
        self.copy_hwid_button.pack(side="right")
        self.pc_label.configure(text="Dieser PC · " + short_hwid(self.hwid))
        self.pc_label.pack(side="right", padx=12)
        self._products(snapshot.get("produkte", []))

    def _products(self, products):
        if not products:
            products = [{"kuerzel": p, "name": "SiroSix " + p.title() + " Bot", "lizenz": None}
                        for p in ("verzum", "rubinum")]
        self.products = products
        for child in self.tool_list.winfo_children():
            child.destroy()
        self.tool_buttons = {}
        for product in self.products:
            key = product["kuerzel"]
            active = bool((product.get("lizenz") or {}).get("aktiv"))
            name = product["name"].removeprefix("SiroSix ")
            process = self.children_running.get(key)
            badge = "Tool läuft" if process and process.poll() is None else "Lizenz aktiv" if active else "Keine aktive Lizenz"
            button = ctk.CTkButton(self.tool_list, text=name + "\n" + badge,
                                   anchor="w", height=66, font=("Segoe UI", 13), fg_color="transparent",
                                   hover_color="#223454", border_spacing=14, command=lambda k=key: self._select_product(k))
            button.pack(fill="x", pady=(0, 8))
            self.tool_buttons[key] = button
        if self.selected_key not in self.tool_buttons:
            self.selected_key = self.products[0]["kuerzel"] if self.products else None
        self._select_product(self.selected_key)
        self._enable(not self.busy)

    @staticmethod
    def _license_status(product, signed_in):
        license = product.get("lizenz") or {}
        if not signed_in:
            return "Anmeldung erforderlich", MUTED
        if license.get("gesperrt"):
            return "Lizenz gesperrt", "#fa8d94"
        if license.get("aktiv"):
            return "Lizenz aktiv", GREEN
        if license:
            return "Lizenz abgelaufen", "#e5b66c"
        return "Keine Lizenz", MUTED

    def _select_product(self, key):
        product = next((p for p in self.products if p["kuerzel"] == key), None)
        if not product:
            return
        self.selected_key = key
        for k, button in self.tool_buttons.items():
            button.configure(fg_color="#223454" if k == key else "transparent")
        for child in self.product_area.winfo_children():
            child.destroy()
        self.product_area.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(self.product_area, fg_color=PANEL, border_width=1, border_color=BORDER, corner_radius=14)
        card.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        card.grid_columnconfigure(0, weight=1)
        status, color = self._license_status(product, self.snapshot is not None)
        ctk.CTkLabel(card, text=status.upper(), font=("Segoe UI", 10, "bold"), text_color=color).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 4))
        ctk.CTkLabel(card, text=product["name"], font=("Segoe UI", 23, "bold"), text_color=TEXT, anchor="w", wraplength=560,
                     justify="left").grid(row=1, column=0, sticky="ew", padx=22)
        ctk.CTkLabel(card, text="Produktinformationen und deine persönliche Freigabe.", text_color=MUTED,
                     anchor="w", wraplength=560, justify="left").grid(row=2, column=0, sticky="ew", padx=22, pady=(1, 18))
        license = product.get("lizenz") or {}
        expires = license.get("laeuft_ab")
        duration = "—" if not license else "Lifetime" if expires is None else datetime.fromtimestamp(expires / 1000).strftime("%d.%m.%Y · %H:%M")
        license_type = {"zeit": "Zeitlizenz", "lifetime": "Lifetime", "abo": "Abonnement"}.get(license.get("art"), "—")
        installed = self._installed_version(key)
        rows = [
            ("Verfügbare Version", product.get("version") or "Noch nicht veröffentlicht"),
            ("Installierte Version", installed or "Noch nicht installiert"),
            ("Lizenzmodell", license_type),
            ("Gültig bis", duration),
            ("Freigegebene Clients", str(license.get("slots", "—"))),
            ("Gebundener PC", (license.get("pc") or "Wird beim ersten Start gebunden") if license else "Keine Lizenz gebunden"),
            ("Kostenloser PC-Wechsel", "Verfügbar" if license.get("pc_wechsel_frei") else "Bereits genutzt" if license else "—"),
        ]
        facts = ctk.CTkFrame(card, fg_color="transparent")
        facts.grid(row=3, column=0, sticky="ew", padx=22)
        facts.grid_columnconfigure(1, weight=1)
        for row, (label, value) in enumerate(rows):
            ctk.CTkLabel(facts, text=label, text_color=MUTED, anchor="w", height=22, font=("Segoe UI", 12)).grid(row=row, column=0, sticky="nw", padx=(0, 24), pady=2)
            ctk.CTkLabel(facts, text=value, text_color=TEXT, anchor="w", justify="left", wraplength=330,
                         height=22, font=("Segoe UI", 12)).grid(row=row, column=1, sticky="ew", pady=2)
        if not hasattr(self, "action_area"):
            self.action_area = ctk.CTkFrame(self.main_area, fg_color=PANEL, corner_radius=12, border_width=1, border_color=BORDER)
        for child in self.action_area.winfo_children():
            child.destroy()
        actions = ctk.CTkFrame(self.action_area, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=12)
        self.start_button = ctk.CTkButton(actions, text="Starten", width=148, height=40, fg_color=BLUE, hover_color="#4467dc",
                                         font=("Segoe UI", 14, "bold"), command=lambda: self._begin_start(product))
        self.start_button.pack(side="left")
        self.change_button = ctk.CTkButton(actions, text="PC wechseln", width=120, height=40, fg_color="#25354a",
                                          command=lambda: self._change_confirm(product))
        self.change_button.pack(side="left", padx=10)
        note = "Beim Start werden Lizenz, Updates und alle Programmdateien geprüft."
        if self.demo:
            note = "Beispieldaten · Starten und Kontofunktionen sind in der Vorschau deaktiviert."
        elif not self.snapshot:
            note = "Melde dich oben mit Discord an, um dieses Tool freizuschalten."
        elif not license.get("aktiv"):
            note = "Eine Lizenz und Hilfe erhältst du über Discord & Support."
        elif not product.get("version"):
            note = "Deine Lizenz ist aktiv. Ein Produktpaket wurde noch nicht veröffentlicht."
        ctk.CTkLabel(card, text=note, text_color=MUTED, font=("Segoe UI", 11), wraplength=560,
                     anchor="w", justify="left").grid(row=4, column=0, sticky="ew", padx=22, pady=(16, 20))
        sync = self.last_sync.strftime("%H:%M:%S") if self.last_sync else "noch nicht synchronisiert"
        ctk.CTkLabel(self.product_area, text="Beispieldaten zur Vorschau" if self.demo else "Lizenzstatus vom Server · " + sync,
                     text_color=MUTED, font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=(10, 0), padx=5)
        self._refresh_action_state()

    def _installed_version(self, key):
        if self.demo:
            return "1.1.0" if key == "verzum" else None
        folder = data_dir() / "products" / key
        if not folder.is_dir() or key not in EXECUTABLES:
            return None
        versions = [p.name for p in folder.iterdir() if p.is_dir() and VERSION_RE.fullmatch(p.name)
                    and (p / EXECUTABLES[key]).is_file() and (p / ".installed.json").is_file()]
        return max(versions, key=lambda v: tuple(int(n) for n in v.split("-")[0].split(".")), default=None)

    def _copy_hwid(self):
        if self.hwid and not self.demo:
            self.clipboard_clear()
            self.clipboard_append(self.hwid)
            self.status.configure(text="HWID-Hash in die Zwischenablage kopiert.", text_color=MUTED)

    def _begin_start(self, product):
        if self.busy or self.demo or not (product.get("lizenz") or {}).get("aktiv") or not product.get("version"):
            return
        self._show_loading(product)
        self.run(lambda: self._start(product))

    def _show_loading(self, product):
        if self.loading_overlay:
            self.loading_overlay.destroy()
        self.starting_key = product["kuerzel"]
        self.loading_steps_seen = set()
        self.loading_overlay = overlay = ctk.CTkFrame(self.main_area, fg_color=BG, corner_radius=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()
        overlay.grid_columnconfigure(0, weight=1)
        overlay.grid_rowconfigure((0, 2), weight=1)
        card = ctk.CTkFrame(overlay, fg_color=PANEL, border_width=1, border_color=BORDER, corner_radius=18)
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=20)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="S6", font=("Segoe UI", 34, "bold"), text_color=BLUE).grid(row=0, column=0, pady=(24, 4))
        self.loading_title = ctk.CTkLabel(card, text="Vorschau · Startprüfung" if self.demo else "Start wird vorbereitet", font=("Segoe UI", 21, "bold"), text_color=TEXT)
        self.loading_title.grid(row=1, column=0, padx=24)
        ctk.CTkLabel(card, text=product["name"], text_color=MUTED, wraplength=500).grid(row=2, column=0, padx=24, pady=(0, 20))
        steps = ctk.CTkFrame(card, fg_color="transparent")
        steps.grid(row=3, column=0, sticky="ew", padx=32)
        self.loading_labels = {}
        for index, (name, title) in enumerate(STEPS):
            label = ctk.CTkLabel(steps, text="○  " + title, text_color=MUTED, anchor="w", font=("Segoe UI", 13))
            label.pack(fill="x", pady=4)
            self.loading_labels[name] = label
        self.loading_progress = ctk.CTkProgressBar(card, height=5, progress_color=BLUE, fg_color=BORDER, mode="indeterminate")
        self.loading_progress.grid(row=4, column=0, sticky="ew", padx=32, pady=(22, 12))
        self.loading_progress.start()
        self.loading_detail = ctk.CTkLabel(card, text="Verbindung zum Lizenzserver wird hergestellt …", text_color=MUTED,
                                          font=("Segoe UI", 12), justify="left", anchor="w", wraplength=480)
        self.loading_detail.grid(row=5, column=0, sticky="ew", padx=32, pady=(0, 24))
        self.loading_close = ctk.CTkButton(card, text="Zurück zur Übersicht", command=self._dismiss_loading, fg_color="#25354a")
        if self.demo:
            self.loading_close.grid(row=6, column=0, padx=32, pady=(0, 24), sticky="w")

    def _loading_phase(self, name, detail):
        if not self.loading_overlay:
            return
        names = [key for key, _ in STEPS]
        if name not in names:
            return
        self.loading_steps_seen.add(name)
        current = names.index(name)
        for index, (key, title) in enumerate(STEPS):
            if index < current:
                skipped = key == "download" and key not in self.loading_steps_seen
                text = "—  " + title + " · nicht nötig" if skipped else "✓  " + title
                self.loading_labels[key].configure(text=text, text_color=MUTED if skipped else GREEN)
            elif index == current:
                self.loading_labels[key].configure(text="●  " + title, text_color=TEXT)
        self.loading_detail.configure(text=detail)
        self.status.configure(text=detail, text_color=MUTED)
        if name == "download":
            self.loading_progress.stop()
            self.loading_progress.configure(mode="determinate")
            self.loading_progress.set(0)
        else:
            self.loading_progress.configure(mode="indeterminate")
            self.loading_progress.start()

    def _finish_loading(self, error=None):
        if not self.loading_overlay:
            return
        self.loading_progress.stop()
        self.loading_progress.configure(mode="determinate")
        if error:
            self.loading_title.configure(text="Start konnte nicht abgeschlossen werden", text_color="#fa8d94", wraplength=480)
            self.loading_detail.configure(text=error, text_color="#fa8d94")
            self.loading_progress.set(0)
            self.loading_close.grid(row=6, column=0, padx=32, pady=(0, 24), sticky="w")
        else:
            self.loading_title.configure(text="Tool wurde geöffnet", text_color=GREEN)
            self.loading_progress.set(1)
            self.loading_labels["launch"].configure(text="✓  Tool öffnen", text_color=GREEN)
            # Die Bestätigung bleibt kurz sichtbar, schnelle Prüfungen werden nicht künstlich verzögert.
            overlay = self.loading_overlay
            self.after(650, lambda: self._dismiss_loading() if self.loading_overlay is overlay else None)
        self.starting_key = None

    def _dismiss_loading(self):
        if self.loading_overlay:
            self.loading_overlay.destroy()
            self.loading_overlay = None

    def _start(self, product):
        key = product["kuerzel"]
        process = self.children_running.get(key)
        if process and process.poll() is None:
            raise RuntimeError("Dieser Bot läuft bereits.")
        if not product.get("version"):
            raise RuntimeError("Für diesen Bot wurde noch kein Produktpaket veröffentlicht.")
        self.children_running[key] = start_product(self.api, key, self.hwid,
            lambda name, detail: self.events.put(("start_phase", (name, detail))),
            lambda done, total: self.events.put(("progress", done / total)))
        self.events.put(("started", None))
        self.events.put(("status", product["name"] + " wurde geöffnet. Starte den Farmer im Bot-Fenster."))
        try:
            self._refresh()
        except (ApiError, NetworkError):
            self.events.put(("status", "Tool wurde geöffnet. Die Lizenzübersicht konnte gerade nicht erneut geladen werden."))

    def _change_confirm(self, product):
        if self.busy or self.demo:
            return
        if messagebox.askyesno("PC wechseln", "Die bestehende PC-Bindung wird gelöst. Der nächste Bot-Start bindet den neuen PC. Ein Wechsel pro Lizenz ist kostenlos. Jetzt wechseln?", parent=self):
            def change():
                self.api.request("/pc/wechsel", {"produkt": product["kuerzel"]})
                self._refresh()
            self.run(change)

    def _logout(self):
        server_ok = True
        try:
            self.api.request("/auth/logout", {})
        except (ApiError, NetworkError):
            server_ok = False
        finally:
            self.store.clear()
            self.api.token = None
            self.snapshot = None
            self.events.put(("account", None))
        self.events.put(("status", "Abgemeldet." if server_ok else "Auf diesem PC abgemeldet. Der Server war nicht erreichbar; die Serversitzung konnte noch nicht beendet werden."))

    def _privacy(self):
        messagebox.showinfo("SiroSix Datenschutz", "SiroSix verarbeitet deine Discord-ID, deinen Discord-Anzeigenamen und dein Avatar-Kürzel, Lizenzdaten sowie einen Hash deiner PC-Kennung. Die Hardware-Rohdaten verlassen deinen PC nicht. Die Sitzung wird auf diesem Windows-Konto verschlüsselt gespeichert. Discord, Cloudflare und GitHub werden für Anmeldung, Lizenzen und Updates verwendet. Dein Discord-Passwort erhält SiroSix nicht.\n\nKontakt: sirosix@proton.me\n\nDies ist ein technischer Hinweis. Aufbewahrungsfristen und die vollständige Datenschutzerklärung müssen vor einem öffentlichen Verkaufsstart ergänzt werden.", parent=self)

    def _check_update(self):
        release = check_release()
        if not release:
            self.events.put(("status", "Kein neueres veröffentlichtes Launcher-Update verfügbar."))
            return
        downloaded = download_release(release, data_dir() / "updates")
        self.events.put(("update_ready", (release, downloaded)))

    def _show_demo(self):
        self.hwid = "a3f9" + "0" * 56 + "7c21"
        self._account({"nutzer": {"id": "demo", "name": "SiroSix"}, "produkte": [
            {"kuerzel": "verzum", "name": "SiroSix Verzum Bot", "version": "1.1.1", "lizenz": {"aktiv": True, "art": "zeit", "laeuft_ab": (time.time() + 7 * 86400) * 1000, "slots": 1, "pc": "A3F9...7C21", "pc_wechsel_frei": True}},
            {"kuerzel": "rubinum", "name": "SiroSix Rubinum Bot", "version": None, "lizenz": None},
        ]})
        self.status.configure(text="Vorschau mit Beispieldaten. Kein Login, kein Download, kein Spielstart.")
        self._enable(True)

    def _close(self):
        self.cancel_login.set()
        self.destroy()


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = Launcher(demo="--demo" in sys.argv)
    if app.demo and "--demo-loading" in sys.argv:
        app._show_loading(app.products[0])
        app._loading_phase("files", "Vorschau: Installierte Dateien werden geprüft. Kein echter Download oder Start.")
    app.mainloop()
