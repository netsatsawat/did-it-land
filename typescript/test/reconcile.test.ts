import assert from "node:assert/strict";
import { test } from "node:test";

import { CapsuleError, capsuleFromDoc } from "../src/capsule.ts";
import type { HttpRequest } from "../src/capsule.ts";
import { EffectError, reconcile, unwind } from "../src/reconcile.ts";
import type { Response, Transport } from "../src/reconcile.ts";
import { bundled } from "../src/registry.ts";

class Scripted implements Transport {
  seen: HttpRequest[] = [];
  routes: Map<string, Response>;

  constructor(routes: Map<string, Response>) {
    this.routes = routes;
  }

  send(req: HttpRequest): Response {
    this.seen.push(req);
    const key = `${req.method} ${req.path}`;
    const resp = this.routes.get(key);
    if (!resp) throw new Error(`no route for ${key}`);
    return resp;
  }
}

function route(method: string, path: string, resp: Response): Scripted {
  return new Scripted(new Map([[`${method} ${path}`, resp]]));
}

test("bundled corpus has the four capsules", () => {
  const reg = bundled();
  assert.equal(reg.size, 4);
  assert.deepEqual(reg.ids(), [
    "github.merge_pr",
    "postgres.insert",
    "s3.delete_object",
    "stripe.charge",
  ]);
});

test("stripe probe maps responses to statuses", async () => {
  const capsule = bundled().get("stripe.charge");
  const path = "/v1/payment_intents/search";
  const cases: [Response, string][] = [
    [{ statusCode: 200, body: { data: [{ id: "pi_1" }] } }, "landed"],
    [{ statusCode: 200, body: { data: [] } }, "not_landed"],
    [{ statusCode: 503, body: {} }, "unknown"],
  ];
  for (const [resp, expected] of cases) {
    const t = route("GET", path, resp);
    const outcome = await reconcile(capsule, { order_id: "ORD-1" }, t);
    assert.equal(outcome.status, expected, `status ${resp.statusCode}`);
  }
});

test("s3 probe reads 404 as landed", async () => {
  const capsule = bundled().get("s3.delete_object");
  const ctx = { bucket: "my-bucket", key: "report.csv" };
  const path = "/my-bucket/report.csv";
  assert.equal((await reconcile(capsule, ctx, route("HEAD", path, { statusCode: 404 }))).status, "landed");
  assert.equal((await reconcile(capsule, ctx, route("HEAD", path, { statusCode: 200 }))).status, "not_landed");
});

test("github probe trusts merged, not the branch", async () => {
  const capsule = bundled().get("github.merge_pr");
  const ctx = { owner: "acme", repo: "app", pull_number: "7" };
  const path = "/repos/acme/app/pulls/7";
  assert.equal((await reconcile(capsule, ctx, route("GET", path, { statusCode: 200, body: { merged: true } }))).status, "landed");
  assert.equal((await reconcile(capsule, ctx, route("GET", path, { statusCode: 200, body: { merged: false } }))).status, "not_landed");
});

test("unwind: stripe refunds, github is irreversible", async () => {
  const reg = bundled();
  const stripe = route("POST", "/v1/refunds", { statusCode: 200, body: { id: "re_1" } });
  const comp = await unwind(reg.get("stripe.charge"), { payment_intent_id: "pi_1" }, stripe);
  assert.equal(comp.status, "compensated");
  assert.equal(stripe.seen[0].query.payment_intent, "pi_1");

  const merge = await unwind(reg.get("github.merge_pr"), {});
  assert.equal(merge.status, "irreversible");
});

test("missing context placeholder throws", async () => {
  const capsule = bundled().get("s3.delete_object");
  await assert.rejects(
    () => reconcile(capsule, { bucket: "my-bucket" }, route("HEAD", "/x", { statusCode: 404 })),
    (err: unknown) => err instanceof EffectError && String(err).includes("key"),
  );
});

test("validator rejects a bad capsule", () => {
  assert.throws(
    () => capsuleFromDoc({ id: "x.y" }),
    (err: unknown) => err instanceof CapsuleError,
  );
});
