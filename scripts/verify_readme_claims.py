"""Recompute the numbers the README states and fail if any has drifted.

Every count effectkit puts in front of a reader is derived from a committed artifact, so
CI can catch a number that stopped being true. This script is stdlib-only on purpose, so
it runs with no model stack and no third-party packages.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def capsule_ids() -> list[str]:
    ids = []
    for path in sorted((ROOT / "capsules").glob("*.yaml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^id:\s*(\S+)", line)
            if match:
                ids.append(match.group(1))
                break
    return sorted(ids)


def main() -> int:
    ids = capsule_ids()
    n = len(ids)
    problems = []

    fresh = json.loads((ROOT / "reports" / "freshness.json").read_text(encoding="utf-8"))
    fresh_ids = sorted(fresh["capsules"])
    if fresh_ids != ids:
        problems.append(f"freshness.json ids {fresh_ids} do not match corpus ids {ids}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"{n} capsules" not in readme:
        problems.append(f"README.md does not state '{n} capsules'")
    for capsule_id in ids:
        if capsule_id not in readme:
            problems.append(f"README.md does not mention capsule '{capsule_id}'")

    if problems:
        for problem in problems:
            print("claim mismatch:", problem, flush=True)
        return 1
    print(f"claims verified: {n} capsules, ids match freshness.json and README", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
