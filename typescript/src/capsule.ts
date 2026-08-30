// The capsule data model and a validator that mirrors the Python one. The canonical
// contract is schema/capsule.schema.json; this rebuilds the same rules with clear errors.

export type Method = "GET" | "HEAD" | "POST" | "PUT" | "PATCH" | "DELETE";
export type Result = "landed" | "not_landed" | "unknown";
export type ProbeKind = "http" | "native";
export type CompKind = "http" | "native" | "none";
export type ReversibilityClass =
  | "reversible"
  | "conditionally_reversible"
  | "irreversible";
export type Strategy = "client_key" | "natural_key" | "none";

export interface HttpRequest {
  method: Method;
  path: string;
  query: Record<string, string>;
  headers: Record<string, string>;
}

export interface Rule {
  result: Result;
  statusIn?: number[];
  jsonPath?: string;
  exists?: boolean;
  hasEquals: boolean;
  equals?: unknown;
  countGte?: number;
  where?: Record<string, unknown>;
}

export interface Confirm {
  request: HttpRequest;
  interpret: Rule[];
}

export interface Probe {
  kind: ProbeKind;
  handler?: string;
  request?: HttpRequest;
  interpret: Rule[];
  confirm?: Confirm;
}

export interface Idempotency {
  strategy: Strategy;
  header?: string;
  keys: string[];
  notes?: string;
}

export interface Reversibility {
  cls: ReversibilityClass;
  condition?: string;
}

export interface Compensation {
  kind: CompKind;
  handler?: string;
  request?: HttpRequest;
  notes?: string;
}

export interface Capsule {
  id: string;
  provider: string;
  operation: string;
  schemaVersion: string;
  idempotency: Idempotency;
  probe: Probe;
  reversibility: Reversibility;
  compensation?: Compensation;
  summary?: string;
  notes?: string;
  source?: string | string[];
}

export const SCHEMA_VERSION = "1";

export class CapsuleError extends Error {}

const METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const STRATEGIES = new Set(["client_key", "natural_key", "none"]);
const PROBE_KINDS = new Set(["http", "native"]);
const COMP_KINDS = new Set(["http", "native", "none"]);
const REV_CLASSES = new Set([
  "reversible",
  "conditionally_reversible",
  "irreversible",
]);
const RESULTS = new Set(["landed", "not_landed", "unknown"]);

function rec(value: unknown, where: string, allowed?: string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CapsuleError(`${where}: expected a mapping`);
  }
  const doc = value as Record<string, unknown>;
  if (allowed) {
    // A typo'd key that silently vanished would leave a rule with no
    // conditions, and a rule with no conditions matches every response.
    const extras = Object.keys(doc).filter((k) => !allowed.includes(k));
    if (extras.length) {
      throw new CapsuleError(`${where}: unknown key(s) ${extras.sort().join(", ")}`);
    }
  }
  return doc;
}

function require_(doc: Record<string, unknown>, key: string, where: string): unknown {
  if (!(key in doc)) {
    throw new CapsuleError(`${where}: missing required field '${key}'`);
  }
  return doc[key];
}

function oneOf(value: unknown, allowed: Set<string>, where: string): string {
  if (typeof value !== "string" || !allowed.has(value)) {
    const opts = [...allowed].sort().join(", ");
    throw new CapsuleError(`${where}: '${String(value)}' must be one of ${opts}`);
  }
  return value;
}

function strMap(value: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries((value ?? {}) as Record<string, unknown>)) {
    out[k] = String(v);
  }
  return out;
}

function keysList(raw: unknown, where: string): string[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw) || raw.some((x) => typeof x !== "string")) {
    throw new CapsuleError(`${where}: expected a list of strings`);
  }
  return raw as string[];
}

function requestFrom(value: unknown, where: string): HttpRequest {
  const doc = rec(value, where, ["method", "path", "query", "headers"]);
  const method = oneOf(
    String(require_(doc, "method", where)).toUpperCase(),
    METHODS,
    `${where}.method`,
  ) as Method;
  return {
    method,
    path: String(require_(doc, "path", where)),
    query: strMap(doc.query),
    headers: strMap(doc.headers),
  };
}

function ruleFrom(value: unknown, where: string): Rule {
  const doc = rec(value, where, ["when", "result"]);
  const when = rec(doc.when ?? {}, `${where}.when`, [
    "status_in", "json_path", "exists", "equals", "count_gte", "where",
  ]);
  if ("status_in" in when) {
    const raw = when.status_in;
    if (!Array.isArray(raw) || raw.some((x) => typeof x !== "number")) {
      throw new CapsuleError(`${where}.when.status_in: expected a list of numbers`);
    }
  }
  if ("count_gte" in when && typeof when.count_gte !== "number") {
    throw new CapsuleError(`${where}.when.count_gte: expected a number`);
  }
  if ("exists" in when && typeof when.exists !== "boolean") {
    throw new CapsuleError(`${where}.when.exists: expected a boolean`);
  }
  if ("where" in when) {
    const w = when.where;
    if (typeof w !== "object" || w === null || Array.isArray(w)) {
      throw new CapsuleError(`${where}.when.where: expected a mapping`);
    }
  }
  return {
    result: oneOf(require_(doc, "result", where), RESULTS, `${where}.result`) as Result,
    statusIn: "status_in" in when ? (when.status_in as number[]) : undefined,
    jsonPath: "json_path" in when ? String(when.json_path) : undefined,
    exists: "exists" in when ? (when.exists as boolean) : undefined,
    hasEquals: "equals" in when,
    equals: "equals" in when ? when.equals : undefined,
    countGte: "count_gte" in when ? (when.count_gte as number) : undefined,
    where: "where" in when ? (when.where as Record<string, unknown>) : undefined,
  };
}

