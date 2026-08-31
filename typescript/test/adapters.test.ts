import assert from "node:assert/strict";
import { test } from "node:test";

import type { HttpRequest } from "../src/capsule.ts";
import type { Response, Transport } from "../src/reconcile.ts";
import { bundled } from "../src/registry.ts";
import { Saga, Skipped, UnknownOutcome, guard } from "../src/adapters.ts";

class OneRoute implements Transport {
  seen: HttpRequest[] = [];
  response: Response;

  constructor(response: Response) {
    this.response = response;
  }

  send(req: HttpRequest): Response {
    this.seen.push(req);
    return this.response;
  }
}

const CTX = { order_id: "ORD-1", created_after: "1700000000" };

test("guard skips the call when the effect already landed", async () => {
  const capsule = bundled().get("stripe.charge");
  const landed = new OneRoute({ statusCode: 200, body: { data: [{ id: "pi_1", status: "succeeded" }] } });
  const calls: string[] = [];
  const result = await guard(capsule, CTX, landed, () => calls.push("did"));
  assert.ok(result instanceof Skipped);
  assert.deepEqual(calls, []);
});

test("guard runs the call when the effect has not landed", async () => {
  const capsule = bundled().get("stripe.charge");
  const empty = new OneRoute({ statusCode: 200, body: { data: [] } });
  const result = await guard(capsule, CTX, empty, () => "charged");
  assert.equal(result, "charged");
});

test("guard refuses to act on an unknown answer", async () => {
  const capsule = bundled().get("stripe.charge");
  const outage = new OneRoute({ statusCode: 503, body: {} });
  const calls: string[] = [];
  await assert.rejects(
    () => guard(capsule, CTX, outage, () => calls.push("did")),
    (err: unknown) => err instanceof UnknownOutcome && err.outcome.status === "unknown",
  );
  assert.deepEqual(calls, [], "an unknown probe result must never fire the side effect");
});

test("guard waits, then succeeds once the answer arrives", async () => {
  const capsule = bundled().get("stripe.charge");
  const answers: Response[] = [
    { statusCode: 503, body: {} },
    { statusCode: 503, body: {} },
    { statusCode: 200, body: { data: [{ id: "pi_1", status: "succeeded" }] } },
  ];
  const sequenced: Transport = { send: () => answers.shift() as Response };
  const naps: number[] = [];
  const result = await guard(capsule, CTX, sequenced, () => "charged", {
    unknownRetries: 2,
    unknownWait: 5.0,
    sleep: (s) => { naps.push(s); },
  });
  assert.ok(result instanceof Skipped);
  assert.deepEqual(naps, [5.0, 5.0], "one wait per unknown answer, then success");
});

test("guard gives up after bounded retries", async () => {
  const capsule = bundled().get("stripe.charge");
  const outage = new OneRoute({ statusCode: 503, body: {} });
  const naps: number[] = [];
  await assert.rejects(
    () => guard(capsule, CTX, outage, () => "charged", {
      unknownRetries: 2,
      unknownWait: 1.0,
      sleep: (s) => { naps.push(s); },
    }),
    UnknownOutcome,
  );
  assert.equal(naps.length, 2, "bounded patience, never an open-ended hang");
  assert.equal(outage.seen.length, 3, "initial probe plus two retries");
});

test("guard treats money in flight as unknown", async () => {
  const capsule = bundled().get("stripe.charge");
  const processing = new OneRoute({ statusCode: 200, body: { data: [{ id: "pi_1", status: "processing" }] } });
  await assert.rejects(
    () => guard(capsule, CTX, processing, () => "charged"),
    UnknownOutcome,
  );
});

test("saga surfaces a wrong context key as a loud error, never a silent skip", async () => {
  // The compensation template binds {payment_intent_id}. Recording only the order
  // id must surface as an error result at compensate time, not a skipped refund.
  const capsule = bundled().get("stripe.charge");
  const saga = new Saga();
  saga.record(capsule, { order_id: "ORD-1" }, new OneRoute({ statusCode: 200, body: {} }));
  const results = await saga.compensate();
  assert.deepEqual(results.map((r) => r.status), ["error"]);
  assert.match(String(results[0].evidence?.error), /payment_intent_id/);
});

test("one bad step does not strand the rest", async () => {
  const capsule = bundled().get("stripe.charge");
  const transport = new OneRoute({ statusCode: 200, body: { id: "re_ok" } });
  const saga = new Saga();
  saga.record(capsule, { payment_intent_id: "pi_good" }, transport);
  saga.record(capsule, { order_id: "wrong-key" }, transport);
  const results = await saga.compensate();
  assert.deepEqual(results.map((r) => r.status), ["error", "compensated"]);
  assert.match(String(results[0].evidence?.error), /payment_intent_id/);
  assert.equal(transport.seen[0].query.payment_intent, "pi_good");
});

test("compensate walks the effects in reverse", async () => {
  const capsule = bundled().get("stripe.charge");
  const transport = new OneRoute({ statusCode: 200, body: { id: "re_x" } });
  const saga = new Saga();
  saga.record(capsule, { payment_intent_id: "pi_first" }, transport);
  saga.record(capsule, { payment_intent_id: "pi_second" }, transport);
  assert.equal(saga.size, 2);
  const results = await saga.compensate();
  assert.deepEqual(results.map((r) => r.status), ["compensated", "compensated"]);
  assert.deepEqual(transport.seen.map((r) => r.query.payment_intent), ["pi_second", "pi_first"]);
});
