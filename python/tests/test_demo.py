from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from effectkit.demo import run_demo

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "reports" / "demo.golden.txt"


class TestDemo(unittest.TestCase):
    def setUp(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.result = run_demo()

    def test_naive_double_charges_effectkit_does_not(self):
        self.assertEqual(self.result["naive_charges"], 2)
        self.assertEqual(self.result["effectkit_charges"], 1)

    def test_reconcile_and_unwind_statuses(self):
        self.assertEqual(self.result["reconcile_status"], "landed")
        self.assertEqual(self.result["unwind_status"], "compensated")

    def test_output_matches_golden(self):
        expected = GOLDEN.read_text(encoding="utf-8").splitlines()
        self.assertEqual(self.result["lines"], expected)


if __name__ == "__main__":
    unittest.main()
