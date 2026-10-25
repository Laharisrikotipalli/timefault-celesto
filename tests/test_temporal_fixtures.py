import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_fixture(scenario, simulated_date):
    src = ROOT / "fixtures" / scenario / "app.py"
    # The fixture is run with a simulated clock; it remains unchanged on disk.
    return subprocess.run(
        [
            "faketime",
            f"{simulated_date} 12:00:00",
            sys.executable,
            str(src),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TemporalFixtureTests(unittest.TestCase):
    def test_e01_fails_only_on_expiry_day(self):
        before = run_fixture("E01", "2028-05-31")
        expiry = run_fixture("E01", "2028-06-01")
        after = run_fixture("E01", "2028-06-02")

        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertNotEqual(expiry.returncode, 0)
        self.assertIn("2028-06-01", expiry.stderr)
        self.assertEqual(after.returncode, 0, after.stderr)

    def test_e02_crosses_signed_32_bit_epoch_limit(self):
        before = run_fixture("E02", "2038-01-18")
        after = run_fixture("E02", "2038-01-19")

        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertNotEqual(after.returncode, 0)
        self.assertIn("overflows int32", after.stderr)

    def test_c01_handles_leap_day_anniversary(self):
        result = run_fixture("C01", "2028-02-29")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_f01_is_not_deterministic(self):
        # Do not assert that any individual random run passes or fails.
        # This test only verifies that the fixture is executable.
        result = run_fixture("F01", "2028-02-29")
        self.assertIn(result.returncode, (0, 1))


if __name__ == "__main__":
    unittest.main()
