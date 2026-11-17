"""Sprachen für Launcher und Bots.

Die Oberfläche ist auf Deutsch geschrieben. Für die anderen Sprachen wird jeder Text,
der auf dem Bildschirm landet (Labels, Knöpfe, Fenstertitel, Protokollanzeige), über
tr() übersetzt. Schlüssel ist immer der deutsche Text; "{}" steht für variable Teile.
Die Logdatei bleibt deutsch, damit Fehlermeldungen für den Support lesbar bleiben.
"""
import os
from pathlib import Path
import re

SPRACHEN = (("de", "Deutsch"), ("en", "English"), ("tr", "Türkçe"), ("ru", "Русский"), ("pl", "Polski"))
_REIHE = {"en": 0, "tr": 1, "ru": 2, "pl": 3}

_sprache = "de"
_exakt = {}
_muster = []
_cache = {}
_hoerer = []


def _datei():
    basis = os.environ.get("LOCALAPPDATA")
    if not basis:
        return None
    return Path(basis) / "SiroSix" / "sprache.txt"


def gespeichert():
    """Gespeicherte Sprache (vom Launcher oder Bot gewählt), sonst Systemsprache."""
    try:
        datei = _datei()
        if datei and datei.is_file():
            code = datei.read_text("utf-8").strip()
            if code in dict(SPRACHEN):
                return code
    except OSError:
        pass
    return systemsprache()


def systemsprache():
    try:
        import ctypes
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x07: "de", 0x09: "en", 0x1F: "tr", 0x19: "ru", 0x15: "pl"}.get(lcid, "en")
    except Exception:
        return "de"


def speichern(code):
    try:
        datei = _datei()
        if datei:
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_text(code, "utf-8")
    except OSError:
        pass


def sprache():
    return _sprache


def name(code=None):
    return dict(SPRACHEN).get(code or _sprache, "Deutsch")


def setzen(code, merken=False):
    global _sprache
    if code not in dict(SPRACHEN):
        code = "de"
    _sprache = code
    _laden()
    if merken:
        speichern(code)
    for f in list(_hoerer):
        try:
            f(code)
        except Exception:
            pass


def bei_wechsel(funktion):
    _hoerer.append(funktion)


def _laden():
    global _exakt, _muster
    _cache.clear()
    _exakt, _muster = {}, []
    if _sprache == "de":
        return
    from .texte import TEXTE
    spalte = _REIHE[_sprache]
    for de, werte in TEXTE.items():
        ziel = werte[spalte] if spalte < len(werte) else None
        if not ziel:
            continue
        if "{}" in de:
            teile = [re.escape(t) for t in de.split("{}")]
            regex = re.compile("^" + "(.*?)".join(teile) + "$", re.S)
            _muster.append((len(de.replace("{}", "")), regex, ziel))
        else:
            _exakt[de] = ziel
    _muster.sort(key=lambda m: -m[0])


def _vorlage(text):
    for _laenge, regex, ziel in _muster:
        m = regex.match(text)
        if m:
            werte = [tr(g) if g and not re.fullmatch(r"[\d\s.,:%/+\-x~()]*", g) else g for g in m.groups()]
            if re.search(r"\{\d\}", ziel):
                # Andere Reihenfolge in der Zielsprache: {0}, {1} ...
                return re.sub(r"\{(\d)\}", lambda t: werte[int(t.group(1))] if int(t.group(1)) < len(werte) else "", ziel)
            stuecke = ziel.split("{}")
            aus = stuecke[0]
            for i, rest in enumerate(stuecke[1:]):
                aus += (werte[i] if i < len(werte) else "") + rest
            return aus
    return None


