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

function filtered(value: unknown, where?: Record<string, unknown>): unknown {
  if (!where || !Array.isArray(value)) return value;
  return value.filter(
    (item) =>
      item !== null &&
      typeof item === "object" &&
      Object.entries(where).every(([k, v]) => (item as Record<string, unknown>)[k] === v),
  );
}

function match(rule: Rule, resp: Response): [boolean, Record<string, unknown>] {
  const evidence: Record<string, unknown> = {};
  if (rule.statusIn !== undefined && !rule.statusIn.includes(resp.statusCode)) {
    return [false, evidence];
  }
  if (rule.jsonPath !== undefined) {
    const [found, raw] = navigate(resp.body, rule.jsonPath);
    const value = filtered(raw, rule.where);
    if (rule.exists !== undefined && found !== rule.exists) return [false, evidence];
    if (rule.countGte !== undefined) {
      if (!found || !Array.isArray(value) || value.length < rule.countGte) {
        return [false, evidence];
      }
      evidence.matched = value.length;
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
  const resp = await transport.send(bindRequest(probe.request!, context, capsule.id));
  for (const rule of probe.interpret) {
    const [ok, evidence] = match(rule, resp);
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
  const resp = await transport.send(bindRequest(comp.request!, context, capsule.id));
  const ok = resp.statusCode >= 200 && resp.statusCode < 300;
  return { status: ok ? "compensated" : "failed", capsuleId: capsule.id };
}
