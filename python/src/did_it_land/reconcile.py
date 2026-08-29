"""The two operations at the heart of did_it_land.

reconcile answers "did this land" by running a capsule's probe. unwind runs the
inverse. Both are deterministic given the capsule and the call context. Neither asks a
model anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .capsule import Capsule, Request, UNSET
from .transport import Response, Transport, TransportError


class EffectError(RuntimeError):
    """A capsule could not be run against the given context or transport."""


@dataclass(frozen=True)
class Outcome:
    status: str
    capsule_id: str
    evidence: dict = field(default_factory=dict)

    @property
    def landed(self) -> bool:
        return self.status == "landed"

    @property
    def not_landed(self) -> bool:
        return self.status == "not_landed"

    @property
    def unknown(self) -> bool:
        return self.status == "unknown"


@dataclass(frozen=True)
class CompensationResult:
    status: str
    capsule_id: str
    evidence: dict = field(default_factory=dict)


def _bind(template: str, context: dict, capsule_id: str) -> str:
    out = template
    start = out.find("{")
    while start != -1:
        end = out.find("}", start)
        if end == -1:
            break
        name = out[start + 1:end]
        if name not in context:
            raise EffectError(
                f"{capsule_id}: context is missing '{name}', needed by '{template}'")
        out = out[:start] + str(context[name]) + out[end + 1:]
        start = out.find("{", start + len(str(context[name])))
    return out


def _bind_request(req: Request, context: dict, capsule_id: str) -> Request:
    return Request(
        method=req.method,
        path=_bind(req.path, context, capsule_id),
        query={k: _bind(v, context, capsule_id) for k, v in req.query.items()},
        headers={k: _bind(v, context, capsule_id) for k, v in req.headers.items()})


def _navigate(body: object, path: str) -> tuple[bool, object]:
    cur = body
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


def _filtered(value: object, where: dict | None) -> object:
    """Apply a rule's where clause: keep array elements whose fields equal the given values."""
    if where is None or not isinstance(value, list):
        return value
    kept = []
    for item in value:
        if isinstance(item, dict) and all(item.get(k) == v for k, v in where.items()):
            kept.append(item)
    return kept


def _match(rule, resp: Response) -> tuple[bool, dict]:
    """Decide whether a rule matches, returning any evidence worth surfacing."""
    evidence: dict = {}
    if rule.status_in is not None and resp.status_code not in rule.status_in:
        return False, evidence
    if rule.json_path is not None:
        found, value = _navigate(resp.body, rule.json_path)
        value = _filtered(value, rule.where)
        if rule.exists is not None and found != rule.exists:
            return False, evidence
        if rule.count_gte is not None:
            if not found or not isinstance(value, list) or len(value) < rule.count_gte:
                return False, evidence
            evidence["matched"] = len(value)
        if rule.equals is not UNSET and (not found or value != rule.equals):
            return False, evidence
    return True, evidence


def reconcile(
        capsule: Capsule,
        context: dict,
        transport: Transport | None = None) -> Outcome:
    """Run the capsule's probe and report landed, not_landed, or unknown."""
    probe = capsule.probe
    if probe.kind == "native":
        from . import native

        return native.get_handler(probe.handler).probe(capsule, context)
    if transport is None:
        raise EffectError(f"{capsule.id}: an http probe needs a transport")
    try:
        resp = transport.send(_bind_request(probe.request, context, capsule.id))
    except TransportError as exc:
        return Outcome("unknown", capsule.id, {"transport_error": str(exc)})
    for rule in probe.interpret:
        matched, evidence = _match(rule, resp)
        if matched:
            evidence["status_code"] = resp.status_code
            return Outcome(rule.result, capsule.id, evidence)
    return Outcome("unknown", capsule.id, {"status_code": resp.status_code})


def unwind(
        capsule: Capsule,
        context: dict,
        transport: Transport | None = None) -> CompensationResult:
    """Run the capsule's compensation, or report why it cannot be reversed."""
    comp = capsule.compensation
    if capsule.reversibility.cls == "irreversible":
        return CompensationResult("irreversible", capsule.id)
    if comp is None or comp.kind == "none":
        return CompensationResult("no_compensation", capsule.id)
    if comp.kind == "native":
        from . import native

        return native.get_handler(comp.handler).compensate(capsule, context)
    if transport is None:
        raise EffectError(f"{capsule.id}: an http compensation needs a transport")
    try:
        resp = transport.send(_bind_request(comp.request, context, capsule.id))
    except TransportError as exc:
        # The undo may or may not have landed. Its request carries its own
        # idempotency key, so retrying unwind with the same context stays safe.
        return CompensationResult("unknown", capsule.id, {"transport_error": str(exc)})
    status = "compensated" if resp.ok else "failed"
    return CompensationResult(status, capsule.id, {"status_code": resp.status_code})
