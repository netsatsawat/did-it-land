"""Weekly live-sandbox drift check.

The offline tests prove the runtime and the shape of each capsule. This checks the other
half: that the vendor still behaves the way the capsule says. It runs a real probe against
each vendor's sandbox when the credentials are present, and stamps
reports/freshness.json with the date a capsule was last confirmed against the live API.

A capsule with no live check yet, or with no credentials in the environment, is skipped
rather than failed, so the job is honest about what it actually verified.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRESH = ROOT / "reports" / "freshness.json"


def stripe_live() -> bool | None:
    """Run the real reconcile path against Stripe test mode with an order id that
    cannot exist. The capsule must walk BOTH questions, the search and the lag-free
    List confirm, and conclude not_landed. That checks the interpret semantics and
    both endpoints' shapes, not merely that one URL returns a 200."""
    key = os.environ.get("STRIPE_TEST_KEY")
    if not key:
        return None
    import sys

    sys.path.insert(0, str(ROOT / "python" / "src"))
    from did_it_land import HttpxTransport, bundled, reconcile

    capsule = bundled().get("stripe.charge")
    transport = HttpxTransport(
        "https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
    outcome = reconcile(
        capsule, {"order_id": "did-it-land-drift-probe-never-created"},
        transport=transport)
    if outcome.status != "not_landed":
        print(f"  expected not_landed, got {outcome.status} ({outcome.evidence})")
        return False
    if not outcome.evidence.get("confirmed"):
        print("  the List confirm pass did not run; probe semantics drifted")
        return False
    return True


# Capsules gain a live check here as their sandbox harness is written. Roadmap capsules
# without one are skipped, never silently marked verified.
CHECKS = {"stripe.charge": stripe_live}


def main() -> int:
    data = json.loads(FRESH.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    failed = False

    for capsule_id, entry in data["capsules"].items():
        check = CHECKS.get(capsule_id)
        if check is None:
            print(f"{capsule_id}: no live check yet, skipped")
            continue
        result = check()
        if result is None:
            print(f"{capsule_id}: credentials not provided, skipped")
            continue
        if result:
            entry["last_verified_live"] = today
            print(f"{capsule_id}: verified live on {today}")
        else:
            print(f"{capsule_id}: LIVE CHECK FAILED, the vendor may have drifted")
            failed = True

    FRESH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
