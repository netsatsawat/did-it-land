"""Reference integration: effectkit inside a DBOS workflow.

This is the pattern effectkit is built for. DBOS resumes a crashed workflow from its last
completed step. The charge step wraps its side effect in effectkit's guard, so on recovery
it probes whether the charge already landed before charging again. A failed workflow walks
its completed effects back with a Saga.

Run it against a real DBOS install and Postgres:

    pip install "effectkit[dbos,http]" dbos
    export DBOS_DATABASE_URL=postgresql://...       # your local Postgres
    python examples/dbos_charge.py

Without DBOS installed it prints how to get it and exits, so the file is safe to open and
read anywhere. The offline demo (`effectkit demo`) proves the same logic with no setup.
"""

from __future__ import annotations

import os
import sys

from effectkit import HttpxTransport, bundled
from effectkit.adapters.dbos import Saga, guard


def _stripe() -> HttpxTransport:
    key = os.environ.get("STRIPE_API_KEY", "sk_test_placeholder")
    return HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})


def main() -> int:
    try:
        from dbos import DBOS
    except ImportError:
        print("This example needs DBOS. Install it with:")
        print('  pip install "effectkit[dbos,http]" dbos')
        print("Then set DBOS_DATABASE_URL to a Postgres instance and run again.")
        print("The logic without DBOS is shown by: effectkit demo")
        return 0

    DBOS()
    charge = bundled().get("stripe.charge")
    stripe = _stripe()
    saga = Saga()

    @DBOS.step()
    def charge_customer(order_id: str) -> str:
        # On recovery this step re-runs. guard probes first and only charges if the
        # charge has not already landed, keyed on the order id the workflow always has.
        def do_charge() -> str:
            # your real Stripe create call goes here; return the payment intent id
            raise NotImplementedError("wire up your Stripe create call")

        result = guard(charge, {"order_id": order_id}, stripe, do_charge)
        saga.record(charge, {"order_id": order_id}, stripe)
        return str(result)

    @DBOS.workflow()
    def fulfil(order_id: str) -> str:
        try:
            return charge_customer(order_id)
        except Exception:
            saga.compensate()
            raise

    DBOS.launch()
    print(fulfil("ORD-1"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
