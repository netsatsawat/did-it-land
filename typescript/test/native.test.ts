import assert from "node:assert/strict";
import { test } from "node:test";

import { EffectError, reconcile, unwind } from "../src/reconcile.ts";
import { bundled } from "../src/registry.ts";
import type { Connection, QueryResult } from "../src/native.ts";
import "../src/native.ts"; // side effect: registers the postgres handlers

// A tiny in-memory stand-in for a node-postgres connection. It knows the two
// statements the handlers issue and answers by a set of present keys, the way the
// Python tests drive the same handlers through sqlite.
class FakeDb implements Connection {
  keys: Set<string>;
  seen: { text: string; values: unknown[] }[] = [];

  constructor(present: string[]) {
    this.keys = new Set(present);
  }

  query(text: string, values: unknown[]): QueryResult {
    this.seen.push({ text, values });
    const key = String(values[0]);
    if (text.startsWith("SELECT")) {
      return this.keys.has(key) ? { rows: [{ n: 1 }], rowCount: 1 } : { rows: [], rowCount: 0 };
    }
    if (text.startsWith("DELETE")) {
      const had = this.keys.delete(key);
      return { rows: [], rowCount: had ? 1 : 0 };
    }
    throw new Error(`unexpected sql: ${text}`);
  }
}

function ctx(conn: Connection, keyValue: string): Record<string, unknown> {
  return { connection: conn, table: "orders", key_column: "order_ref", key_value: keyValue };
}

test("native probe reports landed and not_landed", async () => {
  const capsule = bundled().get("postgres.insert");
  const db = new FakeDb(["ORD-1"]);
  assert.equal((await reconcile(capsule, ctx(db, "ORD-1"))).status, "landed");
  assert.equal((await reconcile(capsule, ctx(db, "ORD-9"))).status, "not_landed");
});

test("native compensation deletes the row, then it reads not_landed", async () => {
  const capsule = bundled().get("postgres.insert");
  const db = new FakeDb(["ORD-1"]);
  const result = await unwind(capsule, ctx(db, "ORD-1"));
  assert.equal(result.status, "compensated");
  assert.equal((await reconcile(capsule, ctx(db, "ORD-1"))).status, "not_landed");
});

test("compensation on a missing row is a no-op", async () => {
  const capsule = bundled().get("postgres.insert");
  const db = new FakeDb(["ORD-1"]);
  const result = await unwind(capsule, ctx(db, "ORD-9"));
  assert.equal(result.status, "no_compensation");
});

test("the identifier whitelist blocks injection", async () => {
  const capsule = bundled().get("postgres.insert");
  const db = new FakeDb(["ORD-1"]);
  const bad = ctx(db, "ORD-1");
  bad.table = "orders; DROP TABLE orders";
  await assert.rejects(
    () => reconcile(capsule, bad),
    (err: unknown) => err instanceof EffectError && /not a safe SQL identifier/.test(String(err)),
  );
  assert.deepEqual(db.seen, [], "a rejected identifier must never reach the driver");
});

test("a native capsule needs a connection", async () => {
  const capsule = bundled().get("postgres.insert");
  await assert.rejects(
    () => reconcile(capsule, { table: "orders", key_column: "order_ref", key_value: "x" }),
    (err: unknown) => err instanceof EffectError && /connection/.test(String(err)),
  );
});
