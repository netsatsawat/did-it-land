"""Generate the TypeScript corpus module from the canonical capsules/.

The npm package cannot reach files outside its own directory, and shipping the corpus as
a generated .ts module keeps the TypeScript runtime free of any parser dependency and safe
under any bundler. Run this after editing a capsule. Pass --check in CI to fail on drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "capsules"
OUT = ROOT / "typescript" / "src" / "corpus.generated.ts"
HEADER = "// Generated from capsules/ by scripts/build_ts_corpus.py. Do not edit by hand.\n"


def render() -> str:
    caps = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(SRC.glob("*.yaml"))]
    body = json.dumps(caps, indent=2, ensure_ascii=False)
    return f"{HEADER}export const CORPUS: unknown[] = {body};\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("drift: typescript/src/corpus.generated.ts is stale")
            print("run: python scripts/build_ts_corpus.py")
            return 1
        print("ts corpus in sync")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
