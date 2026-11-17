"""HTTPS-Zugriff. Zugangsdaten werden nie protokolliert oder in URLs geschrieben."""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://sirosix-server.sirosix.workers.dev"
PUBLIC_KEY = "cP_VJ8CIAigr8Z7R4wtrLwENK5Mhdjba-Ihy1iZ--ag"
DISCORD_URL = "https://discord.gg/vRmhmJRQVK"


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code = status, code
        super().__init__(message)


class NetworkError(Exception):
    pass


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl)[:2] != urllib.parse.urlsplit(req.full_url)[:2]:
            raise NetworkError("Eine unerwartete Weiterleitung wurde abgelehnt.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Api:
    def __init__(self, token=None, base_url=BASE_URL, opener=None):
        u = urllib.parse.urlsplit(base_url)
        if u.scheme != "https" or not u.netloc or u.username or u.password or u.query or u.fragment:
            raise ValueError("Der Lizenzserver muss eine HTTPS-Adresse sein.")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.opener = opener or urllib.request.build_opener(SameOriginRedirect())

    def open(self, path, data=None, method=None, timeout=20):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Ungültiger Serverpfad.")
        headers = {"User-Agent": "SiroSix-Launcher/0.1.0", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        raw = None
        if data is not None:
            raw = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=raw, headers=headers, method=method)
        try:
            return self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read(65536))
            except (ValueError, OSError):
                payload = {}
            raise ApiError(e.code, payload.get("code", "http"), payload.get("meldung", f"Serverzugriff fehlgeschlagen (HTTP {e.code}).")) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise NetworkError("Der SiroSix Server ist gerade nicht erreichbar.") from None

    def request(self, path, data=None, method=None):
        with self.open(path, data, method) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise NetworkError("Die Serverantwort ist zu groß.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise NetworkError("Der Server hat eine ungültige Antwort gesendet.") from None
        if not isinstance(result, dict):
            raise NetworkError("Der Server hat eine ungültige Antwort gesendet.")
        return result

    def me(self):
        return self.request("/ich")

    def grant(self, product, hwid):
        return self.request("/freigabe", {"produkt": product, "hwid": hwid})

    def download_info(self, product):
        if product not in ("verzum", "rubinum"):
            raise ValueError("Unbekanntes Produkt.")
        return self.request("/download/" + product)

    def file_path(self, url):
        expected, actual = urllib.parse.urlsplit(self.base_url), urllib.parse.urlsplit(url)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc) or actual.query or actual.fragment:
            raise ValueError("Download-Adresse gehört nicht zum SiroSix Server.")
        if not actual.path.startswith("/datei/") or actual.username or actual.password:
            raise ValueError("Ungültige Download-Adresse.")
        return actual.path
