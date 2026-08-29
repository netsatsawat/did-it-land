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

export interface Probe {
  kind: ProbeKind;
  handler?: string;
  request?: HttpRequest;
  interpret: Rule[];
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

function rec(value: unknown, where: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CapsuleError(`${where}: expected a mapping`);
  }
  return value as Record<string, unknown>;
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

function requestFrom(value: unknown, where: string): HttpRequest {
  const doc = rec(value, where);
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
  const doc = rec(value, where);
  const when = (doc.when ?? {}) as Record<string, unknown>;
  return {
    result: oneOf(require_(doc, "result", where), RESULTS, `${where}.result`) as Result,
    statusIn: "status_in" in when ? (when.status_in as number[]) : undefined,
    jsonPath: "json_path" in when ? String(when.json_path) : undefined,
    exists: "exists" in when ? Boolean(when.exists) : undefined,
    hasEquals: "equals" in when,
    equals: "equals" in when ? when.equals : undefined,
    countGte: "count_gte" in when ? Number(when.count_gte) : undefined,
    where: "where" in when ? (when.where as Record<string, unknown>) : undefined,
  };
}

function probeFrom(value: unknown): Probe {
  const where = "probe";
  const doc = rec(value, where);
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
  return { kind, request, interpret };
}

function compensationFrom(value: unknown): Compensation | undefined {
  if (value === undefined || value === null) return undefined;
  const where = "compensation";
  const doc = rec(value, where);
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
  const doc = rec(value, where);

  const idemDoc = rec(require_(doc, "idempotency", where), `${where}.idempotency`);
  const idempotency: Idempotency = {
    strategy: oneOf(
      require_(idemDoc, "strategy", `${where}.idempotency`),
      STRATEGIES,
      `${where}.idempotency.strategy`,
    ) as Strategy,
    header: idemDoc.header as string | undefined,
    keys: (idemDoc.keys as string[] | undefined) ?? [],
    notes: idemDoc.notes as string | undefined,
  };

  const revDoc = rec(require_(doc, "reversibility", where), `${where}.reversibility`);
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
