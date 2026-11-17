# SiroSix Launcher · S6

Windows-Launcher mit Discord-Anmeldung und einer Tool-Bibliothek. Ein Klick auf einen Tool-Namen öffnet seine Detailansicht. Die Liste wird nach der Anmeldung aus dem Lizenzserver geladen.

Angezeigt werden Lizenzstatus und Laufzeit, Client-Anzahl, aktuelle und installierte Version, PC-Bindung und kostenloser PC-Wechsel. Der eigene HWID-Hash lässt sich für Supportfälle kopieren; Hardware-Rohdaten werden nicht kopiert.

## Startablauf

Der feste Startknopf ist nur mit aktiver Lizenz und veröffentlichter Produktversion verfügbar. Vor dem Öffnen prüft der Launcher nacheinander:

1. Lizenz und PC-Freigabe beim Server.
2. Aktuell verfügbare Produktversion.
3. Vorhandene Installation einschließlich Dateiprüfsummen und Systemvoraussetzungen (.NET Runtime 10 für Verzum).
4. Download, falls die aktuelle Version noch nicht installiert ist.
5. Paket-Prüfsumme, Produktmanifest und Installation.
6. Öffnen des Tools; erforderliche Windows-UAC-Abfragen bestätigt der Nutzer selbst.

Eine vollständige unveränderte Installation wird nach der Prüfung ohne erneuten Download gestartet. Fehler stoppen den Ablauf und bleiben mit einer Erklärung im Ladebildschirm sichtbar. Beschädigte vorhandene Installationen werden gesperrt; eine automatische Reparatur ist noch nicht implementiert.

## Lokal ausführen

Python 3.12 unter Windows, Abhängigkeiten siehe `requirements.txt`.

```text
python main.py
python main.py --demo
python main.py --demo --demo-loading
python -m unittest discover -s tests -v
python build_windows.py
```

Die Vorschau verwendet ausdrücklich Beispieldaten und führt keine Anmeldung, Downloads oder Spiel-Eingaben aus. Die Tool-Auswahl funktioniert auch in der Vorschau.

Nuitka erzeugt `../builds/launcher/SiroSix-Launcher.exe`. LTO ist für kürzere und reproduzierbare lokale Builds ausgeschaltet. Die Ausgabe muss anschließend auf Windows gestartet und geprüft werden. Eine erfolgreich erzeugte EXE allein bestätigt keinen vollständigen Produktstart.

## Speicherung und Grenzen

- Sitzung: `%LOCALAPPDATA%/SiroSix/sitzung.dpapi`, verschlüsselt für das aktuelle Windows-Konto.
- Produkte: `%LOCALAPPDATA%/SiroSix/products/<produkt>/<version>`.
- Updates: `%LOCALAPPDATA%/SiroSix/updates`.
- Sitzungsschlüssel werden nicht als Prozessargument oder URL weitergereicht.
- Der Bot prüft seine signierte Freigabe zusätzlich selbst. Die Oberfläche ersetzt keine serverseitige Lizenzkontrolle.
- PC-Wechsel ist eine ausdrückliche Aktion und wird vor dem Verbrauch des kostenlosen Wechsels bestätigt.
- Es gibt noch keinen veröffentlichten Launcher-Release oder hochgeladenes Bot-Paket. Die vollständige Produktkette und ein echter Release-Wechsel müssen separat live geprüft werden.
- Der technische Datenschutzhinweis ist noch keine vollständige Erklärung für einen öffentlichen Verkaufsstart.
