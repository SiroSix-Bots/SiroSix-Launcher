import unittest
from unittest.mock import patch
import io
import json
import hashlib
import tempfile
from pathlib import Path
from sirosix.updates import check_release, version_tuple, apply_update


class UpdateTests(unittest.TestCase):
    def release(self, **asset):
        return {"tag_name": "v0.2.0", "assets": [{"name": "SiroSix-Launcher.exe", "size": 1024,
                "digest": "sha256:" + "a" * 64,
                "browser_download_url": "https://github.com/SiroSix-Bots/SiroSix-Launcher/releases/download/v0.2.0/SiroSix-Launcher.exe", **asset}]}

    def check(self, release):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
            return check_release()

    def test_numeric_comparison_and_wrong_versions(self):
        self.assertGreater(version_tuple("v0.10.0"), version_tuple("0.2.0"))
        for value in ("latest", "1.0", "../1.2.3", "1.2.3-beta"):
            with self.assertRaises(ValueError):
                version_tuple(value)

    def test_only_verified_official_release_asset_is_accepted(self):
        self.assertEqual(self.check(self.release())["version"], "v0.2.0")
        for changes in ({"digest": None}, {"digest": "sha256:wrong"}, {"browser_download_url": "https://evil.test/app.exe"}, {"size": 200 * 1024 * 1024}):
            with self.subTest(changes=changes), self.assertRaises((RuntimeError, TypeError)):
                self.check(self.release(**changes))

    def test_prerelease_and_old_release_are_ignored(self):
        self.assertIsNone(self.check({**self.release(), "prerelease": True}))
        self.assertIsNone(self.check({**self.release(), "tag_name": "v0.1.0"}))

    def test_verified_update_preserves_previous_exe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "download").mkdir()
            source, target = root / "download/SiroSix-Launcher.exe", root / "SiroSix-Launcher.exe"
            source.write_bytes(b"MZ-new")
            target.write_bytes(b"MZ-old")
            with patch("subprocess.Popen"):
                apply_update(source, target, 0, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(target.read_bytes(), b"MZ-new")
            self.assertEqual((root / "SiroSix-Launcher.previous.exe").read_bytes(), b"MZ-old")

    def test_update_rolls_back_when_restart_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "download").mkdir()
            source, target = root / "download/SiroSix-Launcher.exe", root / "SiroSix-Launcher.exe"
            source.write_bytes(b"MZ-new")
            target.write_bytes(b"MZ-old")
            with patch("subprocess.Popen", side_effect=OSError("Test")), self.assertRaises(OSError):
                apply_update(source, target, 0, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(target.read_bytes(), b"MZ-old")
