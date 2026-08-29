<h1 align="center">did-it-land</h1>

<p align="center">
  <a href="#-why-this-exists">Why</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="#-sixty-seconds-no-keys">Sixty seconds</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="#-the-four-capsules">The capsules</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="#-using-it-with-dbos">DBOS</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://satsawat.ai/#newsletter">Newsletter</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/did-it-land/"><img src="https://img.shields.io/pypi/v/did-it-land?style=for-the-badge&logo=pypi&logoColor=white&color=2a78d6" alt="PyPI version"></a>
  <a href="https://github.com/netsatsawat/did-it-land/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/netsatsawat/did-it-land/ci.yml?style=for-the-badge&label=CI" alt="CI status"></a>
  <a href="https://github.com/netsatsawat/did-it-land/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/API%20keys-none-1baf7a?style=for-the-badge" alt="No API keys">
  <img src="https://img.shields.io/badge/capsules-4-8a5cf6?style=for-the-badge" alt="4 capsules">
  <a href="https://satsawat.ai"><img src="https://img.shields.io/badge/author-satsawat.ai-e8a112?style=for-the-badge" alt="Author: satsawat.ai"></a>
</p>

> Your durable worker crashed mid-tool-call. Did the charge actually fire, and how do you
> reverse it? did-it-land is the per-vendor knowledge that answers both, as data.

Durable and saga engines (DBOS, Temporal, LangGraph durable, Inngest) resume a crashed
workflow from its last checkpoint, then hand you the hard part: query the vendor to see
whether the side-effect landed, and write your own compensation. did-it-land ships that
per-vendor knowledge as a small corpus of **effect capsules** plus a thin runtime, in
Python and TypeScript, reading the same capsules.

## ⚡ Sixty seconds, no keys

```
pip install did-it-land
did-it-land demo
```

The demo stages the exact failure, with an in-process fake and no network:

```
=== did-it-land demo: did my charge land? ===
A durable worker charges a customer, then crashes before recording the result.

Run A, naive recovery
  attempt 1 : charged, then the worker crashed before the checkpoint
  recovery  : the idempotency key was lost, so the retry uses a new key
  result    : 2 charges for ORD-1, the customer is double charged

Run B, recovery with did-it-land
  attempt 1 : charged, then the worker crashed before the checkpoint
  recovery  : reconcile(stripe.charge, order_id=ORD-1) -> landed
  result    : 1 charge for ORD-1, reconciled, no double charge

Unwind      : unwind(stripe.charge, pi_0001) -> compensated (refund issued)
```

In your own code the two calls are `reconcile` and `unwind`:

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

stripe = HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
charge = bundled().get("stripe.charge")

# After an ambiguous crash: did it land?
outcome = reconcile(charge, {"order_id": "ORD-1"}, transport=stripe)
if outcome.landed:
    ...        # skip the retry, the charge already happened

# Rolling a workflow back:
unwind(charge, {"payment_intent_id": "pi_123"}, transport=stripe)
```

## 🧭 Why this exists

An engine gives you exactly-once for its own checkpoints. It cannot know whether the API
call inside a step succeeded when the process died before the checkpoint committed. On
recovery it re-runs the step, and without the per-vendor probe you either double-charge or
guess. That probe is different for every vendor, it is rarely documented in one place, and
no engine ships it. That knowledge is what did-it-land is.

The moat is not a secret and not a patent. It is the labor of getting each operation right
and keeping it current, which is why the corpus stays deliberately small and definite.

## 🧩 The four capsules

Each capsule answers two questions for one operation: did it land, and how do I reverse it.

| capsule | probe | reversibility |
|---|---|---|
| `stripe.charge` | search by the order id in metadata | reversible, refund the payment intent |
| `s3.delete_object` | HEAD the object | conditionally reversible, only if versioning was on |
| `github.merge_pr` | read the `merged` field, not the branch | irreversible, a revert is a forward commit |
| `postgres.insert` | select by the natural key | conditionally reversible, delete by key |

Every v1 capsule was chosen because its answer is definite in the window that matters. An
operation that can only return `unknown` when you need it does not belong in the corpus.
The format is documented in [docs/CAPSULE-SCHEMA.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/CAPSULE-SCHEMA.md).

## 🔌 Using it with DBOS

DBOS resumes from the last completed step, so a step that called a vendor and crashed
before its checkpoint re-runs on recovery. Wrap the side-effect with `guard`, which probes
first and acts only if the effect has not already landed.

```python
from did_it_land import bundled
from did_it_land.adapters.dbos import guard, Saga

charge = bundled().get("stripe.charge")

@DBOS.step()
def charge_customer(order_id: str) -> object:
    return guard(charge, {"order_id": order_id}, stripe, lambda: create_charge(order_id))
```

`Saga` records each completed effect so a failed workflow can walk them back with `unwind`
in reverse order. See [python/examples/dbos_charge.py](https://github.com/netsatsawat/did-it-land/blob/main/python/examples/dbos_charge.py).

## 🧪 How it is tested

Two tiers, so the default path needs no keys and the corpus still cannot silently rot.

The offline tier runs on every push against local fakes and emulators, proving the runtime
and the shape of each capsule. The scheduled tier ([drift.yml](https://github.com/netsatsawat/did-it-land/blob/main/.github/workflows/drift.yml))
hits real vendor sandboxes weekly to catch API drift and writes
[reports/freshness.json](https://github.com/netsatsawat/did-it-land/blob/main/reports/freshness.json).
A recorded fixture that stays green forever after an API changes is exactly the false
assurance this avoids.

## 🚫 What this deliberately is not

It is not an observability platform, not an eval or a benchmark, and not another durable
engine. It is the per-vendor probe-and-compensation data those engines leave to you, held
in one place and kept honest.

## 🗺️ Roadmap

More capsules, each added only with a live-sandbox drift test attached. A TypeScript
engine adapter. The outbound argument side of a capsule. Held to a dozen stable operations
on purpose, because breadth that must stay current is what sinks a solo corpus.

---

Written by [Satsawat Natakarnkitkul](https://satsawat.ai). Newsletter:
[AI in Practice](https://satsawat.ai/#newsletter). License: MIT.
