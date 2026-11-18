"""S6 Farmbot Oberfläche im Stil eines Mod-Menüs.

Wird von bot_runtime vor dem Erzeugen der App eingehängt und ersetzt nur den Aufbau
der Oberfläche (Kopf, Reiter, Karten, Schalter, Fußleiste). Die Bot-Logik und alle
Variablen bleiben unverändert. Dazu kommen Sprachwahl, Server-Logo, Farben je
Server und ein Overlay im Spielfenster.
"""
import base64
import collections
import ctypes
import io
import json
import os
from pathlib import Path
import time

from . import i18n
from .i18n import tr

SERVER = {
    "verzum": {"name": "Verzum", "logo": "VERZUM"},
    "rubinum": {"name": "Rubinum Classic", "logo": "RUBINUM"},
}

FARBEN = {
    "verzum": dict(
        BG="#0a0806", SIDE="#110d09", CARD="#15100b", RAND="#2e2216", FELD="#0c0907",
        HOVER="#1d160f", SEL="#261c12", TEXT="#f0e6d2", MUTED="#a39276", DIM="#6a5c47",
        ACC="#e3b45a", ACC_H="#c99a3e", AUF_ACC="#1b1206", GOLD="#f2c46d", ACC_DIM="#5a4325",
        GREEN="#3fbf6f", GREEN_H="#33a35d", RED="#d9463b", RED_H="#b9392f"),
    "rubinum": dict(
        BG="#0b0506", SIDE="#12080a", CARD="#170a0c", RAND="#33161a", FELD="#0d0607",
        HOVER="#200d10", SEL="#2b1115", TEXT="#f3e4e0", MUTED="#b2918c", DIM="#715753",
        ACC="#e0303f", ACC_H="#bf2533", AUF_ACC="#ffffff", GOLD="#f0b54f", ACC_DIM="#6b1f27",
        GREEN="#3fbf6f", GREEN_H="#33a35d", RED="#e0303f", RED_H="#bf2533"),
}

_bot = None
_produkt = None


def _einstellungen_datei():
    basis = os.environ.get("LOCALAPPDATA")
    return Path(basis) / "SiroSix" / "oberflaeche.json" if basis else None


