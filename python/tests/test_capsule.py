from __future__ import annotations

import unittest

from did_it_land.capsule import CapsuleError, capsule_from_dict
from did_it_land.registry import bundled


def good_doc() -> dict:
    return {
        "id": "acme.do_thing",
        "provider": "acme",
        "operation": "do_thing",
        "schema_version": "1",
        "idempotency": {"strategy": "client_key", "header": "Idempotency-Key"},
        "probe": {
            "kind": "http",
            "request": {"method": "GET", "path": "/things/{id}"},
            "interpret": [{"when": {"status_in": [200]}, "result": "landed"}]},
        "reversibility": {"class": "reversible"}}


class TestCapsuleValidation(unittest.TestCase):
    def test_bundled_all_valid(self):
        reg = bundled()
        self.assertEqual(len(reg), 4)

    def test_good_doc_builds(self):
        cap = capsule_from_dict(good_doc())
        self.assertEqual(cap.id, "acme.do_thing")
        self.assertEqual(cap.probe.kind, "http")
        self.assertEqual(cap.reversibility.cls, "reversible")

    def test_bad_docs_raise(self):
        def drop(key):
            return lambda d: d.pop(key)

        cases = [
            (drop("id"), "missing required field 'id'"),
            (lambda d: d["idempotency"].__setitem__("strategy", "wat"), "must be one of"),
            (lambda d: d["probe"].__setitem__("kind", "carrier-pigeon"), "must be one of"),
            (lambda d: d["probe"].pop("request"), "missing required field 'request'"),
            (lambda d: d["probe"].__setitem__("interpret", []), "at least one rule"),
            (lambda d: d["probe"]["request"].__setitem__("method", "TELEPORT"), "must be one of"),
            (
                lambda d: d["reversibility"].__setitem__("class", "conditionally_reversible"),
                "must state its condition")]
        for mutate, expected in cases:
            doc = good_doc()
            mutate(doc)
            with self.assertRaises(CapsuleError, msg=expected) as ctx:
                capsule_from_dict(doc)
            self.assertIn(expected, str(ctx.exception), msg=expected)

    def test_typoed_rule_keys_are_rejected_not_ignored(self):
        # A dropped typo would leave a rule with zero conditions, which matches
        # every response. The validator must refuse it loudly instead.
        doc = good_doc()
        doc["probe"]["interpret"] = [
            {"when": {"statuses_in": [200]}, "result": "landed"}]
        with self.assertRaises(CapsuleError) as raised:
            capsule_from_dict(doc)
        self.assertIn("statuses_in", str(raised.exception))

    def test_conditions_outside_when_are_rejected(self):
        doc = good_doc()
        doc["probe"]["interpret"] = [{"status_in": [200], "result": "landed"}]
        with self.assertRaises(CapsuleError) as raised:
            capsule_from_dict(doc)
        self.assertIn("status_in", str(raised.exception))

    def test_unknown_top_level_key_is_rejected(self):
        doc = good_doc()
        doc["reversability"] = {"class": "reversible"}
        with self.assertRaises(CapsuleError) as raised:
            capsule_from_dict(doc)
        self.assertIn("reversability", str(raised.exception))

    def test_wrong_typed_conditions_are_rejected(self):
        for mutate, needle in (
                (lambda d: d["probe"]["interpret"][0]["when"].__setitem__("status_in", 200),
                 "status_in"),
                (lambda d: d["probe"]["interpret"][0]["when"].__setitem__("exists", "yes"),
                 "exists"),
                (lambda d: d["probe"]["interpret"][0]["when"].__setitem__("count_gte", "2"),
                 "count_gte")):
            doc = good_doc()
            mutate(doc)
            with self.assertRaises(CapsuleError, msg=needle) as raised:
                capsule_from_dict(doc)
            self.assertIn(needle, str(raised.exception), msg=needle)

    def test_unsupported_schema_version_is_refused(self):
        doc = good_doc()
        doc["schema_version"] = "99"
        with self.assertRaises(CapsuleError) as raised:
            capsule_from_dict(doc)
        self.assertIn("99", str(raised.exception))

    def test_native_probe_needs_handler(self):
        doc = good_doc()
        doc["probe"] = {"kind": "native"}
        with self.assertRaises(CapsuleError) as ctx:
            capsule_from_dict(doc)
        self.assertIn("missing required field 'handler'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
