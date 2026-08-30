# Contributing

The most valuable contribution here is a new capsule, because the collected knowledge
is the product. Bug reports and fixes are welcome through ordinary issues and pull
requests. This page is mostly about capsules, since they carry rules the code cannot
enforce alone.

## The bar for a new capsule

One rule decides everything: **the probe must return a definite answer in the moment
after a crash.** Ask yourself, if my process died mid-call, could I query the service
right now and learn whether the call went through, yes or no? If the service can only
answer "probably" or "check back tomorrow", the operation does not belong in this
collection, no matter how popular the service is. We would rather ship four honest
capsules than forty hopeful ones.

Operations also score higher when their behavior barely changes over time, because
every capsule joins a weekly freshness check for the rest of its life.

## Adding a capsule, step by step

1. **Write the file.** One YAML per operation at `capsules/<provider>.<operation>.yaml`,
   following [docs/CAPSULE-SCHEMA.md](docs/CAPSULE-SCHEMA.md). Look at
   [capsules/stripe.charge.yaml](capsules/stripe.charge.yaml) for the fullest example.
2. **Cite everything.** Every behavioral claim needs a link in `source` to the
   service's own documentation. A capsule is trusted knowledge, and trust starts with
   showing your receipts.
3. **Mirror the corpus.** Run `python3 scripts/sync_corpus.py` and
   `python3 scripts/build_ts_corpus.py`. CI fails if either copy drifts.
4. **Add offline tests in both runtimes.** Scripted-response tests proving each
   interpret rule: the landed case, the not landed case, and the unknown case, plus
   the compensation. See `python/tests/test_reconcile.py` and
   `typescript/test/reconcile.test.ts` for the pattern.
5. **Add the live drift check.** Write the capsule's weekly probe against the
   service's own test environment in `scripts/drift_check.py`, and add the capsule's
   entry to `reports/freshness.json`. New capsules do not merge without one, because
   unverifiable knowledge rots silently. Honesty note: of the four founding capsules
   only `stripe.charge` has its live harness so far, and closing that gap is open
   work a contribution could claim.
6. **Update the README.** The capsule table and the capsule-count badge. CI recomputes
   the numbers and fails on a mismatch, so honesty is mechanical here.
7. **Run the gates.** `make test`, `make test-ts`, and `make verify` must all pass.
   The TypeScript tests run through Node's native type stripping, which needs Node
   22.18 or newer for development. Consumers of the built package still only need
   Node 18.

If you also want to write a short teardown of what it took to get the probe right,
those posts are how the next contributor finds this project, and we will link it from
the README.

## Code style, the short version

Hand-formatted Python at roughly 90 columns: break after an opening bracket, pack the
contents, closing bracket stays on the last line. Plain `unittest`, not pytest. No
linters or formatters are configured, on purpose. Match the file you are editing.
Docstrings explain why, not just what.

## Reporting problems

A capsule that misreads a service is a serious bug even when no code is wrong, since
someone may act on the answer. Open an issue with the capsule id, what the service
returned, and what the capsule concluded. For anything security-sensitive, see
[SECURITY.md](SECURITY.md).
