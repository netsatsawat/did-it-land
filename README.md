<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-dark.png">
    <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-light.png" alt="did-it-land: the worker died mid-charge. Did it land, and how do you undo it?" width="100%">
  </picture>
</h1>

<p align="center">
  <a href="#-the-problem-in-plain-words">The problem</a> · <a href="#-watch-it-happen-on-your-own-machine">Watch it happen</a> · <a href="#-the-fix-is-a-small-file">The fix</a> · <a href="#-how-one-check-runs">How it runs</a> · <a href="#-where-it-fits-in-a-company-system">Where it fits</a> · <a href="https://github.com/netsatsawat/did-it-land/blob/main/docs/QUICKSTART.md">Quick start</a> · <a href="https://satsawat.ai/#newsletter">Newsletter</a>
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

> Your program charged a customer, then died before it could write that down. When it
> restarts, it charges them again. did-it-land answers the two questions that prevent
> this: did the first charge go through, and if you need to give the money back, how?

## 💸 The problem, in plain words

Many systems run work as a series of steps. Charge the card, update the order, send the
email. The software that runs these steps saves its progress after each one, so if the
machine dies halfway, it can restart and carry on from the last saved point.

Here is the catch. "Charge the card" is really two actions: make the request to the
payment company, and save a note saying the request was made. The machine can die
between those two actions. When that happens, the payment company has the money and
your system has no note. On restart, your system looks at its notes, sees no charge,
and charges again. Nobody wrote a bug. The customer still pays twice.

The picture below walks through what should happen instead:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/workflow.png" alt="Workflow chart: a step calls an outside service, the process crashes before its progress is saved, and recovery asks the service whether the work happened. Yes means skip the retry and reuse the result. No means run the step again with the same key. Unknown means wait and ask again. Both settled paths meet at a saved note recording exactly one effect, and an optional rollback runs the undo step." width="88%">
</p>

Read it top to bottom. A step calls an outside service, and the process dies before
its progress is saved. On restart, nothing reruns blindly. It first asks the service a
direct question: did my earlier request go through? Three answers are possible, and
each gets its own path. **Yes** means the work already
happened, so skip the rerun and use what exists. **No** means it is safe to run the
step now. **Unknown**, for example when the service is briefly down, means wait and ask
again, because acting on a guess is how money gets moved twice. Once the answer is
settled, the system saves its note, and the outside world holds exactly one charge. If
the whole job later needs to be cancelled, the last box runs the undo.

## ⚡ Watch it happen on your own machine

No accounts, no keys, nothing to sign up for. The demo fakes the payment company
inside your own terminal:

```
pip install did-it-land
did-it-land demo
```

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/demo.gif" alt="Terminal recording of the demo staging all three answers: the naive restart charges the customer twice, a landed answer skips the retry, a not landed answer runs the step exactly once, an unknown answer waits for the service and asks again, and the undo issues the refund." width="80%">
</p>

It stages the crash four ways. The naive restart charges twice. Three checked runs
follow, one per answer, and each ends with exactly one charge: the first hears the
charge went through and skips the retry, the second finds nothing and safely runs the
step, and the third gets no answer from a downed service, so it waits and asks again
instead of guessing. Then a refund undoes the landed charge, one call.

## 💊 The fix is a small file

For every kind of action, someone has to know two things. How do you ask the service
whether the action happened, and how do you undo it. That knowledge is different for
every service, it hides in scattered documentation pages, and most teams learn it the
expensive way, after the double charge.

did-it-land collects that knowledge into small files called **capsules**. One file per
action. Here is the one for charging a card with Stripe, shortened:

```yaml
id: stripe.charge
probe:                  # how to ask: did the charge go through?
  request: GET /v1/payment_intents/search?query=metadata["order_id"]:"{order_id}"
  interpret:
    - a payment marked succeeded exists   -> it went through
    - a payment marked processing exists  -> money is moving, wait
    - nothing found                       -> it did not go through
compensation:           # how to undo it: send a refund
  request: POST /v1/refunds
reversibility: refundable, though Stripe keeps its processing fees
source: five links to Stripe's own documentation
```

