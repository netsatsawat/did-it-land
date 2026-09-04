<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-dark.png">
    <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/banner-light.png" alt="did-it-land: the worker died mid-charge. Did it land, and how do you undo it?" width="100%">
  </picture>
</h1>

<p align="center">
  <a href="#-watch-it-happen-on-your-own-machine">Watch it happen</a> · <a href="#-the-problem-in-plain-words">The problem</a> · <a href="#-the-fix-is-a-small-file">The fix</a> · <a href="#-how-one-check-runs">How it runs</a> · <a href="#-where-it-fits-in-a-company-system">Where it fits</a> · <a href="https://github.com/netsatsawat/did-it-land/blob/main/docs/QUICKSTART.md">Quick start</a> · <a href="https://satsawat.ai/#newsletter">Newsletter</a>
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

did-it-land is a small Python and TypeScript library plus four small text files in YAML
format (a plain text format that both people and programs can read). TypeScript is
JavaScript with types, and node runs it outside a browser. Each of the four files covers
one action on one outside service: charging a card on Stripe (a payment company),
deleting a file on S3 (Amazon's file storage), merging a pull request (a proposed code
change) on GitHub, and inserting a row in a Postgres database. The file says how to ask
the service whether an earlier request went through, and how to undo that request if it
did. You call two functions. The knowledge of how each service answers and undoes
lives in the four files, not in the code.

## The words this page uses

Seven words come up again and again on this page, and the demo output below uses
several of them. Each definition comes from the code or the capsule files.

| word | what it means here |
|---|---|
| workflow engine | Software that runs your job as a list of steps and saves a note after each step finishes. After a crash it restarts from the last saved note, not from the top. DBOS is one such engine. The demo below calls the program that runs the steps a worker. |
| checkpoint | The note the workflow engine saves after each step. The crash this library cares about happens between the outside call and the checkpoint. |
| side effect | A step that changes something outside your program. Money moves, a file is deleted, a row is inserted, a pull request is merged. |
| idempotency key | A label you attach to a request so that sending the same request twice with the same label does the work once. A key alone does not save you, for two reasons. Stripe forgets keys after 24 hours. And if your code creates the key when the step starts, a crash loses it. The retry then makes a brand-new key, and Stripe treats it as a brand-new request. The Stripe capsule links to Stripe's own page on idempotent requests. |
| capsule | One YAML file for one action on one service. It holds the probe, the undo, and links to the service's own documentation. |
| probe | The read-only question a capsule sends to the service to learn whether the earlier request went through. It answers landed, not landed, or unknown. In code the function is `reconcile`. |
| undo | The reverse action for a step that did go through: a refund, a restore, a delete. In code the function is `unwind`, and a finished undo reports `compensated`. Some actions, a merged pull request for one, have no undo. |

## ⚡ Watch it happen on your own machine

No account, no key, nothing to sign up for. The demo runs a fake payment company inside
your own terminal and stages the crash there. You need Python 3.10 or newer.

```
pip install did-it-land
did-it-land demo
```

The install adds a `did-it-land` command to your terminal. If your terminal cannot find
that command, run `python -m did_it_land.cli demo` instead, which does the same thing.

