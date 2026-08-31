# Why these are not capsules

did-it-land only covers an operation when a read-only probe can give a definite answer in the
seconds after a crash. The rejections are as much the point as the inclusions: four capsules
of fact beat fifty of folklore.

## The bar

A new capsule has to pass all three:

1. **A key that survives the crash** — an identifier the workflow already owns, not one the
   vendor assigns in a response you just lost.
2. **A read-only API keyed by it** — a way to ask "did this land" without causing a side
   effect.
3. **Strong consistency, or a lag-free confirm fallback** — the answer has to be trustworthy
   immediately after the write, not "eventually."

Miss any one and the honest answer is `unknown`, and an `unknown`-only operation does not
belong in the corpus.

## Deliberately left out

- **Queue and stream sends** (`sqs.send_message`, `kafka.produce`, `pubsub.publish`). There is
  no read-by-your-key: receiving the message consumes or moves it. The broker offers
  deduplication (SQS FIFO ids, Kafka idempotent-producer sequence numbers), which is
  idempotency, not a probe. You cannot ask whether it landed.
- **`github.dispatch_workflow`.** The trigger returns no run id, so you cannot correlate which
  run is yours in time.
- **`github.create_issue`.** The issue number is server-assigned and lost in the crash.
  Searching by a body marker rides GitHub's eventually consistent, rate-limited search index,
  so there is no definite answer in the window.
- **Email, SMS, and chat** (SendGrid, Postmark, Twilio, Slack `chat.postMessage`). The only
  identifier is the message id in the response you just lost. No lookup by your own business
  key.
- **LLM calls.** No idempotency handle, the response is lost on a crash, and the output is
  non-deterministic anyway.
- **`redis.set`.** A `GET` that returns nothing cannot tell "never set" from "set then expired
  or overwritten," so `not_landed` is not definite.
- **Reference-only payment APIs** (Adyen and similar). Correlating your own reference back to a
  payment state usually needs the provider reference from the response, which is weaker than
  Stripe's searchable metadata plus a lag-free List. Left out until a definite lag-free path is
  proven.

Some of these could join later if a vendor ships a probe that clears the bar. Until then, the
honest move is to say so.
