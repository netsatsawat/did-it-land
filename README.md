<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-dark.png">
    <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-light.png" alt="did-it-land: the worker died mid-charge. Did it land, and how do you undo it?" width="100%">
  </picture>
</h1>

<p align="center">
  <a href="#-the-problem">The problem</a> · <a href="#-see-it-fail-then-see-the-fix">See it fail</a> · <a href="#-what-a-capsule-is">Capsules</a> · <a href="#-using-it-with-dbos">DBOS</a> · <a href="https://satsawat.ai/#newsletter">Newsletter</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/did-it-land/"><img src="https://img.shields.io/pypi/v/did-it-land?style=for-the-badge&logo=pypi&logoColor=white&color=2a78d6" alt="PyPI version"></a>
  <a href="https://github.com/netsatsawat/did-it-land/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/netsatsawat/did-it-land/ci.yml?style=for-the-badge&label=CI" alt="CI status"></a>
  <a href="https://github.com/netsatsawat/did-it-land/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/TypeScript-node%2018%2B-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript, node 18+">
  <img src="https://img.shields.io/badge/API%20keys-none-1baf7a?style=for-the-badge" alt="No API keys">
  <img src="https://img.shields.io/badge/capsules-4-8a5cf6?style=for-the-badge" alt="4 capsules">
  <a href="https://satsawat.ai"><img src="https://img.shields.io/badge/author-satsawat.ai-e8a112?style=for-the-badge" alt="Author: satsawat.ai"></a>
</p>

> Your worker charged a customer, then died before it could write that down. The engine
> re-runs the step. The customer pays twice. did-it-land is the per-vendor knowledge that
> stops this: did the call land, and how do you reverse it, shipped as data.

## 💸 The problem

Durable workflow engines (DBOS, Temporal, LangGraph durable, Inngest) checkpoint your
workflow and resume it after a crash. Inside their own state, the guarantee is real. But
a step that calls Stripe does two things: it makes the call, and it records that the
call happened. Those are separate writes to separate systems. When the process dies
between them, the vendor has the money and your engine has nothing. On recovery, the
engine re-runs the step, because as far as it can tell the step never ran.

Every engine's documentation answers this with "make your steps idempotent" and moves
on. That is the homework this repo does for you. Answering "did the call land" takes
vendor-specific knowledge: which endpoint to ask, which field to trust, which statuses
mean money moved, and when the honest answer is "wait and ask again". Reversing the call
takes more of the same. No engine ships that knowledge, because it lives in each
vendor's docs and in the memories of people who already paid for the lesson.

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/workflow.png" alt="Workflow chart of crash recovery: a step calls an external service, the process crashes before the checkpoint, recovery probes with the operation's capsule, and a decision follows. Landed skips the retry, not landed runs the step with the same idempotency key, unknown waits and probes again. Both resolved paths meet at a checkpoint with exactly one effect, and an optional rollback runs the compensation." width="72%">
</p>

## ⚡ See it fail, then see the fix

No keys, no network, one screen:

```
pip install did-it-land
did-it-land demo
```

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/demo.gif" alt="Terminal replay of the demo: naive recovery double-charges the customer, recovery with did-it-land reconciles to a single charge, then unwind issues the refund." width="80%">
</p>

The demo stages the crash twice against an in-process fake Stripe. Naive recovery mints
a fresh idempotency key and charges again. The did-it-land path asks first, hears
"landed", and skips the retry. Then it reverses the charge with one call.

## 💊 What a capsule is

One YAML file per external operation, carrying the answers to both questions:

```yaml
id: stripe.charge
probe:                  # did it land?
  request: GET /v1/payment_intents/search?query=metadata["order_id"]:"{order_id}"
  interpret:
    - status succeeded present    -> landed
    - status processing present   -> unknown, money is in flight
    - otherwise on 200            -> not_landed
compensation:           # how do I reverse it?
  request: POST /v1/refunds
  headers: {Idempotency-Key: did-it-land-refund-{payment_intent_id}}
reversibility: reversible, but Stripe keeps the fees
source: five links to Stripe's own documentation
```

