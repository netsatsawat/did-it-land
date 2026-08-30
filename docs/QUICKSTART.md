# Quick start

From zero to your first real check in about ten minutes. No account is needed until
step 3, and nothing here touches live money.

## 1. Install and see the point

```
pip install did-it-land
did-it-land demo
```

The demo runs entirely on your machine against a built-in fake. It stages a crash four
ways and shows the three possible answers: the charge went through, it did not, and we
cannot tell yet. If the output ends with one charge and a refund, you are ready.

Three other commands are worth knowing:

```
did-it-land list          # the bundled capsules and what each can undo
did-it-land validate      # check a capsule file you are writing
did-it-land schema        # the capsule format version
```

## 2. The two calls

Everything you do with this library is one of two calls. `reconcile` asks whether an
action went through. `unwind` reverses it. That is the entire surface.

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

capsule = bundled().get("stripe.charge")
```

A capsule holds the knowledge. A transport carries the question to the service. The
built-in one needs the http extra, one install flag: `pip install "did-it-land[http]"`.
Configure it once with the service's address and your credentials:

```python
stripe = HttpxTransport(
    "https://api.stripe.com",
    headers={"Authorization": "Bearer sk_test_..."},
    timeout=15.0)        # seconds per request, raise it for slow networks
```

## 3. Your first real check

Use a Stripe test-mode key, so no real money is involved. The Stripe capsule finds a
charge by the order id you attached as metadata when creating it, so create one test
payment first, with `metadata[order_id]=QS-1`, in the Stripe dashboard or from code.

The capsule needs two context values. `order_id` is yours. `created_after` is a unix
timestamp from before the charge began, which a real workflow records the moment an
order starts. For this manual test, yesterday is safely before your test payment:

```python
import time

context = {
    "order_id": "QS-1",
    "created_after": str(int(time.time()) - 86400)}
outcome = reconcile(capsule, context, transport=stripe)

if outcome.landed:
    print("it went through", outcome.evidence)
elif outcome.not_landed:
    print("it never happened, safe to run it now")
else:
    print("no answer yet, wait and ask again", outcome.evidence)
```

Three answers, always. `evidence` carries what the probe saw, including a `matched`
count when more than one charge exists for the same order, which means you already
have a duplicate to refund.

Stripe's search can lag a few moments behind a brand-new charge, and the capsule
handles that for you: on an empty search answer it automatically asks Stripe's List
API, which does not lag, bounded to intents created since your `created_after` moment,
and only then answers not landed, stamping `confirmed: True` into the evidence. The
one residual gap is more than a hundred intents on your account within that window, in
which case the answer is unknown rather than a guess.

## 4. Undo it

```python
result = unwind(capsule, {"payment_intent_id": "pi_..."}, transport=stripe)
print(result.status)     # compensated, failed, or unknown if it did not answer
```

The refund request carries its own idempotency key, derived from the payment intent
id. Running `unwind` twice with the same context cannot refund twice. Retry it
freely.

## 5. Protect a worker, no engine required

`guard` wraps a step so a rerun asks before it acts. It has no engine dependency and imports straight
from the package, so it works in any plain worker or queue consumer:

```python
from did_it_land import guard, UnknownOutcome

def handle(order_id: str, order_started_at: str):
    return guard(
        capsule,
        {"order_id": order_id, "created_after": order_started_at},
        stripe,
        lambda: create_charge(order_id),   # your real call goes here
        unknown_retries=3,                 # optional: wait and re-ask 3 times
        unknown_wait=5.0)                  # seconds between asks
```

`guard` skips the call when the charge already exists, runs it when it provably does
not, and raises `UnknownOutcome` when the service will not say, after the bounded
patience you gave it. Catch that exception and let your queue redeliver later.

Two things in your own create call make the probe able to see the charge at all.
Attach the order id as metadata, `metadata={"order_id": order_id}`, because that is
what both probes search by, and a charge created without it is invisible to recovery.
Derive the Stripe `Idempotency-Key` from the same order id, for example
`f"charge-{order_id}"`, never from a value minted inside the step. And record
`order_started_at = str(int(time.time()))` when the order begins, because the
capsule's second question walks only the intents created after that moment.

If you do run DBOS, the wiring inside a workflow is in
[python/examples/dbos_charge.py](../python/examples/dbos_charge.py).

## 6. The same thing from TypeScript

The npm package reads the same capsules. You supply the transport, any object with a
`send` method, and throw `TransportError` when the service cannot be reached, so a
timeout counts as "no answer" instead of crashing your recovery:

```ts
import { bundled, reconcile, TransportError } from "did-it-land";

const capsule = bundled().get("stripe.charge");

const stripe = {
  async send(req) {
    const url = "https://api.stripe.com" + req.path
      + "?" + new URLSearchParams(req.query);
    let res;
    try {
      res = await fetch(url, {
        method: req.method,
        headers: { Authorization: "Bearer sk_test_...", ...req.headers },
        signal: AbortSignal.timeout(15000),
      });
    } catch (err) {
      throw new TransportError(String(err));
    }
    return { statusCode: res.status, body: await res.json() };
  },
};

const outcome = await reconcile(
  capsule,
  { order_id: "QS-1", created_after: String(Math.floor(Date.now() / 1000) - 86400) },
  stripe,
);
```

## 7. Where to go next

The other three capsules work the same way in Python with different context fields: bucket and
key for `s3.delete_object`, owner, repo, and pull number for `github.merge_pr`, and a
table, key column, and key value plus a database connection for `postgres.insert`.
One TypeScript exception: `postgres.insert` is a native capsule and the TS runtime
ships no built-in database handlers, so it needs a handler you register with
`registerNative()` first. `did-it-land list` shows them, and each YAML file under
[capsules/](../capsules/) documents its fields and cites its sources. The format
itself is specified in [CAPSULE-SCHEMA.md](CAPSULE-SCHEMA.md), and adding a capsule
for your own service is covered in [CONTRIBUTING.md](../CONTRIBUTING.md).
