# did-it-land

> Your durable worker crashed mid-tool-call. Did the charge actually fire, and how do you
> reverse it? did-it-land is the per-vendor knowledge that answers both, as data.

```ts
import { bundled, reconcile, unwind } from "did-it-land";

const charge = bundled().get("stripe.charge");

// After an ambiguous crash: did it land? created_after is a unix-seconds
// timestamp your workflow records when the order begins.
const outcome = await reconcile(
  charge,
  { order_id: "ORD-1", created_after: orderStartedAt },
  stripeTransport,
);
if (outcome.status === "landed") {
  // the charge already happened, skip the retry
}

await unwind(charge, { payment_intent_id: "pi_123" }, stripeTransport);
```

`stripeTransport` is yours to supply: any object with an async `send(request)`
returning `{ statusCode, body }` and throwing `TransportError` on timeouts, as shown
in the quick start's fetch example.

v1 ships four capsules: `stripe.charge`, `s3.delete_object`, `github.merge_pr`, and
`postgres.insert`. Same corpus as the Python package. The native `postgres.insert`
capsule ships built-in handlers that register on import, so it works out of the box once
you pass a database connection in the context. `registerNative()` is only for adding your
own native handlers. Full docs in the repository.

Homepage and docs: https://github.com/netsatsawat/did-it-land

Written by Satsawat Natakarnkitkul. License: MIT.
