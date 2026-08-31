# Changelog

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
