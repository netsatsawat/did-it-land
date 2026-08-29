# The effectkit capsule schema (v1)

A capsule is the unit of the effectkit corpus. It describes one external operation and
carries the two pieces of knowledge that durable and saga engines leave to you: how to
tell whether the operation landed after an ambiguous crash, and how to reverse it. The
machine-readable contract is `schema/capsule.schema.json`. This page explains the intent
behind each field.

Capsules are data, not code. Both the Python and the TypeScript runtimes read the same
YAML files under `capsules/`. That keeps the corpus, which is the hard part to build,
single-sourced.

## Top-level fields

`id` is `provider.operation`, lowercase, for example `stripe.charge`. It is the stable
handle a runtime and an adapter use to find the capsule.

`provider`, `operation`, and `schema_version` are plain strings. `schema_version` is the
version of this schema the capsule was written against, so a runtime can refuse a capsule
it does not understand.

`summary` and `notes` are prose. `notes` is where the empirical knowledge lives, the part
that reads like a teardown of what it actually takes to know whether the operation
happened. `source` links the vendor doc the capsule was derived from.

## idempotency

How to keep a retry from acting twice.

`strategy` is one of `client_key`, `natural_key`, or `none`. For `client_key`, `header`
names the request header that carries a caller-generated key. For `natural_key`, `keys`
lists the context fields that together identify the row or resource. `none` means the
operation is naturally idempotent and needs no key.

## probe

How to answer "did it land", returning `landed`, `not_landed`, or `unknown`.

`kind` is `http` or `native`. An `http` probe is fully declarative: `request` is a method
and a path template whose `{name}` placeholders bind from the call context, plus optional
`query` and `headers`. `interpret` is an ordered list of rules, and the first one that
matches decides the result. A `native` probe names a `handler` that each language runtime
resolves to a small function, for operations that speak a driver protocol rather than HTTP.

A rule matches on any of `status_in` (a list of HTTP status codes), `json_path` with
`exists`, `equals`, or `count_gte` against the response body. If no rule matches, the
result is `unknown`. Prefer capsules whose answer is definite. An operation that can only
ever return `unknown` in the window that matters does not belong in the corpus.

## reversibility

`class` is `reversible`, `conditionally_reversible`, or `irreversible`. A
`conditionally_reversible` capsule must state its `condition`, the precondition under which
the undo is possible. S3 delete is the canonical example: reversible only if bucket
versioning was on.

## compensation

The inverse operation. `kind` is `http`, `native`, or `none`. An `http` compensation
carries a `request` like a probe does. `none` means there is no true reversal, and the
`notes` should say what the caller's real options are.

## Design rules that keep the corpus honest

Keep the answer definite. Every v1 capsule was chosen because its probe returns a real
yes or no in the window that matters, not because a vendor happens to have an API.

State conditions plainly. If an undo depends on a precondition, name it in `condition`
rather than implying reversibility the operation does not have.

Version the schema. Breaking changes bump `schema_version`, so a runtime can reject what
it cannot read instead of guessing.
