"""Capsule data model, loader, and a stdlib validator.

The corpus is data, so the library keeps its own small validator rather than pulling
in a JSON Schema dependency. The canonical machine contract still lives in
schema/capsule.schema.json; this module enforces the same rules with clear errors and
turns a YAML document into frozen dataclasses the runtime can trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCHEMA_VERSION = "1"

# Sentinel so a rule can distinguish "equals was not given" from "equals is false".
UNSET = object()

_STRATEGIES = {"client_key", "natural_key", "none"}
_PROBE_KINDS = {"http", "native"}
_COMP_KINDS = {"http", "native", "none"}
_REV_CLASSES = {"reversible", "conditionally_reversible", "irreversible"}
_RESULTS = {"landed", "not_landed", "unknown"}
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}


class CapsuleError(ValueError):
    """A capsule file is malformed or violates the schema."""


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    result: str
    status_in: list[int] | None = None
    json_path: str | None = None
    exists: bool | None = None
    equals: object = UNSET
    count_gte: int | None = None
    where: dict | None = None


@dataclass(frozen=True)
class Confirm:
    request: Request
    interpret: list[Rule]
    notes: str | None = None


@dataclass(frozen=True)
class Probe:
    kind: str
    handler: str | None = None
    request: Request | None = None
    interpret: list[Rule] = field(default_factory=list)
    confirm: Confirm | None = None


@dataclass(frozen=True)
class Idempotency:
    strategy: str
    header: str | None = None
    keys: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class Reversibility:
    cls: str
    condition: str | None = None


@dataclass(frozen=True)
class Compensation:
    kind: str
    handler: str | None = None
    request: Request | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Capsule:
    id: str
    provider: str
    operation: str
    schema_version: str
    idempotency: Idempotency
    probe: Probe
    reversibility: Reversibility
    compensation: Compensation | None = None
    summary: str | None = None
    notes: str | None = None
    source: str | list[str] | None = None


def _no_extras(doc: dict, allowed: set[str], where: str) -> None:
    """Reject keys the schema does not know. A typo'd condition would otherwise
    become a rule with no conditions, which matches every response, and a probe
    that always answers landed is the precise wrong answer this library exists
    to prevent."""
    extras = set(doc) - allowed
    if extras:
        names = ", ".join(sorted(str(x) for x in extras))
        raise CapsuleError(f"{where}: unknown key(s) {names}")


def _require(doc: dict, key: str, where: str) -> object:
    if key not in doc:
        raise CapsuleError(f"{where}: missing required field '{key}'")
    return doc[key]


def _one_of(value: object, allowed: set[str], where: str) -> str:
    if value not in allowed:
        opts = ", ".join(sorted(allowed))
        raise CapsuleError(f"{where}: '{value}' must be one of {opts}")
    return str(value)


def _keys_list(raw: object, where: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
        raise CapsuleError(f"{where}: expected a list of strings")
    return list(raw)


def _request_from(doc: dict, where: str) -> Request:
    _no_extras(doc, {"method", "path", "query", "headers"}, where)
    method = _one_of(str(_require(doc, "method", where)).upper(), _METHODS, f"{where}.method")
    return Request(
        method=method,
        path=str(_require(doc, "path", where)),
        query={str(k): str(v) for k, v in (doc.get("query") or {}).items()},
        headers={str(k): str(v) for k, v in (doc.get("headers") or {}).items()})


def _rule_from(doc: dict, where: str) -> Rule:
    _no_extras(doc, {"when", "result"}, where)
    when = doc.get("when") or {}
    _no_extras(
        when,
        {"status_in", "json_path", "exists", "equals", "count_gte", "where"},
        f"{where}.when")
    if "status_in" in when:
        raw = when["status_in"]
        if not isinstance(raw, list) or any(not isinstance(x, int) or isinstance(x, bool) for x in raw):
            raise CapsuleError(f"{where}.when.status_in: expected a list of numbers")
    if "count_gte" in when and (
            not isinstance(when["count_gte"], int) or isinstance(when["count_gte"], bool)):
        raise CapsuleError(f"{where}.when.count_gte: expected a number")
    if "exists" in when and not isinstance(when["exists"], bool):
        raise CapsuleError(f"{where}.when.exists: expected a boolean")
    if "where" in when and not isinstance(when["where"], dict):
        raise CapsuleError(f"{where}.when.where: expected a mapping")
    return Rule(
        result=_one_of(_require(doc, "result", where), _RESULTS, f"{where}.result"),
        status_in=list(when["status_in"]) if "status_in" in when else None,
        json_path=str(when["json_path"]) if "json_path" in when else None,
        exists=bool(when["exists"]) if "exists" in when else None,
        equals=when["equals"] if "equals" in when else UNSET,
        count_gte=int(when["count_gte"]) if "count_gte" in when else None,
        where=dict(when["where"]) if "where" in when else None)


def _probe_from(doc: dict) -> Probe:
    where = "probe"
    _no_extras(doc, {"kind", "handler", "request", "interpret", "confirm"}, where)
    kind = _one_of(_require(doc, "kind", where), _PROBE_KINDS, f"{where}.kind")
    if kind == "native":
        handler = str(_require(doc, "handler", where))
        return Probe(kind=kind, handler=handler)
    request = _request_from(_require(doc, "request", where), f"{where}.request")
    raw_rules = _require(doc, "interpret", where)
    if not raw_rules:
        raise CapsuleError(f"{where}.interpret: an http probe needs at least one rule")
    rules = [_rule_from(r, f"{where}.interpret[{i}]") for i, r in enumerate(raw_rules)]
    confirm = None
    if doc.get("confirm") is not None:
        cdoc = doc["confirm"]
        cwhere = f"{where}.confirm"
        _no_extras(cdoc, {"request", "interpret", "notes"}, cwhere)
        creq = _request_from(_require(cdoc, "request", cwhere), f"{cwhere}.request")
        craw = _require(cdoc, "interpret", cwhere)
        if not craw:
            raise CapsuleError(f"{cwhere}.interpret: needs at least one rule")
        crules = [_rule_from(r, f"{cwhere}.interpret[{i}]") for i, r in enumerate(craw)]
        confirm = Confirm(request=creq, interpret=crules, notes=cdoc.get("notes"))
    return Probe(kind=kind, request=request, interpret=rules, confirm=confirm)


def _compensation_from(doc: dict | None) -> Compensation | None:
    if doc is None:
        return None
    where = "compensation"
    _no_extras(doc, {"kind", "handler", "request", "notes"}, where)
    kind = _one_of(_require(doc, "kind", where), _COMP_KINDS, f"{where}.kind")
    if kind == "none":
        return Compensation(kind=kind, notes=doc.get("notes"))
    if kind == "native":
        return Compensation(
            kind=kind, handler=str(_require(doc, "handler", where)), notes=doc.get("notes"))
    request = _request_from(_require(doc, "request", where), f"{where}.request")
    return Compensation(kind=kind, request=request, notes=doc.get("notes"))


def capsule_from_dict(doc: dict, where: str = "capsule") -> Capsule:
    """Validate a parsed capsule document and build a Capsule, or raise CapsuleError."""
    if not isinstance(doc, dict):
        raise CapsuleError(f"{where}: expected a mapping, got {type(doc).__name__}")
    _no_extras(
        doc,
        {"id", "provider", "operation", "schema_version", "summary", "idempotency",
         "probe", "reversibility", "compensation", "notes", "source"},
        where)

    idem_doc = _require(doc, "idempotency", where)
    _no_extras(idem_doc, {"strategy", "header", "keys", "notes"}, f"{where}.idempotency")
    idempotency = Idempotency(
        strategy=_one_of(
            _require(idem_doc, "strategy", f"{where}.idempotency"),
            _STRATEGIES,
            f"{where}.idempotency.strategy"),
        header=idem_doc.get("header"),
        keys=_keys_list(idem_doc.get("keys"), f"{where}.idempotency.keys"),
        notes=idem_doc.get("notes"))

    rev_doc = _require(doc, "reversibility", where)
    _no_extras(rev_doc, {"class", "condition"}, f"{where}.reversibility")
    rev_class = _one_of(
        _require(rev_doc, "class", f"{where}.reversibility"),
        _REV_CLASSES,
        f"{where}.reversibility.class")
    condition = rev_doc.get("condition")
    if rev_class == "conditionally_reversible" and not condition:
        raise CapsuleError(
            f"{where}.reversibility: a conditionally_reversible capsule must state its condition")

    version = str(_require(doc, "schema_version", where))
    if version != SCHEMA_VERSION:
        raise CapsuleError(
            f"{where}: schema_version {version} is not supported, "
            f"this runtime reads version {SCHEMA_VERSION}")

    return Capsule(
        id=str(_require(doc, "id", where)),
        provider=str(_require(doc, "provider", where)),
        operation=str(_require(doc, "operation", where)),
        schema_version=str(_require(doc, "schema_version", where)),
        idempotency=idempotency,
        probe=_probe_from(_require(doc, "probe", where)),
        reversibility=Reversibility(cls=rev_class, condition=condition),
        compensation=_compensation_from(doc.get("compensation")),
        summary=doc.get("summary"),
        notes=doc.get("notes"),
        source=doc.get("source"))


def load_capsule(path: str | Path) -> Capsule:
    """Read and validate one capsule YAML file."""
    path = Path(path)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return capsule_from_dict(doc, where=path.name)
