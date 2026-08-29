"""Native handlers for capsules that speak a driver protocol rather than HTTP.

A native capsule names a handler id; this module resolves it to a small object with a
probe and a compensate method. The built-in Postgres handlers are driver-agnostic: the
caller passes a DB-API 2.0 connection in the context. Only whitelisted identifiers are
ever interpolated into SQL, and values always go through the driver's parameter binding.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from .capsule import Capsule
from .reconcile import CompensationResult, EffectError, Outcome

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER = {"qmark": "?", "format": "%s", "pyformat": "%s"}


@runtime_checkable
class NativeHandler(Protocol):
    def probe(self, capsule: Capsule, context: dict) -> Outcome:
        ...

    def compensate(self, capsule: Capsule, context: dict) -> CompensationResult:
        ...


_HANDLERS: dict[str, NativeHandler] = {}


def register(handler_id: str, handler: NativeHandler) -> None:
    _HANDLERS[handler_id] = handler


def get_handler(handler_id: str | None) -> NativeHandler:
    if handler_id not in _HANDLERS:
        known = ", ".join(sorted(_HANDLERS)) or "none"
        raise EffectError(
            f"no native handler registered for '{handler_id}' (registered: {known})")
    return _HANDLERS[handler_id]


def _ident(name: object, where: str) -> str:
    if not _IDENT.match(str(name)):
        raise EffectError(f"{where}: '{name}' is not a safe SQL identifier")
    return str(name)


def _placeholder(context: dict) -> str:
    return _PLACEHOLDER.get(str(context.get("paramstyle", "format")), "%s")


def _connection(capsule: Capsule, context: dict):
    conn = context.get("connection")
    if conn is None:
        raise EffectError(f"{capsule.id}: native handler needs context['connection']")
    return conn


class _PostgresRowExists:
    """Probe: does a row with the natural key exist and therefore did the insert land."""

    def probe(self, capsule: Capsule, context: dict) -> Outcome:
        conn = _connection(capsule, context)
        table = _ident(context["table"], f"{capsule.id}.table")
        col = _ident(context["key_column"], f"{capsule.id}.key_column")
        ph = _placeholder(context)
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE {col} = {ph} LIMIT 1", (context["key_value"],))
        landed = cur.fetchone() is not None
        return Outcome(
            "landed" if landed else "not_landed",
            capsule.id,
            {"table": table, "key_column": col})

    def compensate(self, capsule: Capsule, context: dict) -> CompensationResult:
        raise EffectError(f"{capsule.id}: postgres_row_exists is a probe, not a compensation")


class _PostgresDeleteByKey:
    """Compensation: delete the row addressed by its natural key."""

    def probe(self, capsule: Capsule, context: dict) -> Outcome:
        raise EffectError(f"{capsule.id}: postgres_delete_by_key is a compensation, not a probe")

    def compensate(self, capsule: Capsule, context: dict) -> CompensationResult:
        conn = _connection(capsule, context)
        table = _ident(context["table"], f"{capsule.id}.table")
        col = _ident(context["key_column"], f"{capsule.id}.key_column")
        ph = _placeholder(context)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table} WHERE {col} = {ph}", (context["key_value"],))
        deleted = cur.rowcount
        conn.commit()
        return CompensationResult(
            "compensated" if deleted else "no_compensation",
            capsule.id,
            {"deleted": deleted})


register("postgres_row_exists", _PostgresRowExists())
register("postgres_delete_by_key", _PostgresDeleteByKey())
