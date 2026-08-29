from __future__ import annotations

import re
import unittest
from pathlib import Path

import effectkit

ROOT = Path(__file__).resolve().parents[2]
PKG_ROOT = ROOT / "python"


def pyproject_version() -> str:
    text = (PKG_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no version in pyproject.toml"
    return match.group(1)


def changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^##\s*([0-9]+\.[0-9]+\.[0-9]+)", text, re.MULTILINE)
    assert match, "no version heading in CHANGELOG.md"
    return match.group(1)


class TestReleaseReadiness(unittest.TestCase):
    def test_version_synced_in_three_places(self):
        self.assertEqual(effectkit.__version__, pyproject_version(), "pyproject vs __version__")
        self.assertEqual(effectkit.__version__, changelog_version(), "CHANGELOG vs __version__")

    def test_corpus_mirror_in_sync(self):
        src = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "capsules").glob("*.yaml")}
        mirror_dir = PKG_ROOT / "src" / "effectkit" / "_corpus"
        mirror = {p.name: p.read_text(encoding="utf-8") for p in mirror_dir.glob("*.yaml")}
        self.assertEqual(src, mirror, "run python scripts/sync_corpus.py")


if __name__ == "__main__":
    unittest.main()