def _einstellungen():
    try:
        d = json.loads(_einstellungen_datei().read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _einstellung_setzen(schluessel, wert):
    datei = _einstellungen_datei()
    if not datei:
        return
    try:
        d = _einstellungen()
        d[schluessel] = wert
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(json.dumps(d), "utf-8")
    except Exception:
        pass


def server_logo(kante=128):
    from PIL import Image
    from . import logos
    daten = base64.b64decode(getattr(logos, SERVER[_produkt]["logo"]))
    bild = Image.open(io.BytesIO(daten)).convert("RGBA")
    return bild.resize((kante, kante), Image.LANCZOS) if kante != bild.width else bild


def s6_abzeichen(kante=160):
    """S6 Zeichen für Fenster, Taskleiste und Tray."""
    from PIL import Image, ImageDraw, ImageFont
    F = _bot.F
    img = Image.new("RGBA", (kante, kante), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rand = max(2, kante // 22)
    d.rounded_rectangle((0, 0, kante - 1, kante - 1), radius=kante // 6, fill=F.BG, outline=F.ACC, width=rand)
    schrift = None
    for name in ("bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            schrift = ImageFont.truetype(name, int(kante * 0.5))
            break
        except Exception:
            pass
    if schrift is not None:
        d.text((kante / 2, kante / 2 + kante * 0.02), "S6", fill=F.GOLD, font=schrift, anchor="mm")
    return img


# ============================================================
#  Einbau
# ============================================================
def anwenden(bot, produkt):
    global _bot, _produkt
    _bot, _produkt = bot, produkt
    i18n.setzen(i18n.gespeichert())
    i18n.installieren(bot.ctk)
    if getattr(bot, "_HAS_TRAY", False):
        try:
            i18n.pystray_installieren(bot.pystray)
        except Exception:
            pass
    for name, wert in FARBEN[produkt].items():
        setattr(bot.F, name, wert)
    bot.APP_NAME = "S6 Farmbot · " + SERVER[produkt]["name"]
    App = bot.App
    App._schriften = _schriften
    App._ui_bauen = _ui_bauen
    App._kompakt_umschalten = _kompakt_umschalten
    App._seite_zeigen = _seite_zeigen
    App._karte = _karte
    App._zeile = _zeile
    App._schalter = _schalter
    App._knopf = _knopf
    App._auswahl = _auswahl
    App._feld = _feld
    App._logo_bild = lambda self, kante=160: s6_abzeichen(kante)
    App._log_zeile = _log_zeile
    App._log_tags = _log_tags
    App._mini_bauen = _mini_bauen
    App._discord_link = lambda self: "https://discord.gg/vRmhmJRQVK"
    App._sprache_wechseln = _sprache_wechseln
    App._neu_aufbauen = _neu_aufbauen
    tick_alt = App._tick

    def _tick(self):
        try:
            _overlay(self).aktualisieren()
        except Exception:
            pass
        return tick_alt(self)
    App._tick = _tick
    schliessen_alt = App._beim_schliessen

    def _beim_schliessen(self):
        try:
            _overlay(self).weg()
        except Exception:
            pass
        return schliessen_alt(self)
    App._beim_schliessen = _beim_schliessen


# ============================================================
#  Aufbau
# ============================================================
def _schriften(self):
    ctk = _bot.ctk
    nt = os.name == "nt"
    text = "Segoe UI" if nt else "DejaVu Sans"
    kopf = "Bahnschrift" if nt else "DejaVu Sans"
    mono = "Consolas" if nt else "DejaVu Sans Mono"
    f = ctk.CTkFont
    self.f_titel = f(family=kopf, size=24, weight="bold")
    self.f_h = f(family=kopf, size=13, weight="bold")
    self.f_tab = f(family=kopf, size=13, weight="bold")
    self.f_text = f(family=text, size=13)
    self.f_fett = f(family=text, size=13, weight="bold")
    self.f_klein = f(family=text, size=12)
    self.f_mini = f(family=text, size=11)
    self.f_zahl = f(family=kopf, size=30, weight="bold")
    self.f_btn = f(family=kopf, size=16, weight="bold")
    self.f_mono = f(family=mono, size=12)


def _ui_bauen(self):
    ctk, F = _bot.ctk, _bot.F
    r = self.root
    r.grid_columnconfigure(0, weight=1)
    r.grid_columnconfigure(1, weight=0)
    r.grid_rowconfigure(0, weight=1)
    if not hasattr(self, "_s6_overlay_an"):
        self._s6_overlay_an = _bot.tk.BooleanVar(value=bool(_einstellungen().get("overlay", True)))
        self._s6_overlay_an.trace_add("write", lambda *_: _einstellung_setzen("overlay", bool(self._s6_overlay_an.get())))

    haupt = ctk.CTkFrame(r, fg_color=F.BG, corner_radius=0, border_width=1, border_color=F.ACC_DIM)
    haupt.grid(row=0, column=0, columnspan=2, sticky="nsew")
    haupt.grid_columnconfigure(0, weight=1)
    haupt.grid_rowconfigure(2, weight=1)
    self._haupt = haupt
    self._sb = haupt          # alte Namen, falls andere Teile darauf zugreifen
    self._inhalt = haupt

    # ----- Kopf: Server-Logo, Name, Sprache -----
    kopf = ctk.CTkFrame(haupt, fg_color=F.SIDE, corner_radius=0, height=70)
    kopf.grid(row=0, column=0, sticky="ew", padx=1, pady=(1, 0))
    kopf.grid_columnconfigure(1, weight=1)
    try:
        self._s6_logo = ctk.CTkImage(light_image=server_logo(), dark_image=server_logo(), size=(50, 50))
        ctk.CTkLabel(kopf, text="", image=self._s6_logo, width=50).grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=10)
    except Exception:
        pass
    titel = ctk.CTkFrame(kopf, fg_color="transparent")
    titel.grid(row=0, column=1, rowspan=2, sticky="w")
    zeile = ctk.CTkFrame(titel, fg_color="transparent")
    zeile.pack(anchor="w")
    ctk.CTkLabel(zeile, text="S6", font=self.f_titel, text_color=F.ACC, height=30).pack(side="left")
    ctk.CTkLabel(zeile, text=" FARMBOT", font=self.f_titel, text_color=F.GOLD, height=30).pack(side="left")
    ctk.CTkLabel(zeile, text=f"  v{_bot.APP_VERSION}", font=self.f_mini, text_color=F.DIM, height=30).pack(side="left", pady=(6, 0))
    ctk.CTkLabel(titel, text=SERVER[_produkt]["name"].upper() + "  ·  " + tr("AUTOMATISCHER METIN FARMER"),
                 font=self.f_mini, text_color=F.MUTED, height=16, anchor="w").pack(anchor="w")

    rechts = ctk.CTkFrame(kopf, fg_color="transparent")
    rechts.grid(row=0, column=2, rowspan=2, sticky="e", padx=14)
    ctk.CTkLabel(rechts, text=tr("Sprache").upper(), font=self.f_mini, text_color=F.DIM).pack(side="left", padx=(0, 6))
    self._s6_sprache = _bot.tk.StringVar(value=i18n.name())
    ctk.CTkOptionMenu(rechts, variable=self._s6_sprache, values=[n for _c, n in i18n.SPRACHEN],
                      command=self._sprache_wechseln, width=118, height=28, corner_radius=3,
                      font=self.f_klein, dropdown_font=self.f_klein, fg_color=F.FELD,
                      button_color=F.RAND, button_hover_color=F.SEL, text_color=F.TEXT,
                      dropdown_fg_color=F.CARD, dropdown_hover_color=F.SEL,
                      dropdown_text_color=F.TEXT).pack(side="left")
    ctk.CTkButton(rechts, text=tr("Kompaktansicht"), command=self._kompakt_umschalten, width=120, height=28,
                  corner_radius=3, font=self.f_klein, fg_color=F.SEL, hover_color=F.RAND,
                  text_color=F.TEXT, border_width=1, border_color=F.ACC_DIM).pack(side="left", padx=(10, 0))
    ctk.CTkFrame(haupt, height=2, fg_color=F.ACC, corner_radius=0).grid(row=0, column=0, sticky="sew", padx=1)

    # ----- Reiter -----
    reiter = ctk.CTkFrame(haupt, fg_color=F.BG, corner_radius=0, height=40)
    reiter.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 0))
    self._s6_reiter_strich = {}
    for key, name, _unter in _bot.SEITEN:
        feld = ctk.CTkFrame(reiter, fg_color="transparent")
        feld.pack(side="left", padx=(0, 4))
        b = ctk.CTkButton(feld, text=tr(name).upper(), height=32, corner_radius=3, font=self.f_tab,
                          fg_color="transparent", hover_color=F.HOVER, text_color=F.MUTED,
                          width=110, command=lambda k=key: self._seite_zeigen(k))
        b.pack()
        strich = ctk.CTkFrame(feld, width=10, height=2, corner_radius=0, fg_color=F.BG)
        strich.pack(fill="x")
        self._nav_btn[key] = b
        self._s6_reiter_strich[key] = strich
    extra = ctk.CTkFrame(reiter, fg_color="transparent")
    extra.pack(side="right")
    extra.grid_columnconfigure((0, 1), weight=0)
    self.feedback_btn = ctk.CTkButton(extra, text=tr("Feedback / Bug melden"), height=28, corner_radius=3,
                                      font=self.f_klein, fg_color="transparent", hover_color=F.HOVER,
                                      text_color=F.MUTED, command=self._feedback_oeffnen, width=10)
    self.feedback_btn.grid(row=0, column=0, padx=(0, 4))
    self.discord_btn = ctk.CTkButton(extra, text="Discord", height=28, corner_radius=3, width=80,
                                     font=self.f_klein, fg_color="transparent", hover_color=F.HOVER,
                                     text_color="#8b9cff", border_width=1, border_color="#3a4280",
                                     command=self._discord_oeffnen)
    self.discord_btn.grid(row=0, column=1)
    ctk.CTkFrame(haupt, height=1, fg_color=F.RAND, corner_radius=0).grid(row=1, column=0, sticky="sew", padx=14)

    # ----- Inhalt -----
    self._halter = ctk.CTkFrame(haupt, fg_color="transparent")
    self._halter.grid(row=2, column=0, sticky="nsew", padx=(14, 0), pady=(12, 10))
    self._halter.grid_columnconfigure(0, weight=1)
    self._halter.grid_rowconfigure(0, weight=1)
    # alte Kopfzeile wird nicht mehr gezeigt, die Namen bleiben für den alten Code
    self.kopf_titel = ctk.CTkLabel(haupt, text="")
    self.kopf_unter = ctk.CTkLabel(haupt, text="")
    for key, bauer, scroll in (("dashboard", self._seite_dashboard, False),
                               ("einstellungen", self._seite_einstellungen, True),
                               ("erkennung", self._seite_erkennung, True),
                               ("protokoll", self._seite_protokoll, False)):
        if scroll:
            f = ctk.CTkScrollableFrame(self._halter, fg_color="transparent",
                                       scrollbar_button_color=F.ACC_DIM,
                                       scrollbar_button_hover_color=F.ACC)
        else:
            f = ctk.CTkFrame(self._halter, fg_color="transparent")
        bauer(f)
        self._seiten[key] = (f, scroll)

    # ----- Fußleiste: Status, Overlay, Start/Stop -----
    fuss = ctk.CTkFrame(haupt, fg_color=F.SIDE, corner_radius=0, height=64)
    fuss.grid(row=3, column=0, sticky="ew", padx=1, pady=(0, 1))
    fuss.grid_columnconfigure(2, weight=1)
    ctk.CTkFrame(haupt, height=1, fg_color=F.ACC_DIM, corner_radius=0).grid(row=3, column=0, sticky="new", padx=1)
    st = ctk.CTkFrame(fuss, fg_color=F.CARD, corner_radius=3, border_width=1, border_color=F.ACC_DIM)
    st.grid(row=0, column=0, padx=(14, 10), pady=12, sticky="w")
    self.status_punkt = ctk.CTkFrame(st, width=10, height=10, corner_radius=5, fg_color=F.DIM)
    self.status_punkt.pack(side="left", padx=(12, 8), pady=8)
    self.status_label = ctk.CTkLabel(st, text="Bereit", font=self.f_fett, text_color=F.TEXT, width=90, anchor="w")
    self.status_label.pack(side="left", padx=(0, 10), pady=6)
    self._status_punkte.append(self.status_punkt)
    self._status_labels.append(self.status_label)
    tasten = ctk.CTkFrame(fuss, fg_color="transparent")
    tasten.grid(row=0, column=1, sticky="w")
    for taste, was in (("Ende / Entf", "Start / Stop"), ("Strg+Entf", "Fenster ein / aus")):
        z = ctk.CTkFrame(tasten, fg_color="transparent")
        z.pack(anchor="w", pady=1)
        ctk.CTkLabel(z, text=taste, font=self.f_mini, text_color=F.TEXT, fg_color=F.SEL,
                     corner_radius=3, width=70, height=18).pack(side="left")
        ctk.CTkLabel(z, text=was, font=self.f_mini, text_color=F.MUTED, height=18).pack(side="left", padx=6)
    ov = ctk.CTkCheckBox(fuss, text=tr("Overlay im Spiel"), variable=self._s6_overlay_an, onvalue=True,
                         offvalue=False, font=self.f_klein, text_color=F.TEXT, corner_radius=3,
                         checkbox_width=18, checkbox_height=18, border_width=2, border_color=F.ACC_DIM,
                         fg_color=F.ACC, hover_color=F.ACC_H, checkmark_color=F.AUF_ACC)
    ov.grid(row=0, column=3, padx=(0, 16), sticky="e")
    if _produkt == "verzum":
        self._s6_overlay_knopf = ctk.CTkButton(
            fuss, text="Overlay verschieben", width=142, height=30, corner_radius=3,
            fg_color=F.CARD, hover_color=F.HOVER, text_color=F.TEXT, font=self.f_klein,
            command=lambda: _overlay(self).verschieben())
        self._s6_overlay_knopf.grid(row=0, column=4, padx=(0, 12), sticky="e")
    self.start_btn = ctk.CTkButton(fuss, text="▶   START", height=40, width=190, corner_radius=3,
                                   font=self.f_btn, fg_color=F.GREEN, hover_color=F.GREEN_H,
                                   text_color="#04130a", command=self._start_stop_knopf)
    self.start_btn.grid(row=0, column=5, padx=(0, 14), pady=12, sticky="e")
    self._start_knoepfe.append(self.start_btn)

    self._seite = None
    self._seite_zeigen("dashboard")
    self._mini_bauen()


def _seite_zeigen(self, key):
    F = _bot.F
    if key == self._seite:
        return
    for k, (f, scroll) in self._seiten.items():
        if k == key:
            f.grid(row=0, column=0, sticky="nsew", padx=(0, 4 if scroll else 14))
        else:
            f.grid_forget()
    for k, b in self._nav_btn.items():
        aktiv = k == key
        b.configure(text_color=F.GOLD if aktiv else F.MUTED, fg_color=F.SEL if aktiv else "transparent")
        try:
            self._s6_reiter_strich[k].configure(fg_color=F.ACC if aktiv else F.BG)
        except Exception:
            pass
    self._seite = key


def _kompakt_umschalten(self):
    import re
    try:
        if not self._kompakt:
            self._geo_voll = self.root.geometry()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self._haupt.grid_remove()
            self._mini.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self.root.minsize(340, 160)
            self.root.geometry(f"380x172+{x}+{y}")
            self.root.attributes("-alpha", 0.93)
            self._kompakt = True
        else:
            self._mini.grid_remove()
            self._haupt.grid()
            self.root.attributes("-alpha", 1.0)
            self.root.minsize(940, 620)
            m = re.fullmatch(r"(\d+)x(\d+)[+-]-?\d+[+-]-?\d+", str(self._geo_voll or ""))
            b, h = (int(m.group(1)), int(m.group(2))) if m else (1000, 680)
            self.root.geometry(f"{b}x{h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self._kompakt = False
            self.root.after(50, self._im_bildschirm_halten)
    except Exception as e:
        self.log(f"[!] Ansicht konnte nicht gewechselt werden: {e}")


# ---------- Bausteine ----------
def _karte(self, eltern, titel=None, hinweis=None, pack=True):
    ctk, F = _bot.ctk, _bot.F
    k = ctk.CTkFrame(eltern, fg_color=F.CARD, corner_radius=4, border_width=1, border_color=F.ACC_DIM)
    if pack:
        k.pack(fill="x", pady=(0, 12))
    if titel:
        kopf = ctk.CTkFrame(k, fg_color="transparent", height=24)
        kopf.pack(fill="x", padx=14, pady=(11, 2))
        ctk.CTkLabel(kopf, text="◆", font=self.f_mini, text_color=F.ACC, width=12, height=20).pack(side="left")
        ctk.CTkLabel(kopf, text=tr(titel).upper(), font=self.f_h, text_color=F.GOLD,
                     anchor="w", height=20).pack(side="left", padx=(6, 0))
        ctk.CTkFrame(kopf, height=1, fg_color=F.ACC_DIM).pack(side="left", fill="x", expand=True, padx=(10, 0))
    if hinweis:
        ctk.CTkLabel(k, text=hinweis, font=self.f_klein, text_color=F.MUTED, anchor="w",
                     justify="left", height=18).pack(fill="x", padx=16, pady=(0, 2))
    return k


def _zeile(self, karte, titel, hilfe=None, erste=False):
    ctk, F = _bot.ctk, _bot.F
    if not erste:
        ctk.CTkFrame(karte, height=1, fg_color=F.RAND).pack(fill="x", padx=16)
    z = ctk.CTkFrame(karte, fg_color="transparent")
    z.pack(fill="x", padx=16, pady=8)
    z.grid_columnconfigure(0, weight=1)
    t = ctk.CTkFrame(z, fg_color="transparent")
    t.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(t, text=titel, font=self.f_fett, text_color=F.TEXT, anchor="w", height=20).pack(anchor="w")
    self._letzte_hilfe = None
    if hilfe:
        self._letzte_hilfe = ctk.CTkLabel(t, text=hilfe, font=self.f_mini, text_color=F.MUTED,
                                          anchor="w", justify="left", wraplength=330)
        self._letzte_hilfe.pack(anchor="w")
    rechts = ctk.CTkFrame(z, fg_color="transparent")
    rechts.grid(row=0, column=1, sticky="e")
    return rechts


def _schalter(self, eltern, var, command=None):
    ctk, F = _bot.ctk, _bot.F
    s = ctk.CTkCheckBox(eltern, text="", variable=var.tk, onvalue=True, offvalue=False, width=24,
                        checkbox_width=22, checkbox_height=22, corner_radius=3, border_width=2,
                        border_color=F.ACC_DIM, fg_color=F.ACC, hover_color=F.ACC_H,
                        checkmark_color=F.AUF_ACC, command=command)
    s.pack(side="left", padx=(14, 0))
    return s


def _knopf(self, eltern, text, command, primaer=False, breite=110):
    ctk, F = _bot.ctk, _bot.F
    if primaer:
        farben = dict(fg_color=F.ACC, hover_color=F.ACC_H, text_color=F.AUF_ACC, border_width=0)
    else:
        farben = dict(fg_color=F.SEL, hover_color=F.RAND, text_color=F.TEXT, border_width=1,
                      border_color=F.ACC_DIM)
    return ctk.CTkButton(eltern, text=text, command=command, width=breite, height=30,
                         corner_radius=3, font=self.f_fett, **farben)


def _auswahl(self, eltern, var, werte, command=None, breite=230):
    ctk, F = _bot.ctk, _bot.F
    o = ctk.CTkOptionMenu(eltern, variable=getattr(var, "tk", var), values=list(werte), command=command,
                          width=breite, height=30, corner_radius=3, font=self.f_text,
                          dropdown_font=self.f_text, fg_color=F.FELD, button_color=F.ACC_DIM,
                          button_hover_color=F.ACC_H, text_color=F.TEXT,
                          dropdown_fg_color=F.CARD, dropdown_hover_color=F.SEL,
                          dropdown_text_color=F.TEXT)
    o.pack(side="left")
    return o


def _feld(self, eltern, var, vor=None, nach=None, breite=62):
    ctk, F = _bot.ctk, _bot.F
    if vor:
        ctk.CTkLabel(eltern, text=vor, font=self.f_klein, text_color=F.MUTED).pack(side="left", padx=(10, 6))
    e = ctk.CTkEntry(eltern, textvariable=var.tk, width=breite, height=30, justify="center",
                     font=self.f_text, fg_color=F.FELD, border_color=F.ACC_DIM, border_width=1,
                     text_color=F.TEXT, corner_radius=3)
    e.pack(side="left")
    if nach:
        ctk.CTkLabel(eltern, text=nach, font=self.f_klein, text_color=F.MUTED).pack(side="left", padx=(6, 0))
    return e


def _mini_bauen(self):
    """Kleine Leiste über dem Spiel: Logo, Status, Zahlen, Start/Stop."""
    ctk, F = _bot.ctk, _bot.F
    m = ctk.CTkFrame(self.root, fg_color=F.BG, corner_radius=0, border_width=1, border_color=F.ACC_DIM)
    self._mini = m
    oben = ctk.CTkFrame(m, fg_color="transparent")
    oben.pack(fill="x", padx=12, pady=(10, 8))
    try:
        self._logo_mini = ctk.CTkImage(light_image=server_logo(64), dark_image=server_logo(64), size=(24, 24))
        ctk.CTkLabel(oben, text="", image=self._logo_mini, width=24).pack(side="left")
    except Exception:
        pass
    ctk.CTkLabel(oben, text="S6", font=self.f_h, text_color=F.ACC).pack(side="left", padx=(8, 0))
    ctk.CTkLabel(oben, text=" FARMBOT", font=self.f_h, text_color=F.GOLD).pack(side="left")
    ctk.CTkButton(oben, text=tr("Vollansicht"), width=92, height=26, corner_radius=3, font=self.f_klein,
                  fg_color=F.SEL, hover_color=F.RAND, text_color=F.TEXT, border_width=1,
                  border_color=F.ACC_DIM, command=self._kompakt_umschalten).pack(side="right")
    mitte = ctk.CTkFrame(m, fg_color=F.CARD, corner_radius=3, border_width=1, border_color=F.ACC_DIM)
    mitte.pack(fill="x", padx=12)
    punkt = ctk.CTkFrame(mitte, width=10, height=10, corner_radius=5, fg_color=F.DIM)
    punkt.pack(side="left", padx=(12, 8), pady=8)
    status = ctk.CTkLabel(mitte, text="Bereit", font=self.f_fett, text_color=F.TEXT, height=20)
    status.pack(side="left", pady=8)
    self.mini_zahlen = ctk.CTkLabel(mitte, text="", font=self.f_klein, text_color=F.MUTED, height=20)
    self.mini_zahlen.pack(side="right", padx=12, pady=8)
    self._status_punkte.append(punkt)
    self._status_labels.append(status)
    knopf = ctk.CTkButton(m, text="▶   START", height=40, corner_radius=3, font=self.f_btn,
                          fg_color=F.GREEN, hover_color=F.GREEN_H, text_color="#04130a",
                          command=self._start_stop_knopf)
    knopf.pack(fill="x", padx=12, pady=8)
    self._start_knoepfe.append(knopf)
    self.mini_meldung = ctk.CTkLabel(m, text="", font=self.f_mini, text_color=F.MUTED, anchor="w", height=16)
    self.mini_meldung.pack(fill="x", padx=14, pady=(0, 8))


def _log_tags(self, box):
    F = _bot.F
    for name, farbe in (("ok", F.GREEN), ("warn", "#f0883e"), ("fehler", "#ff5a5a"),
                        ("buff", F.GOLD), ("info", F.MUTED), ("ziel", "#7cc4ff")):
        try:
            box.tag_config(name, foreground=farbe)
        except Exception:
            pass


# ---------- Protokoll (übersetzt angezeigt, Datei bleibt deutsch) ----------
def _log_zeile(self, text, _puffer=True):
    if _puffer:
        if not hasattr(self, "_s6_puffer"):
            self._s6_puffer = collections.deque(maxlen=300)
        self._s6_puffer.append((time.strftime("%H:%M:%S  "), text))
    zeit = time.strftime("%H:%M:%S  ") if _puffer is True else _puffer
    anzeige = tr(text)
    zeile = zeit + anzeige + "\n"
    tag = self._log_tag(text)
    for box, maxi in ((self.log_box, 1000), (self.akt_box, 60)):
        try:
            box.configure(state="normal")
            box.insert("end", zeile, tag) if tag else box.insert("end", zeile)
            if int(box.index("end-1c").split(".")[0]) > maxi:
                box.delete("1.0", f"{maxi // 4 + 1}.0")
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            pass
    try:
        self.mini_meldung.configure(text=anzeige if len(anzeige) <= 58 else anzeige[:57] + "…")
    except Exception:
        pass


# ---------- Sprache ----------
def _sprache_wechseln(self, anzeige):
    code = {n: c for c, n in i18n.SPRACHEN}.get(anzeige, "de")
    if code == i18n.sprache():
        return
    if self.laeuft:
        self.log("Erst den Bot stoppen, dann die Sprache wechseln.")
        try:
            self._s6_sprache.set(i18n.name())
        except Exception:
            pass
        return
    i18n.setzen(code, merken=True)
    self.root.after(30, self._neu_aufbauen)


def _neu_aufbauen(self):
    """Oberfläche in der neuen Sprache neu bauen. Variablen und Bot bleiben erhalten."""
    seite = self._seite or "dashboard"
    if self._kompakt:
        self._kompakt_umschalten()
    ov = getattr(self, "_s6_overlay", None)
    behalten = {id(ov.fenster)} if ov is not None and ov.fenster is not None else set()
    for w in list(self.root.winfo_children()):
        if id(w) in behalten:
            continue
        try:
            w.destroy()
        except Exception:
            pass
    self._pn_fenster = None
    self._fb_fenster = None
    self._txt = {}
    self._refresh = []
    self._seiten = {}
    self._nav_btn = {}
    self._profil_btn = {}
    self._seite = None
    self._status_punkte = []
    self._status_labels = []
    self._start_knoepfe = []
    self._img_cache = {}
    self._ui_bauen()
    for f in list(self._refresh):
        try:
            f()
        except Exception:
            pass
    for schritt in ("_info_aktualisieren", "_profil_knoepfe", "_revive_anzeige", "_discord_knopf_zeigen"):
        try:
            getattr(self, schritt)()
        except Exception:
            pass
    self._status(self.laeuft)
    self._seite_zeigen(seite)
    for zeit, text in list(getattr(self, "_s6_puffer", [])):
        _log_zeile(self, text, _puffer=zeit)
    try:
        self.root.title(_bot.APP_NAME)
    except Exception:
        pass


# ============================================================
#  Overlay im Spielfenster
# ============================================================
def _overlay(app):
    ov = getattr(app, "_s6_overlay", None)
    if ov is None:
        ov = app._s6_overlay = Overlay(app)
    return ov


class Overlay:
    """Kleine Anzeige über dem Spiel. Klicks gehen hindurch (WS_EX_TRANSPARENT) und
    Bildschirmaufnahmen sehen sie nicht (WDA_EXCLUDEFROMCAPTURE), damit die
    Bilderkennung des Bots unverändert bleibt. Ohne diesen Schutz wird nichts gezeigt."""

    MIN_BREITE = 236

    def __init__(self, app):
        self.app = app
        self.fenster = None
        self.geht = os.name == "nt"
        self._sichtbar = False
        self._labels = {}
        self._position_datei = Path(_bot._ORDNER) / "overlay-position.json"
        self._position = self._position_laden()
        self._spiel = None
        self._verschieben = False
        self._drag = None

    def _bauen(self):
        ctk, F = _bot.ctk, _bot.F
        # Bewusst ein einfaches Tk-Fenster: CTkToplevel blendet sich unter Windows selbst ein und aus.
        w = _bot.tk.Toplevel(self.app.root)
        w.withdraw()
        w.overrideredirect(True)
        w.configure(bg=F.BG)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.9)
        rahmen = ctk.CTkFrame(w, fg_color=F.BG, corner_radius=0, border_width=1, border_color=F.ACC)
        rahmen.pack(fill="both", expand=True)
        oben = ctk.CTkFrame(rahmen, fg_color=F.SIDE, corner_radius=0, height=22)
        oben.pack(fill="x", padx=1, pady=(1, 0))
        try:
            self._logo = ctk.CTkImage(light_image=server_logo(64), dark_image=server_logo(64), size=(16, 16))
            ctk.CTkLabel(oben, text="", image=self._logo, width=16).pack(side="left", padx=(6, 4))
        except Exception:
            pass
        schrift_k = ctk.CTkFont(family="Bahnschrift" if os.name == "nt" else "DejaVu Sans", size=12, weight="bold")
        schrift = ctk.CTkFont(family="Segoe UI" if os.name == "nt" else "DejaVu Sans", size=11)
        ctk.CTkLabel(oben, text="S6", font=schrift_k, text_color=F.ACC, height=20).pack(side="left")
        ctk.CTkLabel(oben, text=" FARMBOT", font=schrift_k, text_color=F.GOLD, height=20).pack(side="left")
        ctk.CTkLabel(oben, text=SERVER[_produkt]["name"].upper(), font=schrift, text_color=F.DIM,
                     height=20).pack(side="right", padx=6)
        mitte = ctk.CTkFrame(rahmen, fg_color="transparent")
        mitte.pack(fill="x", padx=8, pady=(5, 0))
        self._punkt = ctk.CTkFrame(mitte, width=8, height=8, corner_radius=4, fg_color=F.DIM)
        self._punkt.pack(side="left", padx=(0, 6))
        self._labels["status"] = ctk.CTkLabel(mitte, text="", font=schrift_k, text_color=F.TEXT, height=18)
        self._labels["status"].pack(side="left")
        self._labels["zeit"] = ctk.CTkLabel(mitte, text="", font=schrift, text_color=F.MUTED, height=18)
        self._labels["zeit"].pack(side="right")
        unten = ctk.CTkFrame(rahmen, fg_color="transparent")
        unten.pack(fill="x", padx=8, pady=(1, 6))
        self._labels["zahlen"] = ctk.CTkLabel(unten, text="", font=schrift, text_color=F.TEXT,
                                             height=18, anchor="w", justify="left")
        self._labels["zahlen"].pack(side="left")
        # Tk übernimmt die angeforderte Größe der DPI-skalierten Widgets.
        w.minsize(self.MIN_BREITE, 1)
        w.geometry("+-2000+-2000")
        w.deiconify()
        w.update_idletasks()
        if not self._schuetzen(w):
            w.destroy()
            self.geht = False
            self.app.log("[i] Overlay nicht verfügbar (Windows zu alt).")
            return
        w.bind("<ButtonPress-1>", self._ziehen_start)
        w.bind("<B1-Motion>", self._ziehen)
        w.bind("<ButtonRelease-1>", self._ziehen_ende)
        w.withdraw()
        self.fenster = w
        self._klickschutz()

    def _schuetzen(self, w):
        try:
            user32 = ctypes.windll.user32
            hwnd = int(w.wm_frame(), 16)
            if not user32.SetWindowDisplayAffinity(hwnd, 0x11):      # WDA_EXCLUDEFROMCAPTURE
                return False
            stil = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, stil | 0x80000 | 0x20 | 0x80 | 0x08000000)
            return True
        except Exception:
            return False

    def _position_laden(self):
        try:
            position = json.loads(self._position_datei.read_text("utf-8"))
            if (isinstance(position, list) and len(position) == 2
                    and all(type(n) in (float, int) and 0 <= n <= 1 for n in position)):
                return tuple(position)
        except (OSError, ValueError):
            pass
        return None

    def _platz(self):
        x, y, breite, hoehe = self._spiel
        f = self.fenster
        return x, y, max(0, breite - max(self.MIN_BREITE, f.winfo_reqwidth())), max(0, hoehe - f.winfo_reqheight())

    def _klickschutz(self):
        if self.fenster is None:
            return
        user32 = ctypes.windll.user32
        hwnd = int(self.fenster.wm_frame(), 16)
        stil = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, stil & ~0x20 if self._verschieben else stil | 0x20)
        self.fenster.configure(cursor="fleur" if self._verschieben else "")

    def verschieben(self):
        if not self.geht:
            return
        self._verschieben = not self._verschieben
        if self._verschieben:
            self.app._s6_overlay_an.set(True)
        self._klickschutz()
        self._verschiebe_knopf()

    def _verschiebe_knopf(self):
        knopf = getattr(self.app, "_s6_overlay_knopf", None)
        if knopf is not None:
            F = _bot.F
            knopf.configure(text="Overlay jetzt ziehen" if self._verschieben else "Overlay verschieben",
                            fg_color=F.ACC_DIM if self._verschieben else F.CARD)

    def _ziehen_start(self, ereignis):
        if self._verschieben and self._spiel is not None:
            f = self.fenster
            self._drag = ereignis.x_root - f.winfo_rootx(), ereignis.y_root - f.winfo_rooty()
            f.grab_set()

    def _ziehen(self, ereignis):
        if self._drag is None:
            return
        x, y, platz_x, platz_y = self._platz()
        links = min(platz_x, max(0, ereignis.x_root - self._drag[0] - x))
        oben = min(platz_y, max(0, ereignis.y_root - self._drag[1] - y))
        self._position = (links / platz_x if platz_x else 0, oben / platz_y if platz_y else 0)
        self.fenster.geometry(f"+{x + links}+{y + oben}")

    def _ziehen_ende(self, ereignis):
        if self._drag is None:
            return
        self._ziehen(ereignis)
        self._drag = None
        self.fenster.grab_release()
        self._verschieben = False
        self._klickschutz()
        self._verschiebe_knopf()
        tmp = self._position_datei.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._position), "utf-8")
            tmp.replace(self._position_datei)
        except OSError:
            self.app.log("[!] Die Overlay-Position konnte nicht gespeichert werden.")

    def weg(self):
        if self.fenster is not None:
            try:
                self.fenster.destroy()
            except Exception:
                pass
        self.fenster = None

    def _verstecken(self):
        if self.fenster is not None and self._sichtbar:
            if self._drag is not None:
                self.fenster.grab_release()
                self._drag = None
            self.fenster.withdraw()
            self._sichtbar = False

    def aktualisieren(self):
        an = bool(getattr(self.app, "_s6_overlay_an", None) and self.app._s6_overlay_an.get())
        if not an or not self.geht:
            self._verstecken()
            return
        import win32gui
        treffer = _bot.fenster_von_titel(_bot.FENSTER_TITEL[0])
        if not treffer:
            self._verstecken()
            return
        hwnd = treffer[0]
        vorne = win32gui.GetForegroundWindow()
        eigene = {getattr(self.app, "_hwnd", None)}
        if win32gui.IsIconic(hwnd) or (vorne != hwnd and vorne not in eigene):
            self._verstecken()
            return
        if self.fenster is None:
            self._bauen()
            if self.fenster is None:
                return
        x, y = win32gui.ClientToScreen(hwnd, (0, 0))
        _, _, breite, hoehe = win32gui.GetClientRect(hwnd)
        self._spiel = x, y, breite, hoehe
        angeln = _produkt == "verzum" and hasattr(self.app, "_angel_ansicht") and self.app._angel_ansicht()
        self._inhalt_setzen(angeln)
        if self._drag is None:
            self.fenster.update_idletasks()
            _, _, platz_x, platz_y = self._platz()
            if self._position is None:
                dx, dy = min(12, platz_x), min(round(hoehe * 0.28), platz_y)
            else:
                dx, dy = round(platz_x * self._position[0]), round(platz_y * self._position[1])
            self.fenster.geometry(f"+{x + dx}+{y + dy}")
        if not self._sichtbar:
            self.fenster.deiconify()
            self.fenster.attributes("-topmost", True)
            self._sichtbar = True

    def _inhalt_setzen(self, angeln):
        F, app = _bot.F, self.app
        if app.laeuft:
            if angeln and app._angel_wartet:
                farbe, status = F.ACC, tr("Angeln wartet")
            else:
                farbe, status = F.GREEN, tr("Angeln" if angeln else "Läuft")
        elif app.lauf_start:
            farbe, status = F.RED, tr("Gestoppt")
        else:
            farbe, status = F.DIM, tr("Bereit")
        jetzt = time.time()
        gleicher_modus = _produkt != "verzum" or angeln == getattr(app, "_angel_lauf", False)
        lauf_start = app.lauf_start if gleicher_modus else 0
        dauer = (jetzt if app.laeuft else app.lauf_ende) - lauf_start if lauf_start else 0
        if angeln:
            faenge = app._angel_stat[0] if gleicher_modus else 0
            runden, rate = app._angel_rundenzahl(dauer)
            rate_text = f"{rate:.0f}" if rate is not None else "…"
            zahlen = (f"{tr('Angelrunden')}: {runden}   ·   {tr('Fänge')}: {faenge}\n"
                      f"{tr('Angelrunden pro Stunde')}: {rate_text}")
        else:
            k = app.auto.kills if gleicher_modus else 0
            rate = k / dauer * 3600 if dauer >= 60 and k else 0
            zahlen = f"{tr('Metins')}: {k}   ·   {rate:.0f}/h"
        neu = {"status": status.upper(), "zeit": app._dauer(dauer) if lauf_start else "", "zahlen": zahlen}
        for name, text in neu.items():
            if self._labels[name].cget("text") != text:
                self._labels[name].configure(text=text)
        if self._punkt.cget("fg_color") != farbe:
            self._punkt.configure(fg_color=farbe)
