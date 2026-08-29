from __future__ import annotations

import unittest
from pathlib import Path

from effectkit.capsule import Capsule
from effectkit.reconcile import EffectError
from effectkit.registry import Registry, bundled, load_dir

ROOT = Path(__file__).resolve().parents[2]


class TestRegistry(unittest.TestCase):
    def test_bundled_has_four(self):
        reg = bundled()
        self.assertEqual(len(reg), 4)
        self.assertEqual(
            reg.ids(),
            ["github.merge_pr", "postgres.insert", "s3.delete_object", "stripe.charge"])

    def test_get_known_and_unknown(self):
        reg = bundled()
        self.assertEqual(reg.get("stripe.charge").provider, "stripe")
        with self.assertRaises(EffectError) as raised:
            reg.get("stripe.refund")
        self.assertIn("no capsule 'stripe.refund'", str(raised.exception))

    def test_load_dir_matches_bundled(self):
        reg = load_dir(ROOT / "capsules")
        self.assertEqual(reg.ids(), bundled().ids())

    def test_duplicate_id_rejected(self):
        cap = bundled().get("stripe.charge")
        with self.assertRaises(EffectError) as raised:
            Registry([cap, cap])
        self.assertIn("duplicate capsule id", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