This is what prints. The exact expected output is saved in the repo as
[reports/demo.golden.txt](https://github.com/netsatsawat/did-it-land/blob/main/reports/demo.golden.txt).
The tests check the demo against that file, so your run should match it line for line.

```
=== did-it-land demo: did my charge land? ===
A worker charges a customer, then crashes before recording the result.
The recovery has three possible answers. This stages every one of them.

Run A, naive recovery, no check at all
  attempt 1 : charged, then the worker crashed before the checkpoint
  recovery  : the idempotency key was lost, so the retry uses a new key
  result    : 2 charges for ORD-1, the customer is double charged

Run B, answer: landed. The charge made it out before the crash.
  recovery  : reconcile(stripe.charge, order_id=ORD-1) -> landed
  result    : 1 charge for ORD-1, retry skipped, no double charge

Run C, answer: not landed. The crash hit before the request left.
  recovery  : reconcile(stripe.charge, order_id=ORD-1) -> not_landed
  result    : safe to run, 1 charge for ORD-1, exactly once

Run D, answer: unknown. The service is down when recovery asks.
  recovery  : reconcile(stripe.charge, order_id=ORD-1) -> unknown
  decision  : refuse to act on a guess, wait for the service
  re-probe  : service is back -> landed, retry skipped
  result    : 1 charge for ORD-1, still exactly one

Unwind      : unwind(stripe.charge, pi_0001) -> compensated (refund issued)
```

Read the `result` lines. Run A never asks, so one order ends with 2 charges. Runs B, C
and D each ask first, and each ends with 1 charge. Run D is the one to watch. The
payment company is down when the check runs, so the check gets no answer and waits
instead of guessing. When the service comes back the answer is landed, and the retry is
skipped. The last line is the refund of the charge that did land, one call. `pi_0001`
is the fake payment company's id for that charge, and the refund needs it.

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/demo.gif" alt="Terminal recording of the demo staging all three answers: the naive restart charges the customer twice, a landed answer skips the retry, a not landed answer runs the step exactly once, an unknown answer waits for the service and asks again, and the undo issues the refund." width="80%">
</p>

The same library ships for TypeScript. Install it with `npm install did-it-land` and
import `bundled` (the four capsules that ship inside the package), `reconcile` and
`unwind` from `"did-it-land"`. The demo command is part of the Python package only. The
TypeScript walkthrough is step 6 of
[docs/QUICKSTART.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/QUICKSTART.md).

## 💸 The problem, in plain words

Many systems run work as a series of steps. Charge the card, update the order, send the
email. The workflow engine that runs these steps saves its progress after each one, so
if the program dies halfway, the engine can restart it from the last saved point.

Here is the catch. "Charge the card" is really two actions: make the request to the
payment company, and save a note saying the request was made. The program can die
between those two actions. When that happens, the payment company has the money and
your program has no note. On restart, the engine looks at its notes, sees no charge,
and charges again. Nobody wrote a bug. The customer still pays twice.

The picture below walks through what should happen instead:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/workflow.png" alt="Workflow chart: a step calls an outside service, the program crashes before its progress is saved, and recovery asks the service whether the work happened. Yes means skip the retry and reuse the result. No means run the step again with the same key. Unknown means wait and ask again. Both settled paths meet at a saved note recording exactly one effect, and an optional rollback runs the undo step." width="88%">
</p>

Read it top to bottom. A step calls an outside service, and the program dies before
its progress is saved. On restart, nothing reruns blindly. The engine first asks the
service a direct question: did my earlier request go through? Three answers are
possible. Each gets its own path. **Yes** means the work already happened, so skip
the rerun and use what exists. **No** means it is safe to run the step now.
**Unknown**, for example when the service is briefly down, means wait and ask again,
because acting on a guess is how money gets moved twice. Once the answer is settled,
the engine saves its note, and the outside world holds exactly one charge. If the
whole job later needs to be cancelled, the last box runs the undo.

## 💊 The fix is a small file

Every kind of action raises two questions. How do you ask the service whether the
action happened, and how do you undo it. That knowledge differs by service and hides in
scattered documentation pages, so most teams learn it the expensive way, after the
double charge.

did-it-land writes that knowledge down once per action, in a capsule. Here is the one
for charging a card with Stripe. Below is a shortened, plain-English version of that
file. The real one says the same things with more structure. The last two lines here are
plain summaries. In the real file, those two facts live under their own field names. Two
Stripe words appear in it. A payment intent is Stripe's name for one attempted payment. Metadata is a label
Stripe lets you put on a payment, and the capsule expects your own order id there.

```yaml
id: stripe.charge
probe:                  # how to ask: did the charge go through?
  # GET is a read-only web request. This one searches Stripe's payments for your order id.
  request: GET /v1/payment_intents/search?query=metadata["order_id"]:"{order_id}"
  interpret:
    - a payment marked succeeded exists   -> it went through
    - a payment marked processing exists  -> money is moving, wait
    - nothing found                       -> it did not go through
compensation:           # how to undo it: send a refund
  # POST is a web request that changes something. This one creates the refund.
  request: POST /v1/refunds
reversibility: refundable, though Stripe keeps its processing fees
source: six links to Stripe's own documentation
```

You can read the full file at
[capsules/stripe.charge.yaml](https://github.com/netsatsawat/did-it-land/blob/main/capsules/stripe.charge.yaml).
Its `source` list at the bottom holds six links to Stripe's documentation, so you can
check every claim in the file against Stripe's own words. The capsule files are the
real product. The code around them is small on purpose. A generated copy of the same
files feeds the TypeScript package, and a check script fails if that copy drifts from
the originals.

In your own code, the whole thing is two calls plus a few lines of setup. `reconcile`
asks. `unwind` undoes. The library sends its questions over the network through a piece
called a transport. The built-in one is `HttpxTransport`. It is built on httpx, a
Python package for making web requests, so it needs one extra install:
`pip install "did-it-land[http]"`. Unlike the demo, real use needs a Stripe account and
a test-mode key, the kind where no real money moves. Your code must also attach your
order id to the payment as metadata when it creates the payment, or the probe cannot
find the charge.

```python
from did_it_land import bundled, reconcile, unwind, HttpxTransport

key = "sk_test_..."                # your Stripe test-mode key
order_started_at = "1700000000"    # when the order began, in unix time (seconds since 1970)

# "Bearer <key>" is the form Stripe expects the key in
stripe = HttpxTransport("https://api.stripe.com", headers={"Authorization": f"Bearer {key}"})
# bundled() holds the four capsules that ship inside the package; .get picks one by id
charge = bundled().get("stripe.charge")

context = {"order_id": "ORD-1", "created_after": order_started_at}
# created_after backs up Stripe's search when it lags, explained after this block
outcome = reconcile(charge, context, transport=stripe)
if outcome.landed:
    payment_id = outcome.evidence["ids"][0]   # Stripe's id for the charge that went through
    ...                                       # do not run the charge again
elif outcome.not_landed:
    ...                                       # safe to charge now
else:
    ...                                       # unknown: wait and ask again, never guess

# later, if the whole order is cancelled and the charge did land, give the money back
if outcome.landed:
    unwind(charge, {"payment_intent_id": payment_id}, transport=stripe)
```

`outcome` carries three flags, `landed`, `not_landed` and `unknown`. Exactly one is
True. What the probe saw is in `outcome.evidence`, a dict. If the transport cannot
reach the service, it raises `TransportError`, and `reconcile` reports that error as
unknown rather than as a no.

Two values go in `context`. `order_id` is your own order number, the one you attached as
metadata. `created_after` is the time the order began, in unix time. Stripe's search can
miss a charge made moments ago. So the capsule does not trust an empty search on its
own. When the search comes back empty, the capsule also lists the payments created after
`created_after` and looks for your order id in that list. The list has no search lag.
Only when your order id is missing from that list too does the capsule answer not
landed. Keep `created_after` at the moment the order began. The fallback list then
reaches far enough back to include the charge. That list is capped at 100 payments made
since that time, a number the capsule file sets. If you leave `created_after` at a fixed
date long ago, a busy account can pass 100 payments before yours. Then the capsule cannot
be sure it saw yours. So it answers unknown. After a landed answer,
`outcome.evidence["ids"]` holds the payment intent id the refund needs.

## 🧩 What ships today

Today there are 4 capsules, one per action where a definite answer exists. A test
counts the capsule files, then fails if this page states a different count or misses a
capsule's name.

Two words in the table need defining first. A branch is the copy of the code that a
pull request's change lives on. A business key is an id your own system owned before
the call, such as an order id, so it survives the crash.

| capsule | how it asks | how it undoes |
|---|---|---|
| `stripe.charge` | search Stripe by your own order id | refund, protected against double refunds |
| `s3.delete_object` | ask whether the file still exists | restore, only if versioning was on (an S3 setting that keeps old copies of a file) |
| `github.merge_pr` | read GitHub's `merged` flag, not whether the branch still exists | no undo exists, a revert is new work |
| `postgres.insert` | look the row up by its business key | delete the same row, a clean undo only while nothing else refers to the row yet |

Two rows lean on those words. A branch can vanish whether or not the merge happened, so
its absence tells you nothing. Only the `merged` flag does. A business key survives the
crash, which is why the Postgres probe can trust it to find the row again.

Four is on purpose. An action only earns a capsule when the question "did it happen"
has a reliable answer in the moment you need it. Some services cannot answer in time,
and the honest move is to leave them out rather than ship an answer that arrives too
late. The file format is documented in
[docs/CAPSULE-SCHEMA.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/CAPSULE-SCHEMA.md).

## 🔍 How one check runs

This picture shows a single check, left to right, in the order the calls happen:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/sequence.png" alt="Sequence diagram, read left to right: the workflow engine asks the guard to check an order. The guard fetches the right capsule from the collection, asks the outside service for the current state, and reports back one of three answers: it went through, it did not, or unknown." width="86%">
</p>

Each vertical line is one of four players. The engine on the left is the workflow
engine running your steps. The guard wraps your own step. It is a small piece of this
library that asks the question first, then runs your step only when the answer says
that is safe. When the engine restarts after a crash, it asks the guard to check on an
order. The guard pulls the right capsule from the collection, so it knows exactly how
to ask about this kind of action. Then it puts the question to the service, the payment
company in our example, and reads the current state from the reply. Solid arrows are
questions going out. Dashed arrows are answers coming back. The final dashed arrow
carries one of three words back to the engine: it went through, it did not, or we
cannot tell yet. The engine acts only on a definite answer. A probe that cannot reach
the service at all, timeouts included, counts as unknown too.

## 🏛 Where it fits in a company system

Zoom out, and here are the layers of a company system and the one spot did-it-land
occupies:

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/architecture.png" alt="Architecture diagram: business channels feed an agent layer, which feeds the orchestration layer that runs steps and saves progress. On recovery and rollback the orchestrator consults the side-effect reconciliation layer, whose two halves ask whether a call went through and run the undo. A shared set of lines connects down to the payment provider, object store, message service, and relational database. A dashed arrow carries the answer back up, and an observability box sits alongside." width="94%">
</p>

Start at the top. People and apps create work. An agent (software that plans work
and chooses actions on its own) or an application decides what to do. The orchestration
layer is the workflow engine from the words table. It runs the steps and saves progress
as it goes. On the ordinary day, that layer talks straight to the systems at the bottom,
along the gray line on the left. The green box is this library. The engine consults the
green box at exactly two moments: after a crash, to ask "did my call go through?", and
during a cancellation, to run the undo. Its answer travels back up the dashed line as
one of the three words. Note what the green box is not. It is not a platform to install
or a service to run. The green box is a set of files and two functions, and it sits
between the layer that runs your steps and the outside services those steps touch.

## 🗺 Reading the coverage map

Whether an action earns a capsule comes down to the same two questions a capsule
answers: can you ask whether it landed, and can you undo it if it did? Plot every kind
of action on those two axes and you can see which ones got a capsule and why.

<p align="center">
  <img src="https://raw.githubusercontent.com/netsatsawat/did-it-land/main/assets/recovery-map.png" width="88%" alt="Two panels. Top: a scatter of side effects by whether you can get a definite read-only answer that it landed and how cleanly you can undo it. Postgres, Stripe and the S3 delete sit in fully recoverable, a merged PR in detect-it-can't-undo-it, and email, webhooks and LLM calls are out of scope. Bottom: a risk matrix showing that a guarded retry stays safe at every blast radius (how much damage a rerun can do), while a naive retry of a money-moving step ends in a double charge.">
</p>

The top panel is the capsule map. It has four regions.

- The top right, "fully recoverable", holds a Postgres row, a Stripe charge and an S3
  delete. You can ask with a read-only probe, a lookup or a search, and you can undo,
  with a delete, a refund or a restore. These earn capsules. The S3 delete carries a
  star because the restore works only when versioning was on. The Postgres delete is a
  clean undo only while nothing else refers to the row yet. Nothing in the picture shows
  this condition, but the capsule file states it.
- The bottom right, "detect it, can't undo it", holds a merged pull request. You can
  read the merged flag, but a revert is new work, not an undo. The capsule still earns
  its place by stopping the second merge.
- The top left, "undoable, but you're guessing", is empty. An action lands there when
  you could undo it but cannot get a definite answer about whether it happened, and no
  capsule ships without that answer.
- The bottom left, "deliberately out of scope", holds an email or SMS, a
  fire-and-forget webhook (a web request your system sends to another system and never
  checks on), and a call to a language model (an LLM). No read-only probe gives a
  definite answer in the seconds after a crash, so these are left out rather than
  shipped with an answer that lands too late.

The bottom panel is why `guard` exists. `guard` is the wrapper that asks before it
retries, and the DBOS section below shows it in code. The panel has two axes. Up the
side is how much damage a rerun can do, from a plain read up to moving money. Across
the bottom is how blindly the retry fires: it asks first, it carries only an idempotency
key, or it just reruns. A key on its own is not enough. The words table above gives the
two reasons. A blind rerun of a money-moving step lands in the red "double charge"
cell. `guard` asks first and refuses to act on an unknown
answer, so a step stays in the green "safe to retry" column no matter how much money it
moves.

## 🧰 When you need this

The pattern fits any job that both touches an outside system and can die halfway.
Five common shapes:

- A checkout flow charges the card and then saves the order. The classic case. Any crash
  between the two risks a double charge, and any cancellation needs a refund that itself
  cannot fire twice.
- An AI agent that books, sends, buys, or files tickets is a series of steps with
  real-world effects. When the engine restarts the agent after a crash, the agent must
  know which actions already happened. Otherwise it repeats them. The architecture
  picture above shows where that check sits: between the agent's engine and the
  outside services.
- A nightly cleanup job deletes old files and inserts summary rows. Rerun it blindly
  after a crash and you get duplicate rows, or you delete things twice and lose the
  ability to restore. Asking first makes reruns boring.
- A bot that merges pull requests must trust the merged flag, not the branch, because
  a deleted branch looks exactly like a finished merge.
- An order fails at step four of five. The three completed steps each need their undo,
  run in reverse order, and each undo needs the same protection against running twice.
  `Saga`, a small helper this library ships, keeps the list of completed steps, and
  `unwind` runs each undo. The DBOS section below shows `Saga` in code.

## 🔌 Using it with DBOS

DBOS is one of the engines that restarts crashed work from the last saved step. Wrap a
step in `guard` and the rerun asks before it acts. Landed means `guard` skips your call
and returns `Skipped`. Not landed means `guard` runs your call. Unknown means `guard`
refuses and raises `UnknownOutcome`, so the engine's own retry rules take over. Pass
`unknown_retries=N` if you prefer to wait. `guard` then sleeps `unknown_wait` seconds
(2.0 by default) and asks again, up to N times, before it raises.

```python
from dbos import DBOS
from did_it_land import bundled
from did_it_land.adapters.dbos import guard

charge = bundled().get("stripe.charge")
# stripe is the HttpxTransport from the earlier example
# create_charge is your own function that makes the Stripe call

# the @ line tells DBOS to run this function as one step and save a note when it finishes
@DBOS.step()
def charge_customer(order_id: str, started_at: str) -> object:
    return guard(
        charge, {"order_id": order_id, "created_after": started_at}, stripe,
        lambda: create_charge(order_id))
```

Only a not landed answer makes `guard` run `create_charge`.

`Saga` keeps a list of everything a job has done so far, so a failed job can undo its
completed work in reverse order. The list is kept in memory. A step that raises an
error leaves the list in place for the undo. A killed program loses it. An engine like
DBOS can rebuild the list when it reruns the job. A step is the function you marked with
`@DBOS.step()`. Everything else in your job function is the surrounding code. On a rerun
the engine reuses each step's old result without running it again, but it does run the
surrounding code again. So call `saga.record` right after each step call, out in that
surrounding code. The rerun then adds every finished step back to the list before it
reaches the point of failure. Put a `record` call inside a step and the rerun skips it
along with the step. Then the list is empty exactly when you need it. The full
example is
[python/examples/dbos_charge.py](https://github.com/netsatsawat/did-it-land/blob/main/python/examples/dbos_charge.py).

## 🧪 How it stays honest

Knowledge like this rots. A service changes its behavior, and a test that replays saved
copies of the service's old replies keeps passing anyway. A test like that is worse
than no test. So the tests run in two tiers.

The fast tier runs on every change to the repo against local stand-ins, fake services
that live inside the tests, and needs no account. The badge marked CI at the top of this
page shows whether the latest run of those checks passed. CI stands for continuous
integration, the automated checks a service runs on every change to the repo. This tier
proves the code and the shape of every capsule.

The weekly tier
([drift.yml](https://github.com/netsatsawat/did-it-land/blob/main/.github/workflows/drift.yml))
runs every Monday. It asks the real services whether they still behave the way a
capsule says. No real money moves. The services answer in their test modes. The Stripe
check runs `reconcile` in test mode with an order id that cannot exist. It passes only
when both questions ran and the answer came back not landed. The two questions are the
search and the follow-up list. So a pass covers both Stripe requests the capsule sends,
and how it reads them, not one URL. Then it writes the date of the last successful check into
[reports/freshness.json](https://github.com/netsatsawat/did-it-land/blob/main/reports/freshness.json).

Two notes while this is new. The weekly job ships with this repo but has no history
yet. The freshness file says so plainly, with no date for any capsule until its first
passing live check. And the live check covers `stripe.charge` today. The other three
are checked offline until their own live checks are written.

## 🚫 What this deliberately is not

did-it-land is the ask-and-undo knowledge that workflow engines leave out, written down
in one place and kept current. It does not run your steps, and it is not a benchmark or a
monitor. The engine already runs your steps.

## 🗺 Roadmap

More capsules, each added only together with its weekly real-service check. The
collection stays small on purpose, around a dozen actions whose behavior barely
changes, because a big collection that quietly goes stale would defeat the whole
point.

The full plan is in [docs/ROADMAP.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/ROADMAP.md), and the operations deliberately left out, with the rule every capsule has to pass, are in [docs/WHY-NOT.md](https://github.com/netsatsawat/did-it-land/blob/main/docs/WHY-NOT.md).

---

Written by [Satsawat Natakarnkitkul](https://satsawat.ai). Companion article: *The Retry
That Charges Twice* (in draft). Newsletter:
[AI in Practice](https://satsawat.ai/#newsletter). License: MIT.
