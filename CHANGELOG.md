# Changelog

## 0.1.2

A documentation release, no code or capsule changes. The PyPI long description no longer
opens the Stripe example with `key` used before it is assigned, and the TypeScript
quickstart no longer tells you to call `registerNative()` for Postgres, which the runtime
has auto-registered on import since 0.1.1. The README is rewritten to lead a first-time
reader from the problem to a working example, and ROADMAP and WHY-NOT docs are added.

## 0.1.1

The TypeScript runtime reaches parity with Python. It gains `guard` and `Saga`, the
engine-free pair that lets a durable step reconcile before it re-charges and walk a
failed workflow's recorded effects back in reverse, and the native Postgres handlers,
so TypeScript now runs all four capsules rather than the three HTTP ones alone. The
capsules themselves are unchanged. On the release side, npm now publishes through OIDC
trusted publishing instead of a token, and the PyPI publish skips a version that
already exists, so a re-run is safe.

## 0.1.0

First release. Four effect capsules (`stripe.charge`, `s3.delete_object`,
`github.merge_pr`, `postgres.insert`), the Python runtime (`reconcile`, `unwind`,
registry, the `did-it-land` CLI), the engine-free `guard` and `Saga` with bounded
patience on unknown answers, a lag-free confirm fallback for probes that can trail
the truth, the DBOS reference adapter and example, a no-keys demo staging every
answer, and the TypeScript runtime reading the same corpus.
