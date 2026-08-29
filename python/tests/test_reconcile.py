from __future__ import annotations

import unittest

from did_it_land.capsule import Request
from did_it_land.reconcile import EffectError, reconcile, unwind
from did_it_land.registry import bundled
from did_it_land.transport import Response, TransportError


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
        search = ("GET", "/v1/payment_intents/search")
        listing = ("GET", "/v1/payment_intents")
        empty = Response(200, {"data": []})
        cases = [
            (Response(200, {"data": [{"id": "pi_1", "status": "succeeded"}]}), "landed"),
            (Response(200, {"data": [{"id": "pi_1", "status": "requires_payment_method"}]}),
                "not_landed"),
            (Response(200, {"data": [{"id": "pi_1", "status": "processing"}]}), "unknown"),
            (empty, "not_landed"),
            (Response(503, {}), "unknown")]
        for resp, expected in cases:
            t = ScriptedTransport({search: resp, listing: empty})
            outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=t)
            self.assertEqual(outcome.status, expected, msg=f"body {resp.body}")

    def test_confirm_rescues_a_lagging_search(self):
        # Search has not indexed the charge yet, but the lag-free List API has it.
        # The capsule must answer landed, never green-light the double charge.
        capsule = self.reg.get("stripe.charge")
        landed_intent = {
            "id": "pi_lagged",
            "status": "succeeded",
            "metadata": {"order_id": "ORD-1"}}
        t = ScriptedTransport({
            ("GET", "/v1/payment_intents/search"): Response(200, {"data": []}),
            ("GET", "/v1/payment_intents"): Response(200, {"data": [landed_intent]})})
        outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=t)
        self.assertEqual(outcome.status, "landed")
        self.assertTrue(outcome.evidence["confirmed"])
        self.assertEqual(outcome.evidence["ids"], ["pi_lagged"],
                         "the id must flow so unwind needs no second lookup")

    def test_confirm_filters_by_the_callers_order_id(self):
        # Someone else's charge in the recent list must not read as ours.
        capsule = self.reg.get("stripe.charge")
        other = {
            "id": "pi_other",
            "status": "succeeded",
            "metadata": {"order_id": "SOMEONE-ELSE"}}
        t = ScriptedTransport({
            ("GET", "/v1/payment_intents/search"): Response(200, {"data": []}),
            ("GET", "/v1/payment_intents"): Response(200, {"data": [other]})})
        outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=t)
        self.assertEqual(outcome.status, "not_landed")
        self.assertTrue(outcome.evidence["confirmed"])

    def test_stripe_probe_surfaces_duplicates(self):
        capsule = self.reg.get("stripe.charge")
        path = "/v1/payment_intents/search"
        body = {"data": [
            {"id": "pi_1", "status": "succeeded"},
            {"id": "pi_2", "status": "succeeded"},
            {"id": "pi_3", "status": "requires_payment_method"}]}
        t = ScriptedTransport({("GET", path): Response(200, body)})
        outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=t)
        self.assertEqual(outcome.status, "landed")
        self.assertEqual(outcome.evidence["matched"], 2, "two succeeded intents is a duplicate")
        self.assertEqual(outcome.evidence["ids"], ["pi_1", "pi_2"])

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

    def test_timeout_during_probe_is_unknown_not_a_crash(self):
        capsule = self.reg.get("stripe.charge")

        class TimingOut:
            def send(self, request):
                raise TransportError("GET /v1/payment_intents/search: timed out")

        outcome = reconcile(capsule, {"order_id": "ORD-1"}, transport=TimingOut())
        self.assertEqual(outcome.status, "unknown")
        self.assertIn("timed out", outcome.evidence["transport_error"])

    def test_http_probe_needs_transport(self):
        capsule = self.reg.get("stripe.charge")
        with self.assertRaises(EffectError):
            reconcile(capsule, {"order_id": "ORD-1"})


class TestUnwind(unittest.TestCase):
    def setUp(self):
        self.reg = bundled()

    def test_stripe_compensation_refunds_with_its_own_idempotency_key(self):
        capsule = self.reg.get("stripe.charge")
        t = ScriptedTransport({("POST", "/v1/refunds"): Response(200, {"id": "re_1"})})
        result = unwind(capsule, {"payment_intent_id": "pi_1"}, transport=t)
        self.assertEqual(result.status, "compensated")
        self.assertEqual(t.seen[0].query["payment_intent"], "pi_1")
        self.assertEqual(
            t.seen[0].headers["Idempotency-Key"],
            "did-it-land-refund-pi_1",
            "a crashed compensation must not refund twice either")

    def test_github_merge_is_irreversible(self):
        capsule = self.reg.get("github.merge_pr")
        result = unwind(capsule, {})
        self.assertEqual(result.status, "irreversible")

    def test_timeout_during_compensation_is_unknown_and_retryable(self):
        capsule = self.reg.get("stripe.charge")

        class TimingOut:
            def send(self, request):
                raise TransportError("POST /v1/refunds: timed out")

        result = unwind(capsule, {"payment_intent_id": "pi_1"}, transport=TimingOut())
        self.assertEqual(result.status, "unknown",
                         "the refund may have landed, so report unknown, never failed")

    def test_failed_compensation_reports_failed(self):
        capsule = self.reg.get("stripe.charge")
        t = ScriptedTransport({("POST", "/v1/refunds"): Response(402, {"error": "declined"})})
        result = unwind(capsule, {"payment_intent_id": "pi_1"}, transport=t)
        self.assertEqual(result.status, "failed")


if __name__ == "__main__":
    unittest.main()