function probeFrom(value: unknown): Probe {
  const where = "probe";
  const doc = rec(value, where, ["kind", "handler", "request", "interpret", "confirm"]);
  const kind = oneOf(require_(doc, "kind", where), PROBE_KINDS, `${where}.kind`) as ProbeKind;
  if (kind === "native") {
    return { kind, handler: String(require_(doc, "handler", where)), interpret: [] };
  }
  const request = requestFrom(require_(doc, "request", where), `${where}.request`);
  const raw = require_(doc, "interpret", where) as unknown[];
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new CapsuleError(`${where}.interpret: an http probe needs at least one rule`);
  }
  const interpret = raw.map((r, i) => ruleFrom(r, `${where}.interpret[${i}]`));
  let confirm: Confirm | undefined;
  if (doc.confirm !== undefined && doc.confirm !== null) {
    const cdoc = rec(doc.confirm, `${where}.confirm`, ["request", "interpret", "notes"]);
    const creq = requestFrom(require_(cdoc, "request", `${where}.confirm`), `${where}.confirm.request`);
    const craw = require_(cdoc, "interpret", `${where}.confirm`) as unknown[];
    if (!Array.isArray(craw) || craw.length === 0) {
      throw new CapsuleError(`${where}.confirm.interpret: needs at least one rule`);
    }
    confirm = { request: creq, interpret: craw.map((r, i) => ruleFrom(r, `${where}.confirm.interpret[${i}]`)) };
  }
  return { kind, request, interpret, confirm };
}

function compensationFrom(value: unknown): Compensation | undefined {
  if (value === undefined || value === null) return undefined;
  const where = "compensation";
  const doc = rec(value, where, ["kind", "handler", "request", "notes"]);
  const kind = oneOf(require_(doc, "kind", where), COMP_KINDS, `${where}.kind`) as CompKind;
  if (kind === "none") return { kind, notes: doc.notes as string | undefined };
  if (kind === "native") {
    return {
      kind,
      handler: String(require_(doc, "handler", where)),
      notes: doc.notes as string | undefined,
    };
  }
  return {
    kind,
    request: requestFrom(require_(doc, "request", where), `${where}.request`),
    notes: doc.notes as string | undefined,
  };
}

export function capsuleFromDoc(value: unknown, where = "capsule"): Capsule {
  const doc = rec(value, where, [
    "id", "provider", "operation", "schema_version", "summary", "idempotency",
    "probe", "reversibility", "compensation", "notes", "source",
  ]);

  const idemDoc = rec(
    require_(doc, "idempotency", where), `${where}.idempotency`,
    ["strategy", "header", "keys", "notes"]);
  const idempotency: Idempotency = {
    strategy: oneOf(
      require_(idemDoc, "strategy", `${where}.idempotency`),
      STRATEGIES,
      `${where}.idempotency.strategy`,
    ) as Strategy,
    header: idemDoc.header as string | undefined,
    keys: keysList(idemDoc.keys, `${where}.idempotency.keys`),
    notes: idemDoc.notes as string | undefined,
  };

  const revDoc = rec(
    require_(doc, "reversibility", where), `${where}.reversibility`,
    ["class", "condition"]);
  const cls = oneOf(
    require_(revDoc, "class", `${where}.reversibility`),
    REV_CLASSES,
    `${where}.reversibility.class`,
  ) as ReversibilityClass;
  const condition = revDoc.condition as string | undefined;
  if (cls === "conditionally_reversible" && !condition) {
    throw new CapsuleError(
      `${where}.reversibility: a conditionally_reversible capsule must state its condition`,
    );
  }

  const version = String(require_(doc, "schema_version", where));
  if (version !== SCHEMA_VERSION) {
    throw new CapsuleError(
      `${where}: schema_version ${version} is not supported, this runtime reads version ${SCHEMA_VERSION}`,
    );
  }

  return {
    id: String(require_(doc, "id", where)),
    provider: String(require_(doc, "provider", where)),
    operation: String(require_(doc, "operation", where)),
    schemaVersion: String(require_(doc, "schema_version", where)),
    idempotency,
    probe: probeFrom(require_(doc, "probe", where)),
    reversibility: { cls, condition },
    compensation: compensationFrom(doc.compensation),
    summary: doc.summary as string | undefined,
    notes: doc.notes as string | undefined,
    source: doc.source as string | string[] | undefined,
  };
}
