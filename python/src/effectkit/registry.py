"""Load a corpus of capsules and index it by id.

The bundled corpus is the copy packaged with the library under _corpus. That directory
is a mirror of the repository-root capsules/ folder, kept in sync by
scripts/sync_corpus.py and checked in CI, so the shipped wheel and the canonical source
never drift.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

from .capsule import Capsule, capsule_from_dict, load_capsule
from .reconcile import EffectError


class Registry:
    def __init__(self, capsules: list[Capsule]):
        self._by_id: dict[str, Capsule] = {}
        for cap in capsules:
            if cap.id in self._by_id:
                raise EffectError(f"duplicate capsule id '{cap.id}'")
            self._by_id[cap.id] = cap

    def get(self, capsule_id: str) -> Capsule:
        if capsule_id not in self._by_id:
            known = ", ".join(sorted(self._by_id)) or "none"
            raise EffectError(f"no capsule '{capsule_id}' (have: {known})")
        return self._by_id[capsule_id]

    def all(self) -> list[Capsule]:
        return list(self._by_id.values())

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)


def load_dir(path: str | Path) -> Registry:
    """Load every *.yaml capsule from a directory."""
    path = Path(path)
    caps = [load_capsule(p) for p in sorted(path.glob("*.yaml"))]
    if not caps:
        raise EffectError(f"no capsules found in {path}")
    return Registry(caps)


def bundled() -> Registry:
    """Load the corpus packaged with the library."""
    root = resources.files("effectkit").joinpath("_corpus")
    caps = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".yaml"):
            doc = yaml.safe_load(entry.read_text(encoding="utf-8"))
            caps.append(capsule_from_dict(doc, where=entry.name))
    if not caps:
        raise EffectError("bundled corpus is empty, run scripts/sync_corpus.py")
    return Registry(caps)
