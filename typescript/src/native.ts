// Native handlers for capsules that speak a driver protocol rather than HTTP.
//
// A native capsule names a handler id; this module resolves it to a small object with a
// probe and a compensate method, mirroring the Python native handlers. The built-in
// Postgres handlers are driver-agnostic: the caller passes a connection in the context
// whose query(text, values) returns { rows, rowCount }, the shape node-postgres uses.
// Only whitelisted identifiers are ever interpolated into SQL, and values always go
// through the driver's own parameter binding.

import type { Capsule } from "./capsule.ts";
import {
  type CompensationResult,
  EffectError,
  type NativeHandler,
  type Outcome,
  registerNative,
} from "./reconcile.ts";

export interface QueryResult {
  rows: unknown[];
  rowCount?: number | null;
}

export interface Connection {
  query(text: string, values: unknown[]): QueryResult | Promise<QueryResult>;
}

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const PLACEHOLDER: Record<string, string> = {
  numbered: "$1", qmark: "?", format: "%s", pyformat: "%s",
};

function ident(name: unknown, where: string): string {
  const s = String(name);
  if (!IDENT.test(s)) throw new EffectError(`${where}: '${s}' is not a safe SQL identifier`);
  return s;
}

function placeholder(context: Record<string, unknown>): string {
  return PLACEHOLDER[String(context.paramstyle ?? "numbered")] ?? "$1";
}

function connection(capsule: Capsule, context: Record<string, unknown>): Connection {
  const conn = context.connection as Connection | undefined;
  if (!conn) throw new EffectError(`${capsule.id}: native handler needs context.connection`);
  return conn;
}

// Probe: does a row with the natural key exist, and therefore did the insert land.
class PostgresRowExists implements NativeHandler {
  async probe(capsule: Capsule, context: Record<string, unknown>): Promise<Outcome> {
    const conn = connection(capsule, context);
    const table = ident(context.table, `${capsule.id}.table`);
    const col = ident(context.key_column, `${capsule.id}.key_column`);
    const ph = placeholder(context);
    const result = await conn.query(
      `SELECT 1 FROM ${table} WHERE ${col} = ${ph} LIMIT 1`, [context.key_value]);
    const landed = (result.rows?.length ?? 0) > 0;
    return {
      status: landed ? "landed" : "not_landed",
      capsuleId: capsule.id,
      evidence: { table, key_column: col },
    };
  }

  compensate(capsule: Capsule): CompensationResult {
    throw new EffectError(`${capsule.id}: postgres_row_exists is a probe, not a compensation`);
  }
}

// Compensation: delete the row addressed by its natural key.
class PostgresDeleteByKey implements NativeHandler {
  probe(capsule: Capsule): Outcome {
    throw new EffectError(`${capsule.id}: postgres_delete_by_key is a compensation, not a probe`);
  }

  async compensate(
    capsule: Capsule, context: Record<string, unknown>): Promise<CompensationResult> {
    const conn = connection(capsule, context);
    const table = ident(context.table, `${capsule.id}.table`);
    const col = ident(context.key_column, `${capsule.id}.key_column`);
    const ph = placeholder(context);
    const result = await conn.query(
      `DELETE FROM ${table} WHERE ${col} = ${ph}`, [context.key_value]);
    const deleted = result.rowCount ?? 0;
    return {
      status: deleted ? "compensated" : "no_compensation",
      capsuleId: capsule.id,
      evidence: { deleted },
    };
  }
}

registerNative("postgres_row_exists", new PostgresRowExists());
registerNative("postgres_delete_by_key", new PostgresDeleteByKey());