# Alte Markentexte aus den Bots, in jeder Sprache durch den neuen Namen ersetzt.
MARKE = {
    "SiroSix Verzum Bot · programmiert von SiroSix": "S6 Farmbot · Verzum",
    "SiroSix Metin Bot · programmiert von SiroSix": "S6 Farmbot · Rubinum Classic",
    "SiroSix Rubinum Bot · programmiert von SiroSix": "S6 Farmbot · Rubinum Classic",
    "Discord: SiroSix schreiben": "Discord",
    "Feedback an SiroSix": "Feedback",
    "Danke! Deine Meldung ist bei SiroSix angekommen.": "Danke! Deine Meldung ist angekommen.",
    "[OK] Feedback an SiroSix gesendet.": "[OK] Feedback gesendet.",
    "Dieser SiroSix Bot läuft bereits.": "Dieser S6 Farmbot läuft bereits.",
    "Bitte zuerst im SiroSix Launcher mit Discord anmelden.": "Bitte zuerst im S6 Launcher mit Discord anmelden.",
    "SiroSix Launcher": "S6 Launcher",
    "Willkommen bei SiroSix": "Willkommen bei S6",
    "SiroSix Update": "S6 Update",
    "Du bist nicht mehr auf dem SiroSix Discord.": "Du bist nicht mehr auf dem S6 Discord.",
}


def tr(text):
    """Text in die aktive Sprache übersetzen. Unbekanntes bleibt wie es ist."""
    if not isinstance(text, str) or not text.strip():
        return text
    if _sprache == "de":
        return MARKE.get(text, text)
    try:
        return _cache[text]
    except KeyError:
        pass
    aus = _exakt.get(text)
    if aus is None and text in MARKE:
        aus = tr(MARKE[text]) if MARKE[text] != text else MARKE[text]
    if aus is None:
        kern = text.strip()
        if kern != text and kern in _exakt:
            aus = text.replace(kern, _exakt[kern])
    if aus is None and "\n" in text:
        zeilen = text.split("\n")
        neu = [tr(z) for z in zeilen]
        if neu != zeilen:
            aus = "\n".join(neu)
    if aus is None:
        aus = _vorlage(text)
    if aus is None:
        aus = text
    if len(_cache) > 4000:
        _cache.clear()
    _cache[text] = aus
    return aus


# ---------- Einbau in customtkinter ----------
_installiert = False


def installieren(ctk):
    """Alle Texte, die customtkinter-Widgets anzeigen, laufen ab jetzt über tr()."""
    global _installiert
    if _installiert:
        return
    _installiert = True

    def text_klasse(klasse):
        init_alt, conf_alt = klasse.__init__, klasse.configure

        def init(self, *args, **kw):
            if isinstance(kw.get("text"), str):
                kw["text"] = tr(kw["text"])
            init_alt(self, *args, **kw)

        def configure(self, require_redraw=False, **kw):
            if isinstance(kw.get("text"), str):
                kw["text"] = tr(kw["text"])
            return conf_alt(self, require_redraw=require_redraw, **kw)
        klasse.__init__ = init
        klasse.configure = configure

    for name_ in ("CTkLabel", "CTkButton", "CTkCheckBox", "CTkSwitch", "CTkRadioButton"):
        klasse = getattr(ctk, name_, None)
        if klasse is not None:
            text_klasse(klasse)

    seg = getattr(ctk, "CTkSegmentedButton", None)
    if seg is not None:
        seg_neu_alt = seg._create_button

        def _create_button(self, index, value):
            knopf = seg_neu_alt(self, index, value)
            try:
                knopf.configure(text=tr(value))
            except Exception:
                pass
            return knopf
        seg._create_button = _create_button

    for name_ in ("CTk", "CTkToplevel"):
        klasse = getattr(ctk, name_, None)
        if klasse is None:
            continue
        titel_alt = klasse.title

        def title(self, string=None, _alt=titel_alt):
            return _alt(self, tr(string) if isinstance(string, str) else string)
        klasse.title = title

    try:
        from tkinter import messagebox

        for name_ in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel"):
            alt = getattr(messagebox, name_)

            def neu(title=None, message=None, _alt=alt, **kw):
                return _alt(tr(title) if title else title, tr(message) if message else message, **kw)
            setattr(messagebox, name_, neu)
    except Exception:
        pass


def pystray_installieren(pystray):
    alt = pystray.MenuItem.__init__

    def init(self, text, *args, **kw):
        alt(self, tr(text) if isinstance(text, str) else text, *args, **kw)
    pystray.MenuItem.__init__ = init
