from __future__ import annotations

import unittest

from effectkit.adapters.dbos import Saga, Skipped, UnknownOutcome, guard
from effectkit.capsule import Request
from effectkit.registry import bundled
from effectkit.transport import Response


class OneRoute:
    def __init__(self, response: Response):
        self.response = response
        self.seen: list[Request] = []

    def send(self, request: Request) -> Response:
        self.seen.append(request)
        return self.response


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.capsule = bundled().get("stripe.charge")

    def test_guard_skips_when_already_landed(self):
        landed = OneRoute(Response(200, {"data": [{"id": "pi_1", "status": "succeeded"}]}))
        calls = []
        result = guard(self.capsule, {"order_id": "ORD-1"}, landed, lambda: calls.append("did"))
        self.assertIsInstance(result, Skipped)
        self.assertEqual(calls, [])

    def test_guard_runs_when_not_landed(self):
        empty = OneRoute(Response(200, {"data": []}))
        result = guard(self.capsule, {"order_id": "ORD-1"}, empty, lambda: "charged")
        self.assertEqual(result, "charged")

    def test_guard_refuses_to_act_on_unknown(self):
        outage = OneRoute(Response(503, {}))
        calls = []
        with self.assertRaises(UnknownOutcome) as raised:
            guard(self.capsule, {"order_id": "ORD-1"}, outage, lambda: calls.append("did"))
        self.assertEqual(calls, [], "an unknown probe result must never fire the side effect")
        self.assertEqual(raised.exception.outcome.status, "unknown")

    def test_guard_treats_money_in_flight_as_unknown(self):
        processing = OneRoute(Response(200, {"data": [{"id": "pi_1", "status": "processing"}]}))
        with self.assertRaises(UnknownOutcome):
            guard(self.capsule, {"order_id": "ORD-1"}, processing, lambda: "charged")


class TestSaga(unittest.TestCase):
    def test_compensate_walks_in_reverse(self):
        capsule = bundled().get("stripe.charge")
        transport = OneRoute(Response(200, {"id": "re_x"}))
        saga = Saga()
        saga.record(capsule, {"payment_intent_id": "pi_first"}, transport)
        saga.record(capsule, {"payment_intent_id": "pi_second"}, transport)
        results = saga.compensate()
        self.assertEqual([r.status for r in results], ["compensated", "compensated"])
        refunded = [r.query["payment_intent"] for r in transport.seen]
        self.assertEqual(refunded, ["pi_second", "pi_first"])


if __name__ == "__main__":
    unittest.main()
