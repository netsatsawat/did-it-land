from __future__ import annotations

import unittest

from effectkit.capsule import Request
from effectkit.reconcile import EffectError, reconcile, unwind
from effectkit.registry import bundled
from effectkit.transport import Response


class ScriptedTransport:
    """Return a canned Response per (method, path), recording every request seen."""

    def __init__(self, routes: dict[tuple[str, str], Response]):
        self.routes = routes
        self.seen: list[Request] = []

    def send(self, request: Request) -> Response:
        self.seen.append(request)
        return self.routes[(request.method, request.path)]


class TestHttpProbe(unittest.TestCase):
    def setUp(self):
        self.reg = bundled()

    def test_stripe_probe_results(self):
        capsule = self.reg.get("stripe.charge")
        path = "/v1/payment_intents/search"
        cases = [
            (Response(200, {"data": [{"id": "pi_1"}]}), "landed"),
            (Response(200, {"data": []}), "not_landed"),
            (Response(503, {}), "unknown")]
        for resp, expected in cases:
            t = ScriptedTransport({("GET", path): resp})
            outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=t)
            self.assertEqual(outcome.status, expected, msg=f"status {resp.status_code}")

    def test_s3_probe_results(self):
        capsule = self.reg.get("s3.delete_object")
        path = "/my-bucket/report.csv"
        ctx = {"bucket": "my-bucket", "key": "report.csv"}
        cases = [(Response(404), "landed"), (Response(200), "not_landed"), (Response(503), "unknown")]
        for resp, expected in cases:
            t = ScriptedTransport({("HEAD", path): resp})
            outcome = reconcile(capsule, ctx, transport=t)
            self.assertEqual(outcome.status, expected, msg=f"status {resp.status_code}")

    def test_github_probe_distinguishes_merged(self):
        capsule = self.reg.get("github.merge_pr")
        path = "/repos/acme/app/pulls/7"
        ctx = {"owner": "acme", "repo": "app", "pull_number": "7"}
        cases = [
            (Response(200, {"merged": True}), "landed"),
            (Response(200, {"merged": False}), "not_landed"),
            (Response(404, {}), "unknown")]
        for resp, expected in cases:
            t = ScriptedTransport({("GET", path): resp})
            outcome = reconcile(capsule, ctx, transport=t)
            self.assertEqual(outcome.status, expected, msg=f"status {resp.status_code}")

    def test_missing_context_placeholder_raises(self):
        capsule = self.reg.get("s3.delete_object")
        t = ScriptedTransport({})
        with self.assertRaises(EffectError) as ctx:
            reconcile(capsule, {"bucket": "my-bucket"}, transport=t)
        self.assertIn("key", str(ctx.exception))

    def test_http_probe_needs_transport(self):
        capsule = self.reg.get("stripe.charge")
        with self.assertRaises(EffectError):
            reconcile(capsule, {"order_id": "ORD-1"})


class TestUnwind(unittest.TestCase):
    def setUp(self):
        self.reg = bundled()

    def test_stripe_compensation_refunds(self):
        capsule = self.reg.get("stripe.charge")
        t = ScriptedTransport({("POST", "/v1/refunds"): Response(200, {"id": "re_1"})})
        result = unwind(capsule, {"payment_intent_id": "pi_1"}, transport=t)
        self.assertEqual(result.status, "compensated")
        self.assertEqual(t.seen[0].query["payment_intent"], "pi_1")

    def test_github_merge_is_irreversible(self):
        capsule = self.reg.get("github.merge_pr")
        result = unwind(capsule, {})
        self.assertEqual(result.status, "irreversible")

    def test_failed_compensation_reports_failed(self):
        capsule = self.reg.get("stripe.charge")
        t = ScriptedTransport({("POST", "/v1/refunds"): Response(402, {"error": "declined"})})
        result = unwind(capsule, {"payment_intent_id": "pi_1"}, transport=t)
        self.assertEqual(result.status, "failed")


if __name__ == "__main__":
    unittest.main()
