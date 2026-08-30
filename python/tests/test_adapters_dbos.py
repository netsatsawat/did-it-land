from __future__ import annotations

import unittest

from did_it_land.adapters.dbos import Saga, Skipped, UnknownOutcome, guard
from did_it_land.capsule import Request
from did_it_land.registry import bundled
from did_it_land.transport import Response


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

    def test_guard_waits_then_succeeds_when_the_answer_arrives(self):
        answers = [
            Response(503, {}),
            Response(503, {}),
            Response(200, {"data": [{"id": "pi_1", "status": "succeeded"}]})]

        class Sequenced:
            def send(self, request):
                return answers.pop(0)

        naps = []
        result = guard(
            self.capsule, {"order_id": "ORD-1"}, Sequenced(), lambda: "charged",
            unknown_retries=2, unknown_wait=5.0, sleep=naps.append)
        self.assertIsInstance(result, Skipped)
        self.assertEqual(naps, [5.0, 5.0], "one wait per unknown answer, then success")

    def test_guard_gives_up_after_bounded_retries(self):
        outage = OneRoute(Response(503, {}))
        naps = []
        with self.assertRaises(UnknownOutcome):
            guard(
                self.capsule, {"order_id": "ORD-1"}, outage, lambda: "charged",
                unknown_retries=2, unknown_wait=1.0, sleep=naps.append)
        self.assertEqual(len(naps), 2, "bounded patience, never an open-ended hang")
        self.assertEqual(len(outage.seen), 3, "initial probe plus two retries")

    def test_guard_treats_money_in_flight_as_unknown(self):
        processing = OneRoute(Response(200, {"data": [{"id": "pi_1", "status": "processing"}]}))
        with self.assertRaises(UnknownOutcome):
            guard(self.capsule, {"order_id": "ORD-1"}, processing, lambda: "charged")


class TestSaga(unittest.TestCase):
    def test_recording_the_wrong_context_key_fails_loudly(self):
        # The compensation template binds {payment_intent_id}. Recording only the
        # order id, the mistake our own example once shipped, must surface as a
        # loud error result at compensate time, never as a silently skipped
        # refund.
        capsule = bundled().get("stripe.charge")
        saga = Saga()
        saga.record(capsule, {"order_id": "ORD-1"}, OneRoute(Response(200, {})))
        results = saga.compensate()
        self.assertEqual([r.status for r in results], ["error"])
        self.assertIn("payment_intent_id", results[0].evidence["error"])

    def test_one_bad_step_does_not_strand_the_rest(self):
        # The second-recorded effect has a broken context. Its unwind raises,
        # is captured as an error result, and the first effect still gets its
        # refund.
        capsule = bundled().get("stripe.charge")
        transport = OneRoute(Response(200, {"id": "re_ok"}))
        saga = Saga()
        saga.record(capsule, {"payment_intent_id": "pi_good"}, transport)
        saga.record(capsule, {"order_id": "wrong-key"}, transport)
        results = saga.compensate()
        self.assertEqual([r.status for r in results], ["error", "compensated"])
        self.assertIn("payment_intent_id", results[0].evidence["error"])
        self.assertEqual(transport.seen[0].query["payment_intent"], "pi_good")

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
