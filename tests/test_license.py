import base64
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sirosix.license import Lease, LeaseError, LicenseGuard


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


class Clock:
    def __init__(self):
        self.value = 1000.0
    def __call__(self):
        return self.value


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = b64(self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        self.claims = {"v": 1, "sub": "1001", "p": "verzum", "h": "a" * 64,
                       "s": 1, "iat": 100000, "exp": 7300000, "lab": None}
        self.clock = Clock()

    def reply(self, **overrides):
        claims = {**self.claims, **overrides}
        payload = b64(json.dumps(claims).encode())
        return {"schluessel": payload + "." + b64(self.key.sign(payload.encode())), "serverzeit": 0}

    def lease(self, response=None, **kwargs):
        return Lease(response or self.reply(), "verzum", "a" * 64, "1001", public_key=self.public,
                     clock=self.clock, **kwargs)

    def test_server_signed_time_and_elapsed_time_bound_two_hours(self):
        lease = self.lease(request_started=998)
        self.assertEqual(lease.remaining(), 7198)
        self.clock.value += 7199
        self.assertFalse(lease.valid())

    def test_product_pc_user_and_schema_are_bound(self):
        for changed in ({"p": "rubinum"}, {"h": "b" * 64}, {"sub": "someone"}, {"v": 2}):
            with self.subTest(changed=changed), self.assertRaises(LeaseError):
                self.lease(self.reply(**changed))

    def test_tampering_or_another_key_fails(self):
        response = self.reply()
        payload, sig = response["schluessel"].split(".")
        changed = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        changed["s"] = 4
        response["schluessel"] = b64(json.dumps(changed).encode()) + "." + sig
        with self.assertRaises(LeaseError):
            self.lease(response)

    def test_rejects_overlong_negative_and_non_numeric_claims(self):
        for changed in ({"exp": 7300001}, {"exp": 90000}, {"exp": "7300000"}, {"iat": True}, {"s": 0}, {"s": 5}, {"lab": 99999}):
            with self.subTest(changed=changed), self.assertRaises(LeaseError):
                self.lease(self.reply(**changed))

    def test_license_expiry_caps_offline_grace(self):
        lease = self.lease(self.reply(lab=160000))
        self.assertEqual(lease.remaining(), 60)
        self.clock.value += 60
        self.assertFalse(lease.valid())

    def test_network_delay_consumes_grace_and_unsigned_time_cannot_extend_it(self):
        response = self.reply()
        response["gueltig_bis"] = 10**20
        response["serverzeit"] = -10**20
        self.assertEqual(self.lease(response, request_started=950).remaining(), 7150)

    def test_expired_in_transit_rejected(self):
        with self.assertRaises(LeaseError):
            self.lease(self.reply(exp=101000), request_started=998)

    def test_denial_is_once_and_a_late_refresh_cannot_restart(self):
        class FakeApi:
            def grant(inner, product, hwid):
                return self.reply()
        stopped = []
        guard = LicenseGuard(FakeApi(), "verzum", "a" * 64, "1001", stopped.append,
                             clock=self.clock, public_key=self.public)
        guard.refresh()
        self.assertTrue(guard.valid())
        guard.deny("gesperrt")
        guard.deny("nochmal")
        self.assertEqual(stopped, ["gesperrt"])
        with self.assertRaises(LeaseError):
            guard.refresh()
        self.assertFalse(guard.valid())


if __name__ == "__main__":
    unittest.main()