That excerpt is abridged. The real capsule is
[capsules/stripe.charge.yaml](https://github.com/netsatsawat/did-it-land/blob/main/capsules/stripe.charge.yaml),
and every claim in it cites the vendor's documentation. The corpus is the product. Both
runtimes stay thin on purpose and read the same files, so Python and TypeScript can
never disagree about what a probe means.

In code, the whole surface is two calls:

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

stripe = HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
charge = bundled().get("stripe.charge")

outcome = reconcile(charge, {"order_id": "ORD-1"}, transport=stripe)
if outcome.landed:
    ...        # the charge already happened, do not retry

unwind(charge, {"payment_intent_id": "pi_123"}, transport=stripe)
```

Under the hood, one reconcile call is this exchange:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/sequence.png" alt="UML sequence diagram: the durable workflow engine calls reconcile on the guard, the guard looks the operation up in the effect corpus and receives its capsule, probes the external API and receives the current state, then returns landed, not landed, or unknown to the engine." width="80%">
</p>

## 🏛️ Where it sits in an enterprise stack

Between the orchestration layer and the systems of record. The durable engine keeps
calling services directly on the happy path. On recovery and rollback it consults the
reconciliation layer, which probes or compensates per capsule and hands back a verdict.

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/architecture.png" alt="Enterprise architecture diagram in neutral terms: business channels feed an agent layer, which feeds durable orchestration. On recovery and rollback the orchestrator consults the side-effect reconciliation layer, whose probe and undo halves talk to the systems of record: a payment provider, an object store, a message service, and a relational database. The verdict, landed, not landed, or unknown, returns to the orchestrator, with observability and audit alongside." width="90%">
</p>

## 🧩 The four capsules

| capsule | did it land? | how do I reverse it? |
|---|---|---|
| `stripe.charge` | search by your order id in metadata, read status client-side | refund, with its own idempotency key |
| `s3.delete_object` | HEAD the object | restore the version, only if versioning was on |
| `github.merge_pr` | trust the `merged` field, never the branch | you cannot, a revert is a forward commit |
| `postgres.insert` | select by the natural key | delete by the same key |

Four is deliberate. I chose each operation because its probe returns a definite answer
in the window that matters, and an operation that can only say "unknown" when you need
it does not belong here. The format is specified in
[docs/CAPSULE-SCHEMA.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/CAPSULE-SCHEMA.md).

## 🔌 Using it with DBOS

DBOS resumes from the last completed step, so a step that crashed after calling the
vendor re-runs on recovery. Wrap the side effect in `guard`, which probes first, acts
only on a definite "not landed", and refuses to guess on "unknown":

```python
from did_it_land import bundled
from did_it_land.adapters.dbos import guard, Saga

charge = bundled().get("stripe.charge")

@DBOS.step()
def charge_customer(order_id: str) -> object:
    return guard(charge, {"order_id": order_id}, stripe, lambda: create_charge(order_id))
```

`Saga` records each completed effect so a failed workflow can walk them back with
`unwind` in reverse order. The full wiring is in
[python/examples/dbos_charge.py](https://github.com/netsatsawat/did-it-land/blob/main/python/examples/dbos_charge.py).

## 🧪 How it stays honest

A frozen test fixture stays green forever, even after the vendor changes its API, and a
green light on stale knowledge is worse than no light. So testing runs in two tiers.
The offline tier runs on every push against local fakes, with no keys, proving the
runtimes and the shape of every capsule. The scheduled tier
([drift.yml](https://github.com/netsatsawat/did-it-land/blob/main/.github/workflows/drift.yml))
hits real vendor sandboxes weekly and stamps
[reports/freshness.json](https://github.com/netsatsawat/did-it-land/blob/main/reports/freshness.json)
with the date each capsule was last confirmed against the live API. CI also recomputes
every number this README states from the committed artifacts, and fails when one drifts.

## 🚫 What this deliberately is not

Not an observability platform, not an eval, not a benchmark, and not another durable
engine. It is the per-vendor probe-and-undo data those engines leave as an exercise for
the reader, collected in one place and kept current.

## 🗺️ Roadmap

More capsules, each added only with a live-sandbox drift test attached. A TypeScript
engine adapter. The outbound argument side of a capsule. The corpus stays at a dozen or
so stable operations on purpose, because breadth that must stay current is what turns a
corpus into folklore.

---

Written by [Satsawat Natakarnkitkul](https://satsawat.ai). Companion article: *The Retry
That Charges Twice* (in draft). Newsletter:
[AI in Practice](https://satsawat.ai/#newsletter). License: MIT.
