# The did-it-land capsule schema (v1)

A capsule is the unit of the did-it-land corpus. It describes one external operation and
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

A rule has exactly two keys: its conditions nest under `when`, and `result` sits beside
it. Conditions are `status_in` (a list of HTTP status codes) and `json_path` combined
with `exists`, `equals`, or `count_gte` against the response body. When the `json_path`
target is an array, an optional `where` map filters its elements first: each key is a
field name, dotted paths like `metadata.order_id` reach into nested objects, and a
string value may carry a `{name}` placeholder bound from the call context. Elements
that survive the filter are what `count_gte` counts, and their ids surface in the
outcome's evidence. Unknown keys are rejected, in the JSON schema and the runtime both,
because a typo that silently vanished would leave a rule with no conditions, and a rule
with no conditions matches everything.

A probe may also declare `confirm`, a second request-and-interpret pair asked only when
the primary rules answer `not_landed`. Some services answer their fast search from an
index that trails the truth, and "it never happened" from a lagging index is how double
charges get approved. The confirm is the lag-free second question, its verdict wins,
and it stamps `confirmed: true` into the evidence. All three features together, in the
shape the Stripe capsule uses:

```yaml
interpret:
  - when:
      status_in: [200]
      json_path: data
      where:
        metadata.order_id: "{order_id}"
        status: succeeded
      count_gte: 1
    result: landed
  - when:
      status_in: [200]
    result: not_landed
confirm:
  request:
    method: GET
    path: /v1/payment_intents
    query: {limit: "100", "created[gte]": "{created_after}"}
  interpret:
    - when:
        status_in: [200]
        json_path: data
        where: {metadata.order_id: "{order_id}", status: succeeded}
        count_gte: 1
      result: landed
    - when: {status_in: [200], json_path: has_more, equals: true}
      result: unknown
    - when: {status_in: [200]}
      result: not_landed
```

The confirm leads with the same landed rule as the primary, so a charge sitting in the
lag-free answer is found, not skipped past. And the time bound is what keeps has_more
honest: unbounded, a mature account always has more history and the rule would jam on
unknown forever, but within the order's own window it means a real burst.

If no rule matches, the result is `unknown`. Prefer capsules whose answer is definite.
An operation that can only ever return `unknown` in the window that matters does not
belong in the corpus.

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
