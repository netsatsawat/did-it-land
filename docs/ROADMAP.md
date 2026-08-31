# Roadmap

did-it-land grows on purpose, not on demand. The ceiling is about a dozen capsules, and a
capsule only earns a slot when a read-only probe can give a definite answer in the seconds
after a crash. The real cost of a capsule is not the YAML, it is keeping its weekly drift
check green forever, so the ordering below earns trust on what already ships before adding
anything new.

See [WHY-NOT.md](WHY-NOT.md) for the operations that are deliberately left out, and the
rule every new capsule has to pass.

## 0.2.0 — close the gaps, stand up the drift history

- **Live drift checks for the other three capsules.** Only `stripe.charge` has a weekly
  real-service check today; `s3.delete_object`, `github.merge_pr`, and `postgres.insert`
  are verified offline. Postgres is the cheapest: a real Postgres container in CI is the
  genuine vendor, so the check is hermetic and needs no secrets. GitHub runs against a
  throwaway repo. Every new harness asserts both `landed` and `not_landed`, which also
  fixes the gap that the Stripe check exercises only one direction.
- **`did-it-land lint`.** The JSON schema validates shape; it cannot enforce the design
  rules. A linter should reject a capsule with no `source`, an HTTP probe that does not map
  outage codes (429/500/502/503) to `unknown`, an `irreversible` class paired with a real
  compensation, or a `conditionally_reversible` with no condition. This mechanizes the bar
  so it survives contributors who are not the author.
- **TypeScript CLI and example.** Python ships `list`/`validate`/`demo`/`schema` and a DBOS
  example; TypeScript ships neither yet. Match `list` and `validate` at least, plus one
  `guard` example.
- **Machine-readable output.** `--json` on `list` and `validate`, and a `freshness` command
  that prints each capsule's last live-check age from `reports/freshness.json`.
- **New capsule: `github.create_release`.** Probe
  `GET /repos/{owner}/{repo}/releases/tags/{tag}` (200 landed, 404 not_landed); compensation
  `DELETE .../releases/{id}`, conditionally reversible. A strongly consistent point-read with
  no index lag, on the existing HTTP engine.

## 0.3.0 — measured growth

- **`gcs.delete_object`.** The S3 analog in the other cloud. Probe the object read
  (404 means gone, so landed); conditionally reversible via versioning. Its drift check needs
  real GCP credentials, because an emulator can drift from the real API, and marking a capsule
  "verified live" against an emulator would be dishonest.
- **One second database.** Either `mysql.insert` (near-zero new logic, hermetic container
  check) or `dynamodb.put_item` (a consistent read is a genuinely different proof, but needs
  real AWS credentials). Pick one, not both. This is where sprawl starts: a stack of "the same
  capsule with a different driver" is low information.
- **Live drift for `s3.delete_object`** against real AWS, finishing the trust matrix.
- **Temporal adapter example.** `guard` and `Saga` are engine-free, so this is a thin wrapper
  plus an example, never a runtime dependency. Examples only, and stop here unless a user asks
  for another engine.
- **Freshness surfacing.** A badge fed from `freshness.json`, and stale-flagging in the
  `freshness` command.

## Beyond 0.3.0 — hold the line

Only two more capsules are worth naming, and both teach rather than fill coverage:
`stripe.capture` (a strongly consistent point-read, the clean contrast to `stripe.charge`'s
lag-free confirm fallback) and `s3.put_object` (definite only when you know the expected
ETag, so a conditionally reversible capsule whose condition is load-bearing). Payment APIs
move fastest, so Stripe stays capped at one more.

Nothing past this earns a slot without displacing something. The ceiling is real.

## Done

- **0.1.1** — TypeScript reached parity with Python: `guard`, `Saga`, and the native Postgres
  handlers, so both runtimes run all four capsules.