The full file is
[capsules/stripe.charge.yaml](https://github.com/netsatsawat/did-it-land/blob/main/capsules/stripe.charge.yaml),
and every claim in it links to the page in Stripe's documentation that backs it up.
Those files are the real product. The code around them is small on purpose, and the same
files drive both the Python and the TypeScript versions, so the two can never disagree.

In your own code, the whole thing is two calls. One asks, one undoes:

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

stripe = HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
charge = bundled().get("stripe.charge")

outcome = reconcile(charge, {"order_id": "ORD-1"}, transport=stripe)
if outcome.landed:
    ...        # the charge already happened, do not run it again

unwind(charge, {"payment_intent_id": "pi_123"}, transport=stripe)
```

## 🔍 How one check runs

This picture shows a single check, left to right, in the order the calls happen:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/sequence.png" alt="Sequence diagram, read left to right: the workflow engine asks the guard to check an order. The guard fetches the right capsule from the collection, asks the outside service for the current state, and reports back one of three answers: it went through, it did not, or unknown." width="86%">
</p>

Each vertical line is one of four players. The **engine** on the left is the
software running your steps. When it restarts after a crash, it asks the **guard** to
check on an order. The guard pulls the right **capsule** from the collection, so it
knows exactly how to ask about this kind of action. Then it puts the question to the
**service**, the payment company in our example, and reads the current state from the
reply. Solid arrows are questions going out. Dashed arrows are answers coming back.
The final dashed arrow carries one of three words back to the engine: it went through,
it did not, or we cannot tell yet. The engine acts only on a definite answer. A probe that cannot reach the service at
all, timeouts included, counts as unknown too, never as a no.

## 🏛️ Where it fits in a company system

Zooming out, this is the whole landscape and the one spot did-it-land occupies:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/architecture.png" alt="Architecture diagram: business channels feed an agent layer, which feeds the orchestration layer that runs steps and saves progress. On recovery and rollback the orchestrator consults the side-effect reconciliation layer, whose two halves ask whether a call went through and run the undo. A shared set of lines connects down to the payment provider, object store, message service, and relational database. A dashed arrow carries the answer back up, and an observability box sits alongside." width="94%">
</p>

Top to bottom: people and apps create work, an agent or application decides what to do,
and the orchestration layer runs the steps and saves progress as it goes. On the
ordinary day, that layer talks straight to the systems at the bottom, along the gray
line on the left. The green band is this library, and it is consulted at exactly two
moments: after a crash, to ask "did my call go through?", and during a cancellation,
to run the undo. Its answer travels back up the dashed line as one of the three words.
Note what the green band is not. It is not a platform to install or a service to run.
It is a set of files and two functions, sitting between the layer that runs your steps
and the outside services those steps touch.

## 🧩 What ships today

Four capsules, each for an action where a definite answer exists:

| capsule | how it asks | how it undoes |
|---|---|---|
| `stripe.charge` | search by your own order id | refund, protected against double refunds |
| `s3.delete_object` | ask whether the file still exists | restore, only if versioning was on |
| `github.merge_pr` | read the merged flag, never the branch | no undo exists, a revert is new work |
| `postgres.insert` | look the row up by its business key | delete the same row |

Four is deliberate. An action only earns a capsule when the question "did it happen"
has a reliable answer in the moment you need it. Some services cannot answer in time,
and the honest move is to leave them out rather than ship an answer that arrives too
late. The file format is documented in
[docs/CAPSULE-SCHEMA.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/CAPSULE-SCHEMA.md).

## 🧰 When you need this

The pattern fits any job that both touches an outside system and can die halfway.
Five common shapes:

**Taking payments.** The classic. A checkout flow charges the card and then saves the
order. Any crash between the two risks a double charge, and any cancellation needs a
refund that itself cannot fire twice.

**Agents that act.** An AI agent that books, sends, buys, or files tickets is a series
of steps with real-world effects. When its runtime restarts it, the agent must know
which actions already happened, or it repeats them. This is the enterprise agent
problem the architecture picture above places.

**Cleanup jobs and data pipelines.** A nightly job deletes old files and inserts
summary rows. Rerun it blindly after a crash and you get duplicate rows, or you delete
things twice and lose the ability to restore. Asking first makes reruns boring.

**Release and repo automation.** A bot that merges pull requests must trust the merged
flag, not the branch, because a deleted branch looks exactly like a finished merge.

**Cancelling multi-step work.** An order fails at step four of five. The three
completed steps each need their undo, run in reverse order, and each undo needs the
same protection against running twice. That is what `Saga` and `unwind` are for.

## 🔌 Using it with DBOS

DBOS is one of the engines that restarts crashed work from the last saved step. Wrap a step in `guard` and the rerun asks before it acts. It skips work that already
happened, runs work that did not, and refuses to guess when the answer is unknown. If
you prefer, tell it how many times to wait and ask again before giving up:

```python
from did_it_land import bundled
from did_it_land.adapters.dbos import guard, Saga

charge = bundled().get("stripe.charge")

@DBOS.step()
def charge_customer(order_id: str) -> object:
    return guard(charge, {"order_id": order_id}, stripe, lambda: create_charge(order_id))
```

`Saga` keeps a list of everything a job has done so far, so a failed job can undo its
completed work in reverse order. The list lives in process memory: it survives a
failure inside the job, and a replaying engine rebuilds it, but it does not survive a
bare process crash on its own. The full example is
[python/examples/dbos_charge.py](https://github.com/netsatsawat/did-it-land/blob/main/python/examples/dbos_charge.py).

## 🧪 How it stays honest

Knowledge like this rots. A service changes its behavior, and a test built on old
recordings keeps passing anyway, which is worse than no test. So the tests run in two
tiers. The fast tier runs on every change against local stand-ins, with no accounts
needed, and proves the code and the shape of every capsule. The weekly tier
([drift.yml](https://github.com/netsatsawat/did-it-land/blob/main/.github/workflows/drift.yml))
asks the real services, in their test environments, whether they still behave the way
each capsule says, and writes the date of the last successful check into
[reports/freshness.json](https://github.com/netsatsawat/did-it-land/blob/main/reports/freshness.json).
And the build recomputes every number in this page from the project's own files,
failing when one drifts. One honest note while this is new: the weekly job ships with
this repo but has not accumulated history yet, and the freshness file says so plainly
with a null date until each capsule's first green run.

## 🚫 What this deliberately is not

Not a monitoring platform, not a benchmark, and not another engine for running steps.
It is the ask-and-undo knowledge those engines leave out, written down in one place
and kept current.

## 🗺️ Roadmap

More capsules, each added only together with its weekly real-service check. A
TypeScript engine adapter. The collection stays small on purpose, around a dozen
actions whose behavior barely changes, because a big collection that quietly goes
stale would defeat the whole point.

---

Written by [Satsawat Natakarnkitkul](https://satsawat.ai). Companion article: *The Retry
That Charges Twice* (in draft). Newsletter:
[AI in Practice](https://satsawat.ai/#newsletter). License: MIT.
