import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WlanProfileBuilderTests(unittest.TestCase):
    def test_profile_builder_outputs_safe_xp_profiles(self):
        with tempfile.TemporaryDirectory(prefix="hermesxp-wlan-test-") as tmp:
            binary = pathlib.Path(tmp) / "wlan_profile_test"
            compile_result = subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-attributes",
                 str(ROOT / "tests" / "wlan_profile_test.c"), "-o", str(binary)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
            self.assertEqual(run_result.returncode, 0, run_result.stderr)


if __name__ == "__main__":
    unittest.main()
