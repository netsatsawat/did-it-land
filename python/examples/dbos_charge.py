"""Reference integration: did-it-land inside a DBOS workflow.

This is the pattern did-it-land is built for. DBOS resumes a crashed workflow from its last
completed step. The charge step wraps its side effect in did-it-land's guard, so on recovery
it probes whether the charge already landed before charging again. A failed workflow walks
its completed effects back with a Saga.

Run it against a real DBOS install and Postgres:

    pip install "did-it-land[dbos,http]" dbos
    export DBOS_DATABASE_URL=postgresql://...       # your local Postgres
    python examples/dbos_charge.py

Without DBOS installed it prints how to get it and exits, so the file is safe to open and
read anywhere. The offline demo (`did-it-land demo`) proves the same logic with no setup.
"""

from __future__ import annotations

import os
import sys
import time

from did_it_land import HttpxTransport, Saga, Skipped, bundled, guard


def _stripe() -> HttpxTransport:
    key = os.environ.get("STRIPE_API_KEY", "sk_test_placeholder")
    return HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})


def main() -> int:
    try:
        from dbos import DBOS
    except ImportError:
        print("This example needs DBOS. Install it with:")
        print('  pip install "did-it-land[dbos,http]" dbos')
        print("Then set DBOS_DATABASE_URL to a Postgres instance and run again.")
        print("The logic without DBOS is shown by: did-it-land demo")
        return 0

    DBOS()
    charge = bundled().get("stripe.charge")
    stripe = _stripe()

    @DBOS.step()
    def charge_customer(order_id: str, started_at: str) -> str:
        # On recovery an incomplete step re-runs, so guard probes first and only
        # charges if the charge has not already landed, keyed on the order id the
        # workflow always has. Two contracts make the probe able to see your
        # charge at all: the create call must attach metadata={"order_id":
        # order_id}, and its Idempotency-Key must derive from the order id, for
        # example f"charge-{order_id}", never from a value minted inside the step.
        def do_charge() -> str:
            # your real Stripe create call goes here; return the payment intent id
            raise NotImplementedError("wire up your Stripe create call")

        context = {"order_id": order_id, "created_after": started_at}
        result = guard(charge, context, stripe, do_charge)
        # The undo template needs the payment intent id, so return THAT, never the
        # order id. A landed probe already carries the id in its evidence.
        if isinstance(result, Skipped):
            return result.outcome.evidence["ids"][0]
        return str(result)

    @DBOS.workflow()
    def fulfil(order_id: str, started_at: str) -> str:
        # The Saga lives in the WORKFLOW body, one per invocation, and record()
        # runs here with the step's return value. Engines skip completed steps on
        # recovery, so a record() inside the step would never replay and the
        # journal would be empty exactly when compensation matters.
        saga = Saga()
        try:
            pi_id = charge_customer(order_id, started_at)
            saga.record(charge, {"payment_intent_id": pi_id}, stripe)
            return pi_id
        except Exception:
            saga.compensate()
            raise

    DBOS.launch()
    # Record the order's start before any work begins: recovery re-binds this
    # exact value, so the capsule's window always reaches back to the order.
    print(fulfil("ORD-1", str(int(time.time()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
