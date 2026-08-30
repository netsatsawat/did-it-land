# did-it-land

> Your durable worker crashed mid-tool-call. Did the charge actually fire, and how do you
> reverse it? did-it-land is the per-vendor knowledge that answers both, as data.

Durable and saga engines resume a crashed workflow from a checkpoint, then leave you the
hard part: query the vendor to see whether the side-effect landed, and write your own
compensation. did-it-land ships that knowledge as a small corpus of effect capsules plus a
thin runtime.

```
pip install "did-it-land[http]"
did-it-land demo
```

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

stripe = HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
charge = bundled().get("stripe.charge")

order_started_at = "1700000000"    # unix seconds, recorded when the order began
context = {"order_id": "ORD-1", "created_after": order_started_at}
outcome = reconcile(charge, context, transport=stripe)
if outcome.landed:
    ...        # the charge already happened, skip the retry

unwind(charge, {"payment_intent_id": "pi_123"}, transport=stripe)
```

v1 ships four capsules: `stripe.charge`, `s3.delete_object`, `github.merge_pr`, and
`postgres.insert`. Full docs, the DBOS adapter, and the TypeScript runtime are in the
repository.

Homepage and docs: https://github.com/netsatsawat/did-it-land

Written by [Satsawat Natakarnkitkul](https://satsawat.ai). License: MIT.
