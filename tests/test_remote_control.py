import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RemoteControlValidationTests(unittest.TestCase):
    def test_authentication_and_numeric_validation(self):
        with tempfile.TemporaryDirectory(prefix="hermesxp-remote-test-") as tmp:
            binary = pathlib.Path(tmp) / "remote_control_test"
            result = subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests" / "remote_control_test.c"), "-o", str(binary)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
