import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from sirosix.api import Api
from sirosix.packages import PackageError, install_archive, download_product, checked_executable


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manifest = {"schema": 1, "product": "verzum", "version": "1.1.1", "executable": "SiroSix-Verzum-Bot.exe"}

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, extra=None, manifest=None):
        path = self.root / "payload.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("sirosix-product.json", json.dumps(manifest or self.manifest))
            bundle.writestr("SiroSix-Verzum-Bot.exe", b"MZ-Testfixture")
            for name, value in (extra or {}).items():
                bundle.writestr(name, value)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_verified_install_and_cache_and_tamper_detection(self):
        archive, sha = self.archive({"hid/test.dll": b"fixture"})
        exe = install_archive(archive, self.root / "products", "verzum", "1.1.1", sha)
        self.assertTrue(exe.is_file())
        self.assertEqual(install_archive(archive, self.root / "products", "verzum", "1.1.1", sha), exe)
        exe.write_bytes(b"MZ-changed")
        with self.assertRaises(PackageError):
            checked_executable(exe.parent, "verzum")

    def test_bad_hash_never_installs(self):
        archive, _ = self.archive()
        with self.assertRaises(PackageError):
            install_archive(archive, self.root / "products", "verzum", "1.1.1", "0" * 64)
        self.assertFalse((self.root / "products/verzum/1.1.1").exists())

    def test_rejects_traversal_windows_ads_reserved_and_case_collisions(self):
        for bad in ("../escaped.exe", "/abs.exe", "C:/evil.exe", "evil.exe:stream", "CON.txt", "trailing./a", "SIROSIX-PRODUCT.JSON"):
            with self.subTest(path=bad):
                archive, sha = self.archive({bad: b"evil"})
                with self.assertRaises(PackageError):
                    install_archive(archive, self.root / "products", "verzum", "1.1.1", sha)
        self.assertFalse((self.root / "escaped.exe").exists())

    def test_raw_windows_separator_is_rejected_before_zip_normalizes_it(self):
        archive, _ = self.archive({"hid/evil.exe": b"fixture"})
        archive.write_bytes(archive.read_bytes().replace(b"hid/evil.exe", b"hid\\evil.exe"))
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        with self.assertRaises(PackageError):
            install_archive(archive, self.root / "products", "verzum", "1.1.1", sha)

    def test_wrong_product_or_version_never_installs(self):
        for changed in ({"product": "rubinum"}, {"version": "9.9.9"}, {"executable": "unexpected.exe"}):
            archive, sha = self.archive(manifest={**self.manifest, **changed})
            with self.assertRaises(PackageError):
                install_archive(archive, self.root / "products", "verzum", "1.1.1", sha)

    def test_download_auth_is_used_and_size_and_hash_are_checked(self):
        archive, sha = self.archive()
        raw = archive.read_bytes()
        info = {"version": "1.1.1", "sha256": sha, "groesse": len(raw), "url": "https://sirosix-server.sirosix.workers.dev/datei/example"}
        class FakeApi:
            token = "test-session"
            file_path = Api().file_path
            def download_info(self, product):
                return info
            def open(inner, path):
                self.assertEqual(inner.token, "test-session")
                return io.BytesIO(raw)
        exe = download_product(FakeApi(), self.root / "products", "verzum")
        self.assertTrue(exe.exists())
        info["groesse"] += 1
        with self.assertRaises(PackageError):
            download_product(FakeApi(), self.root / "fresh-products", "verzum")

    def test_chunked_download_is_joined_and_verified(self):
        archive, sha = self.archive({"hid/test.dll": b"x" * 5000})
        raw = archive.read_bytes()
        size = 700
        chunks = [raw[i:i + size] for i in range(0, len(raw), size)]
        info = {"version": "1.1.1", "sha256": sha, "groesse": len(raw), "teile": len(chunks),
                "url": "https://sirosix-server.sirosix.workers.dev/datei/example"}
        asked = []
        class FakeApi:
            file_path = Api().file_path
            def download_info(self, product):
                return info
            def file_part(inner, path, nr):
                asked.append((path, nr))
                return chunks[nr]
            def open(inner, path):
                self.fail("Chunked packages must not use the single-file route")
        exe = download_product(FakeApi(), self.root / "products", "verzum")
        self.assertTrue(exe.exists())
        self.assertEqual(asked, [("/datei/example", i) for i in range(len(chunks))])
        chunks[1] = b"y" * len(chunks[1])
        with self.assertRaises(PackageError):
            download_product(FakeApi(), self.root / "other", "verzum")

    def test_api_decodes_base64_parts(self):
        import base64
        api = Api("t")
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        api.open = lambda path, timeout=20: Resp(base64.b64encode(b"teil-daten"))
        self.assertEqual(api.file_part("/datei/x", 3), b"teil-daten")

    def test_current_install_is_verified_without_downloading_again(self):
        archive, sha = self.archive({"hid/test.dll": b"fixture"})
        install_archive(archive, self.root / "products", "verzum", "1.1.1", sha)
        class FakeApi:
            def download_info(inner, product):
                return {"version": "1.1.1", "sha256": sha, "groesse": archive.stat().st_size}
            def open(inner, path):
                self.fail("An intact installation must not be downloaded again")
        phases = []
        exe = download_product(FakeApi(), self.root / "products", "verzum", phase=lambda name, detail: phases.append(name))
        self.assertTrue(exe.is_file())
        self.assertEqual(phases, ["updates", "files", "verify"])

    def test_server_cannot_redirect_session_to_another_host(self):
        api = Api("not-a-real-token")
        for url in ("http://sirosix-server.sirosix.workers.dev/datei/x", "https://evil.test/datei/x", "https://sirosix-server.sirosix.workers.dev/admin/x"):
            with self.assertRaises(ValueError):
                api.file_path(url)


if __name__ == "__main__":
    unittest.main()
