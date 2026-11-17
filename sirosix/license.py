"""Signierte Freigaben mit monotonichem Ablauf und Windows-Suspend-Erkennung."""
import base64
import ctypes
import json
import math
import threading
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from .api import PUBLIC_KEY, ApiError, NetworkError

MAX_LEASE_MS = 2 * 3600 * 1000
RENEW_SECONDS = 10 * 60


def elapsed_clock():
    # GetTickCount64 zählt Standby-Zeit mit. Ein Neustart erfordert eine neue Freigabe.
    if hasattr(ctypes, "windll"):
        fn = ctypes.windll.kernel32.GetTickCount64
        fn.restype = ctypes.c_ulonglong
        return fn() / 1000.0
    return time.monotonic()


def unb64(value):
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class LeaseError(Exception):
    pass


class Lease:
    def __init__(self, response, product, hwid, user_id, *, public_key=PUBLIC_KEY,
                 received_at=None, request_started=None, clock=elapsed_clock):
        self.clock = clock
        now = clock() if received_at is None else received_at
        try:
            payload, signature = response["schluessel"].split(".")
            Ed25519PublicKey.from_public_bytes(unb64(public_key)).verify(unb64(signature), payload.encode("ascii"))
            claims = json.loads(unb64(payload))
            if claims.get("v") != 1 or claims.get("p") != product or claims.get("h") != hwid or claims.get("sub") != user_id:
                raise ValueError("Falsche Bindung")
            issued, expires = claims["iat"], claims["exp"]
            if any(type(x) is not int for x in (issued, expires)) or issued < 0 or not 0 < expires - issued <= MAX_LEASE_MS:
                raise ValueError("Ungültige Laufzeit")
            if type(claims.get("s")) is not int or not 1 <= claims["s"] <= 4:
                raise ValueError("Ungültige Slots")
            end = claims.get("lab")
            if end is not None:
                if type(end) is not int or end <= issued:
                    raise ValueError("Ungültiges Lizenzende")
                expires = min(expires, end)
            # Nur signierte Zeitwerte bestimmen die Frist. Transportzeit abziehen.
            delay = max(0.0, now - request_started) if request_started is not None else 0.0
            self.deadline = now + (expires - issued) / 1000.0 - delay
            self.claims = claims
            if not math.isfinite(self.deadline) or self.deadline <= now:
                raise ValueError("Abgelaufen")
        except (KeyError, ValueError, TypeError, InvalidSignature, UnicodeError):
            raise LeaseError("Die Lizenzfreigabe ist ungültig oder abgelaufen.") from None

    def remaining(self):
        return max(0.0, self.deadline - self.clock())

    def valid(self):
        return self.remaining() > 0


class LicenseGuard:
    def __init__(self, api, product, hwid, user_id, on_stop, on_status=lambda text: None,
                 *, clock=elapsed_clock, public_key=PUBLIC_KEY):
        self.api, self.product, self.hwid, self.user_id = api, product, hwid, user_id
        self.on_stop, self.on_status = on_stop, on_status
        self.clock, self.public_key = clock, public_key
        self.lease = None
        self.closed = threading.Event()
        self.denied = False
        self.next_refresh = 0
        self.lock = threading.RLock()

    def refresh(self):
        started = self.clock()
        reply = self.api.grant(self.product, self.hwid)
        lease = Lease(reply, self.product, self.hwid, self.user_id, clock=self.clock,
                      request_started=started, public_key=self.public_key)
        with self.lock:
            if self.denied:
                raise LeaseError("Die Freigabe wurde beendet. Bitte den Bot neu starten.")
            self.lease = lease
        self.next_refresh = self.clock() + RENEW_SECONDS
        self.on_status("Lizenz bestätigt")

    def valid(self):
        with self.lock:
            return not self.denied and self.lease is not None and self.lease.valid()

    def deny(self, message):
        with self.lock:
            if self.denied:
                return
            self.denied = True
        self.on_stop(message)

    def start(self):
        self.refresh()  # Bei jedem Prozessstart einmal online, keine wiederverwendete Offline-Uhr.
        self.next_refresh = self.clock() + RENEW_SECONDS
        threading.Thread(target=self._renew_loop, daemon=True, name="SiroSix-Lizenz").start()
        threading.Thread(target=self._expiry_loop, daemon=True, name="SiroSix-Ablauf").start()

    def _expiry_loop(self):
        while not self.closed.wait(0.2):
            if not self.valid():
                self.deny("Die Lizenzfreigabe ist abgelaufen. Alle Eingaben wurden beendet.")
                return

    def _renew_loop(self):
        while not self.closed.wait(1):
            if self.denied:
                return
            if self.clock() < self.next_refresh:
                continue
            try:
                self.refresh()
            except ApiError as e:
                if e.status in (400, 401, 403, 404, 409, 410):
                    self.deny(str(e))
                    return
                self._offline()
            except NetworkError:
                self._offline()
            except LeaseError as e:
                self.deny(str(e))
                return
            except Exception:
                self.deny("Die Lizenzprüfung konnte nicht sicher abgeschlossen werden.")
                return

    def _offline(self):
        self.next_refresh = self.clock() + 30
        remaining = self.lease.remaining() if self.lease else 0
        self.on_status(f"Server nicht erreichbar, Freigabe noch {math.ceil(remaining / 60)} Minuten gültig")

    def close(self):
        self.closed.set()
        with self.lock:
            self.denied = True
