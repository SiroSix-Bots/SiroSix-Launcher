import os
from pathlib import Path
import tempfile
import unittest
from sirosix.windows import SecureStore, hardware_id


@unittest.skipUnless(os.name == "nt", "Windows DPAPI")
class WindowsTests(unittest.TestCase):
    def test_dpapi_roundtrip_without_plaintext(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sitzung.dpapi"
            store = SecureStore(path)
            dummy = "test-only-never-a-real-session-1234567890"
            store.save({"token": dummy})
            self.assertNotIn(dummy.encode(), path.read_bytes())
            self.assertEqual(store.load(), {"token": dummy})
            store.clear()
            self.assertIsNone(store.load())

    def test_hwid_is_stable_hash_only(self):
        first = hardware_id()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, hardware_id())


if __name__ == "__main__":
    unittest.main()
