// reconcile answers "did it land"; unwind runs the inverse. Both are deterministic given
// the capsule and the context.

import type { Capsule, HttpRequest, Result, Rule } from "./capsule.ts";

export interface Response {
  statusCode: number;
  body?: unknown;
}

export interface Transport {
  send(req: HttpRequest): Response | Promise<Response>;
}

export interface Outcome {
  status: Result;
  capsuleId: string;
  evidence?: Record<string, unknown>;
}

export interface CompensationResult {
  status: string;
  capsuleId: string;
}

export class EffectError extends Error {}

/** The service could not be reached or did not answer in time. A transport that
 * throws this tells reconcile and unwind the question went unanswered, which is an
 * unknown outcome, not a no. */
export class TransportError extends Error {}

export interface NativeHandler {
  probe(capsule: Capsule, context: Record<string, unknown>): Outcome | Promise<Outcome>;
  compensate(
    capsule: Capsule,
    context: Record<string, unknown>,
  ): CompensationResult | Promise<CompensationResult>;
}

const HANDLERS = new Map<string, NativeHandler>();

export function registerNative(id: string, handler: NativeHandler): void {
  HANDLERS.set(id, handler);
}

function getHandler(id: string | undefined): NativeHandler {
  const handler = id === undefined ? undefined : HANDLERS.get(id);
  if (!handler) {
    const known = [...HANDLERS.keys()].sort().join(", ") || "none";
    throw new EffectError(`no native handler registered for '${id}' (registered: ${known})`);
  }
  return handler;
}

function bind(template: string, context: Record<string, unknown>, capsuleId: string): string {
  return template.replace(/\{([^}]+)\}/g, (_match, name: string) => {
    if (!(name in context)) {
      throw new EffectError(`${capsuleId}: context is missing '${name}', needed by '${template}'`);
    }
    return String(context[name]);
  });
}

function bindRequest(
  req: HttpRequest,
  context: Record<string, unknown>,
  capsuleId: string,
): HttpRequest {
  const query: Record<string, string> = {};
  for (const [k, v] of Object.entries(req.query)) query[k] = bind(v, context, capsuleId);
  const headers: Record<string, string> = {};
  for (const [k, v] of Object.entries(req.headers)) headers[k] = bind(v, context, capsuleId);
  return { method: req.method, path: bind(req.path, context, capsuleId), query, headers };
}

function navigate(body: unknown, path: string): [boolean, unknown] {
  let cur: unknown = body;
  for (const part of path.split(".")) {
    if (cur !== null && typeof cur === "object" && !Array.isArray(cur) && part in cur) {
      cur = (cur as Record<string, unknown>)[part];
    } else if (Array.isArray(cur) && /^\d+$/.test(part) && Number(part) < cur.length) {
      cur = cur[Number(part)];
    } else {
      return [false, undefined];
    }
  }
  return [true, cur];
}

function fieldOf(item: unknown, dotted: string): unknown {
  let cur: unknown = item;
  for (const part of dotted.split(".")) {
    if (cur === null || typeof cur !== "object" || !(part in (cur as object))) return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function filtered(
  value: unknown,
  where: Record<string, unknown> | undefined,
  context: Record<string, unknown>,
  capsuleId: string,
): unknown {
  if (!where || !Array.isArray(value)) return value;
  const bound = Object.fromEntries(
    Object.entries(where).map(([k, v]) => [
      k,
      typeof v === "string" ? bind(v, context, capsuleId) : v,
    ]),
  );
  return value.filter(
    (item) =>
      item !== null &&
      typeof item === "object" &&
      Object.entries(bound).every(([k, v]) => fieldOf(item, k) === v),
  );
}

function match(
  rule: Rule,
  resp: Response,
  context: Record<string, unknown>,
  capsuleId: string,
): [boolean, Record<string, unknown>] {
  const evidence: Record<string, unknown> = {};
  if (rule.statusIn !== undefined && !rule.statusIn.includes(resp.statusCode)) {
    return [false, evidence];
  }
  if (rule.jsonPath !== undefined) {
    const [found, raw] = navigate(resp.body, rule.jsonPath);
    const value = filtered(raw, rule.where, context, capsuleId);
    if (rule.exists !== undefined && found !== rule.exists) return [false, evidence];
    if (rule.countGte !== undefined) {
      if (!found || !Array.isArray(value) || value.length < rule.countGte) {
        return [false, evidence];
      }
      evidence.matched = value.length;
      const ids = value
        .filter((x) => x !== null && typeof x === "object" && "id" in (x as object))
        .map((x) => (x as Record<string, unknown>).id);
      if (ids.length) evidence.ids = ids;
    }
    if (rule.hasEquals && (!found || value !== rule.equals)) return [false, evidence];
  }
  return [true, evidence];
}

export async function reconcile(
  capsule: Capsule,
  context: Record<string, unknown>,
  transport?: Transport,
): Promise<Outcome> {
  const probe = capsule.probe;
  if (probe.kind === "native") {
    return getHandler(probe.handler).probe(capsule, context);
  }
  if (!transport) throw new EffectError(`${capsule.id}: an http probe needs a transport`);
  const outcome = await httpProbe(capsule, probe.request!, probe.interpret, context, transport);
  if (outcome.status === "not_landed" && probe.confirm) {
    const confirmed = await httpProbe(
      capsule, probe.confirm.request, probe.confirm.interpret, context, transport);
    return {
      status: confirmed.status,
      capsuleId: capsule.id,
      evidence: { ...confirmed.evidence, confirmed: true },
    };
  }
  return outcome;
}

async function httpProbe(
  capsule: Capsule,
  request: HttpRequest,
  interpret: Rule[],
  context: Record<string, unknown>,
  transport: Transport,
): Promise<Outcome> {
  let resp: Response;
  try {
    resp = await transport.send(bindRequest(request, context, capsule.id));
  } catch (err) {
    if (err instanceof TransportError) {
      return { status: "unknown", capsuleId: capsule.id, evidence: { transport_error: String(err) } };
    }
    throw err;
  }
  for (const rule of interpret) {
    const [ok, evidence] = match(rule, resp, context, capsule.id);
    if (ok) {
      evidence.status_code = resp.statusCode;
      return { status: rule.result, capsuleId: capsule.id, evidence };
    }
  }
  return { status: "unknown", capsuleId: capsule.id, evidence: { status_code: resp.statusCode } };
}

export async function unwind(
  capsule: Capsule,
  context: Record<string, unknown>,
  transport?: Transport,
): Promise<CompensationResult> {
  const comp = capsule.compensation;
  if (capsule.reversibility.cls === "irreversible") {
    return { status: "irreversible", capsuleId: capsule.id };
  }
  if (!comp || comp.kind === "none") {
    return { status: "no_compensation", capsuleId: capsule.id };
  }
  if (comp.kind === "native") {
    return getHandler(comp.handler).compensate(capsule, context);
  }
  if (!transport) throw new EffectError(`${capsule.id}: an http compensation needs a transport`);
  let resp: Response;
  try {
    resp = await transport.send(bindRequest(comp.request!, context, capsule.id));
  } catch (err) {
    if (err instanceof TransportError) {
      return { status: "unknown", capsuleId: capsule.id };
    }
    throw err;
  }
  const ok = resp.statusCode >= 200 && resp.statusCode < 300;
  return { status: ok ? "compensated" : "failed", capsuleId: capsule.id };
}
