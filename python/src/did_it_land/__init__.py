"""did-it-land: know whether a side-effect landed, and how to reverse it.

A corpus of per-vendor effect capsules plus a thin runtime. reconcile answers "did it
land" after an ambiguous crash; unwind runs the inverse. See docs/CAPSULE-SCHEMA.md.
"""

from __future__ import annotations

from . import native
from .capsule import (
    SCHEMA_VERSION,
    Capsule,
    CapsuleError,
    capsule_from_dict,
    load_capsule)
from .reconcile import (
    CompensationResult,
    EffectError,
    Outcome,
    reconcile,
    unwind)
from .registry import Registry, bundled, load_dir
from .transport import HttpxTransport, Response, Transport, TransportError

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "Capsule",
    "CapsuleError",
    "CompensationResult",
    "EffectError",
    "HttpxTransport",
    "Outcome",
    "Registry",
    "Response",
    "Transport",
    "TransportError",
    "bundled",
    "capsule_from_dict",
    "load_capsule",
    "load_dir",
    "native",
    "reconcile",
    "unwind",
    "__version__"]
