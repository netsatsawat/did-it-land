"""Mirror the canonical capsules/ corpus into the Python package as _corpus/.

The repository root holds the one true corpus. The Python wheel needs its own copy as
package data, so this script mirrors it. Run it after editing a capsule. In CI, pass
--check to fail if the mirror has drifted from the source.

    python scripts/sync_corpus.py          # copy capsules/ -> python/src/did_it_land/_corpus/
    python scripts/sync_corpus.py --check   # verify they match, exit 1 on drift
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "capsules"
DST = ROOT / "python" / "src" / "did_it_land" / "_corpus"


def _read(path: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(path.glob("*.yaml"))}


def check() -> int:
    source = _read(SRC)
    mirror = _read(DST) if DST.exists() else {}
    if source == mirror:
        print(f"corpus in sync: {len(source)} capsules")
        return 0
    missing = sorted(set(source) - set(mirror))
    extra = sorted(set(mirror) - set(source))
    changed = sorted(k for k in source.keys() & mirror.keys() if source[k] != mirror[k])
    for name in missing:
        print(f"drift: {name} missing from mirror")
    for name in extra:
        print(f"drift: {name} in mirror but not source")
    for name in changed:
        print(f"drift: {name} differs")
    print("run: python scripts/sync_corpus.py")
    return 1


def sync() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for stale in DST.glob("*.yaml"):
        stale.unlink()
    source = _read(SRC)
    for name, text in source.items():
        (DST / name).write_text(text, encoding="utf-8")
    print(f"synced {len(source)} capsules to {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv[1:] else sync())
