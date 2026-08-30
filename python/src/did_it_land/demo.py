"""A runnable demo that needs no keys and no network.

It stages the exact failure did-it-land exists for: a durable worker charges a customer,
then crashes before it can record that the charge went through. On recovery the naive
path double-charges, because the idempotency key died with the crash. The did-it-land path
asks the stripe.charge capsule "did this land" using the order id, which the workflow
always has, and skips the second charge.

The Stripe here is an in-process fake that mimics idempotency and the search endpoint.
No real calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .capsule import Request
from .reconcile import reconcile, unwind
from .registry import bundled
from .transport import Response


@dataclass
class FakeStripe:
    """Just enough Stripe to run the demo: create with idempotency, search, refund,
    and an outage switch so the demo can stage an unknown answer."""

    _by_key: dict[str, dict] = field(default_factory=dict)
    _by_order: dict[str, list[dict]] = field(default_factory=dict)
    _seq: int = 0
    outage: bool = False

    def send(self, request: Request) -> Response:
        path, method = request.path, request.method
        if self.outage:
            return Response(503, {"error": "service unavailable"})
        if method == "POST" and path == "/v1/payment_intents":
            return self._create(request)
        if method == "GET" and path == "/v1/payment_intents/search":
            return self._search(request)
        if method == "GET" and path == "/v1/payment_intents":
            all_intents = [pi for charges in self._by_order.values() for pi in charges]
            return Response(200, {"data": all_intents})
        if method == "POST" and path == "/v1/refunds":
            return self._refund(request)
        return Response(404, {"error": f"no fake route for {method} {path}"})

    def _create(self, request: Request) -> Response:
        key = request.headers.get("Idempotency-Key", "")
        if key and key in self._by_key:
            return Response(200, self._by_key[key])
        self._seq += 1
        order_id = request.query.get("order_id", "")
        pi = {
            "id": f"pi_{self._seq:04d}",
            "status": "succeeded",
            "amount": int(request.query.get("amount", "0")),
            "refunded": False,
            "metadata": {"order_id": order_id}}
        if key:
            self._by_key[key] = pi
        self._by_order.setdefault(order_id, []).append(pi)
        return Response(200, pi)

    def _search(self, request: Request) -> Response:
        query = request.query.get("query", "")
        order_id = query.split('"')[-2] if '"' in query else ""
        return Response(200, {"data": list(self._by_order.get(order_id, []))})

    def _refund(self, request: Request) -> Response:
        pi_id = request.query.get("payment_intent", "")
        for charges in self._by_order.values():
            for pi in charges:
                if pi["id"] == pi_id:
                    pi["refunded"] = True
                    return Response(200, {"id": f"re_{pi_id}", "payment_intent": pi_id})
        return Response(404, {"error": "no such payment_intent"})

    def charges_for(self, order_id: str) -> list[dict]:
        return self._by_order.get(order_id, [])


def _charge(stripe: FakeStripe, order_id: str, idem_key: str) -> dict:
    resp = stripe.send(
        Request(
            "POST",
            "/v1/payment_intents",
            headers={"Idempotency-Key": idem_key},
            query={"order_id": order_id, "amount": "4999"}))
    return resp.body


def run_demo() -> dict:
    """Run both recovery paths and return a summary. Prints a narrative as it goes."""
    capsule = bundled().get("stripe.charge")
    order_id = "ORD-1"

    def _ctx(oid: str) -> dict:
        # A real workflow records the moment the order began and passes it as
        # created_after so the confirm walks only that window. The fake ignores
        # time, so any fixed instant works here.
        return {"order_id": oid, "created_after": "1700000000"}
    out: list[str] = []

    def say(line: str) -> None:
        out.append(line)
        print(line)

    say("=== did-it-land demo: did my charge land? ===")
    say("A worker charges a customer, then crashes before recording the result.")
    say("The recovery has three possible answers. This stages every one of them.")
    say("")

    # Run A: naive recovery. The idempotency key was lost in the crash, so the retry
    # mints a fresh key and charges again.
    naive = FakeStripe()
    _charge(naive, order_id, idem_key="attempt-1-key")
    say("Run A, naive recovery, no check at all")
    say("  attempt 1 : charged, then the worker crashed before the checkpoint")
    say("  recovery  : the idempotency key was lost, so the retry uses a new key")
    _charge(naive, order_id, idem_key="recovery-fresh-key")
    naive_count = len(naive.charges_for(order_id))
    say(f"  result    : {naive_count} charges for {order_id}, the customer is double charged")
    say("")

    # Run B: the charge went through before the crash. The probe finds it, so the
    # retry is skipped.
    fixed = FakeStripe()
    _charge(fixed, order_id, idem_key="attempt-1-key")
    say("Run B, answer: landed. The charge made it out before the crash.")
    landed = reconcile(capsule, _ctx(order_id), transport=fixed)
    say(f"  recovery  : reconcile(stripe.charge, order_id={order_id}) -> {landed.status}")
    if not landed.landed:
        _charge(fixed, order_id, idem_key="recovery-fresh-key")
    fixed_count = len(fixed.charges_for(order_id))
    say(f"  result    : {fixed_count} charge for {order_id}, retry skipped, no double charge")
    say("")

    # Run C: the crash hit before the request ever left. The probe finds nothing,
    # so running the step now is safe.
    empty = FakeStripe()
    say("Run C, answer: not landed. The crash hit before the request left.")
    absent = reconcile(capsule, _ctx(order_id), transport=empty)
    say(f"  recovery  : reconcile(stripe.charge, order_id={order_id}) -> {absent.status}")
    if absent.not_landed:
        _charge(empty, order_id, idem_key="derived-from-order-key")
    empty_count = len(empty.charges_for(order_id))
    say(f"  result    : safe to run, {empty_count} charge for {order_id}, exactly once")
    say("")

    # Run D: the service is down, so the answer is unknown. The honest move is to
    # refuse, wait, and ask again once the service is back.
    downed = FakeStripe()
    _charge(downed, order_id, idem_key="attempt-1-key")
    downed.outage = True
    say("Run D, answer: unknown. The service is down when recovery asks.")
    unknown = reconcile(capsule, _ctx(order_id), transport=downed)
    say(f"  recovery  : reconcile(stripe.charge, order_id={order_id}) -> {unknown.status}")
    say("  decision  : refuse to act on a guess, wait for the service")
    downed.outage = False
    retried = reconcile(capsule, _ctx(order_id), transport=downed)
    say(f"  re-probe  : service is back -> {retried.status}, retry skipped")
    downed_count = len(downed.charges_for(order_id))
    say(f"  result    : {downed_count} charge for {order_id}, still exactly one")
    say("")

    # And reversing a landed charge is one call.
    pi_id = fixed.charges_for(order_id)[0]["id"]
    comp = unwind(capsule, {"payment_intent_id": pi_id}, transport=fixed)
    say(f"Unwind      : unwind(stripe.charge, {pi_id}) -> {comp.status} (refund issued)")

    return {
        "naive_charges": naive_count,
        "did_it_land_charges": fixed_count,
        "not_landed_charges": empty_count,
        "unknown_then_charges": downed_count,
        "reconcile_status": landed.status,
        "not_landed_status": absent.status,
        "unknown_status": unknown.status,
        "reprobe_status": retried.status,
        "unwind_status": comp.status,
        "lines": out}
