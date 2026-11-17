import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from sirosix.prerequisites import check_requirements


class PrerequisiteTests(unittest.TestCase):
    @patch("sirosix.prerequisites.Path.is_file", return_value=True)
    @patch("sirosix.prerequisites.subprocess.run")
    def test_net8_or_preview_does_not_satisfy_the_net10_requirement(self, run, exists):
        for output in ("Microsoft.NETCore.App 8.0.23 [C:/dotnet/shared]", "Microsoft.NETCore.App 10.0.0-preview.1 [C:/dotnet/shared]"):
            run.return_value = SimpleNamespace(returncode=0, stdout=output)
            with self.assertRaisesRegex(RuntimeError, "Runtime 10"):
                check_requirements("verzum")
        run.return_value = SimpleNamespace(returncode=0, stdout="Microsoft.NETCore.App 10.0.1 [C:/dotnet/shared]")
        check_requirements("verzum")

    @patch("sirosix.prerequisites.Path.is_file", return_value=False)
    @patch("sirosix.prerequisites.shutil.which", return_value=None)
    def test_missing_runtime_is_clear_and_rubinum_does_not_require_it(self, which, exists):
        with self.assertRaisesRegex(RuntimeError, "Runtime 10"):
            check_requirements("verzum")
        check_requirements("rubinum")

    @patch("sirosix.prerequisites.Path.is_file", return_value=True)
    @patch("sirosix.prerequisites.subprocess.run", side_effect=subprocess.TimeoutExpired("dotnet", 8))
    def test_runtime_probe_timeout_is_a_clear_error(self, run, exists):
        with self.assertRaisesRegex(RuntimeError, "nicht geprüft"):
            check_requirements("verzum")
