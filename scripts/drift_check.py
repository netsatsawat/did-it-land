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
    """A well-formed search returns 200 even with zero results. A changed endpoint or
    response shape is exactly the drift we want to catch."""
    key = os.environ.get("STRIPE_TEST_KEY")
    if not key:
        return None
    import httpx

    resp = httpx.get(
        "https://api.stripe.com/v1/payment_intents/search",
        params={"query": 'metadata["order_id"]:"did-it-land-drift-probe"'},
        headers={"Authorization": f"Bearer {key}"},
        timeout=15.0)
    return resp.status_code == 200 and isinstance(resp.json().get("data"), list)


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
