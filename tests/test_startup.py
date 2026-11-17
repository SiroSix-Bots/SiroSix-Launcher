import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import ctypes
from sirosix.api import Api, ApiError
from sirosix.packages import PackageError
from sirosix.startup import start_product, launch_tool, ElevatedProcess
import zipfile


class StartupTests(unittest.TestCase):
    def setUp(self):
        requirements = patch("sirosix.startup.check_requirements")
        requirements.start()
        self.addCleanup(requirements.stop)

    def test_windows_elevation_is_requested_only_when_required_and_cancel_is_clear(self):
        from win32com.shell import shell
        error = ctypes.WinError(740)
        with patch("sirosix.startup.subprocess.Popen", side_effect=error), patch.object(shell, "ShellExecuteEx", return_value={"hProcess": Mock()}) as execute:
            result = launch_tool(["C:/test/tool.exe"], cwd=Path("C:/test"))
            self.assertIsInstance(result, ElevatedProcess)
            self.assertEqual(execute.call_args.kwargs["lpVerb"], "runas")
            self.assertEqual(execute.call_args.kwargs["lpFile"], "C:/test/tool.exe")
        with patch("sirosix.startup.subprocess.Popen", side_effect=error), patch.object(shell, "ShellExecuteEx", side_effect=ctypes.WinError(1223)):
            with self.assertRaisesRegex(RuntimeError, "abgebrochen"):
                launch_tool(["C:/test/tool.exe"], cwd=Path("C:/test"))

    def test_elevated_process_handle_is_closed_after_exit(self):
        handle = Mock()
        process = ElevatedProcess(handle)
        with patch("win32process.GetExitCodeProcess", side_effect=[259, 0]):
            self.assertIsNone(process.poll())
            self.assertEqual(process.poll(), 0)
            self.assertEqual(process.poll(), 0)
        handle.Close.assert_called_once()

    def test_first_start_downloads_and_second_checks_files_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, "w") as bundle:
                bundle.writestr("sirosix-product.json", json.dumps({"schema": 1, "product": "verzum", "version": "1.1.1", "executable": "SiroSix-Verzum-Bot.exe"}))
                bundle.writestr("SiroSix-Verzum-Bot.exe", b"MZfixture")
                bundle.writestr("needed.dll", b"dependency")
            payload = raw.getvalue()
            events, launches = [], []
            class FakeApi:
                file_path = Api().file_path
                def grant(inner, key, hwid):
                    events.append("grant")
                def download_info(inner, key):
                    return {"version": "1.1.1", "groesse": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "url": "https://sirosix-server.sirosix.workers.dev/datei/test"}
                def open(inner, path):
                    events.append("fetch")
                    return io.BytesIO(payload)
            def launch(args, **kwargs):
                launches.append(args)
                self.assertTrue(Path(args[0]).is_file())
                self.assertEqual(len(args), 1)
                events.append("spawn")
                return "process"
            for _ in range(2):
                self.assertEqual(start_product(FakeApi(), "verzum", "hash", lambda name, detail: events.append(name),
                                              lambda done, total: None, root=Path(folder), launch=launch), "process")
            self.assertEqual(len(launches), 2)
            self.assertEqual(events.count("fetch"), 1)
            self.assertEqual(events.count("verify"), 2)
            self.assertLess(events.index("grant"), events.index("fetch"))
            self.assertLess(events.index("verify"), events.index("spawn"))
            Path(folder, "verzum/1.1.1/needed.dll").write_bytes(b"changed")
            with self.assertRaises(PackageError):
                start_product(FakeApi(), "verzum", "hash", lambda *args: None, lambda *args: None,
                              root=Path(folder), launch=launch)
            self.assertEqual(len(launches), 2)

    def test_denied_license_never_downloads_or_launches(self):
        class Denied:
            def grant(inner, key, hwid):
                raise ApiError(403, "lizenz", "Keine aktive Lizenz")
            def download_info(inner, key):
                self.fail("No download after denial")
        with self.assertRaises(ApiError):
            start_product(Denied(), "verzum", "hash", lambda *args: None, lambda *args: None,
                          launch=lambda *args, **kwargs: self.fail("No process after denial"))

    def test_missing_runtime_stops_before_download_or_launch(self):
        class FakeApi:
            def grant(inner, key, hwid):
                pass
            def download_info(inner, key):
                return {"version": "1.1.1", "sha256": "0" * 64, "groesse": 50}
            def open(inner, path):
                self.fail("No download when prerequisites are missing")
        with patch("sirosix.startup.check_requirements", side_effect=RuntimeError("Runtime fehlt")):
            with self.assertRaisesRegex(RuntimeError, "Runtime fehlt"):
                start_product(FakeApi(), "verzum", "hash", lambda *args: None, lambda *args: None,
                              launch=lambda *args, **kwargs: self.fail("No process when prerequisites are missing"))
