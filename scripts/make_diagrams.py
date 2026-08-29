#!/usr/bin/env python3
"""Render the README's three diagrams: architecture, workflow, sequence.

Three deliberate styles, one per job. The architecture view uses draw.io's pastel
boxes-and-arrows language and neutral words (no vendor names) to show where
side-effect reconciliation sits in an enterprise agent stack. The workflow chart uses
flat bold flowchart color with decision diamonds. The sequence diagram is classic UML:
pale yellow lifeline heads, maroon lines, solid calls and dashed returns. Every image
carries the repo signature bottom-left, the same way the social preview does.

Writes assets/{architecture,workflow,sequence}.svg and .png (2x, via headless
Chrome, same mechanism the hand-drawn tool uses).

    python3 scripts/make_diagrams.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIG = "github.com/netsatsawat/did-it-land"
SANS = "Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "Menlo, Monaco, monospace"

# draw.io pastel pairs: fill, border
BLUE = ("#dae8fc", "#6c8ebf")
PURPLE = ("#e1d5e7", "#9673a6")
YELLOW = ("#fff2cc", "#d6b656")
GREEN = ("#d5e8d4", "#82b366")
PINK = ("#f8cecc", "#b85450")

# flat workflow palette
W_TEAL, W_BLUE, W_ORANGE = "#1a9988", "#3d7dd8", "#f0a030"
W_RED, W_GREEN, W_PURPLE = "#d9534f", "#3d9a50", "#7d5ba6"

# UML sequence
UML_LINE, UML_HEAD = "#9a2b2b", "#fefece"


class SVG:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">',
            '<defs>'
            '<marker id="ab" markerWidth="10" markerHeight="8" refX="8" refY="4" '
            'orient="auto"><path d="M0,0 L9,4 L0,8 z" fill="#444"/></marker>'
            '<marker id="am" markerWidth="10" markerHeight="8" refX="8" refY="4" '
            f'orient="auto"><path d="M0,0 L9,4 L0,8 z" fill="{UML_LINE}"/></marker>'
            '<marker id="aw" markerWidth="10" markerHeight="8" refX="8" refY="4" '
            'orient="auto"><path d="M0,0 L9,4 L0,8 z" fill="#555"/></marker>'
            '</defs>',
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>']

    def raw(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, size=15, fill="#1f2328", anchor="middle", weight="normal",
             family=SANS, style=""):
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {style}>{s}</text>')

    def lines_in(self, cx, cy, rows, size=15, fill="#1f2328", weight="normal", gap=19):
        y0 = cy - gap * (len(rows) - 1) / 2 + size / 3
        for i, row in enumerate(rows):
            self.text(cx, y0 + i * gap, row, size=size, fill=fill, weight=weight)

    def box(self, cx, cy, w, h, fill, border, rows, size=15, rx=10, bold_first=False):
        self.parts.append(
            f'<rect x="{cx - w/2}" y="{cy - h/2}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{border}" stroke-width="1.6"/>')
        if bold_first and len(rows) > 1:
            self.lines_in(cx, cy - 10, rows[:1], size=size, weight="600")
            self.lines_in(cx, cy + 11, rows[1:], size=size - 2, fill="#57606a")
        else:
            self.lines_in(cx, cy, rows, size=size,
                          weight="600" if bold_first else "normal")

    def cylinder(self, cx, cy, w, h, fill, border, rows):
        ry = 12
        self.parts.append(
            f'<path d="M{cx - w/2},{cy - h/2 + ry} '
            f'a{w/2},{ry} 0 0,1 {w},0 v{h - 2*ry} a{w/2},{ry} 0 0,1 -{w},0 z" '
            f'fill="{fill}" stroke="{border}" stroke-width="1.6"/>')
        self.parts.append(
            f'<path d="M{cx - w/2},{cy - h/2 + ry} a{w/2},{ry} 0 0,0 {w},0" '
            f'fill="none" stroke="{border}" stroke-width="1.6"/>')
        self.lines_in(cx, cy + 6, rows, size=14)

    def diamond(self, cx, cy, w, h, fill, rows):
        self.parts.append(
            f'<path d="M{cx},{cy - h/2} L{cx + w/2},{cy} L{cx},{cy + h/2} '
            f'L{cx - w/2},{cy} z" fill="{fill}"/>')
        self.lines_in(cx, cy, rows, size=15, fill="#ffffff", weight="600")

    def arrow(self, x1, y1, x2, y2, label="", dashed=False, color="#444",
              marker="ab", lx=None, ly=None, lsize=13, lfill="#57606a"):
        dash = ' stroke-dasharray="6,5"' if dashed else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="1.6" marker-end="url(#{marker})"{dash}/>')
        if label:
            self.text(lx if lx is not None else (x1 + x2) / 2 + 8,
                      ly if ly is not None else (y1 + y2) / 2 - 7,
                      label, size=lsize, fill=lfill,
                      anchor="middle" if lx is None else "start")

    def path_arrow(self, points, color="#444", marker="ab", dashed=False):
        d = "M" + " L".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="6,5"' if dashed else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'marker-end="url(#{marker})"{dash}/>')

    def signature(self):
        self.text(26, self.h - 20, SIG, size=16, fill="#6e7781", anchor="start",
                  family=MONO)

    def write(self, path: Path):
        self.parts.append("</svg>")
        path.write_text("\n".join(self.parts), encoding="utf-8")


def architecture() -> SVG:
    s = SVG(1240, 820)
    cx = 560
    s.text(cx, 44, "Where side-effect reconciliation sits in an enterprise agent stack",
           size=20, fill="#57606a", weight="600")

    s.box(cx, 106, 320, 56, *BLUE, ["Business channels", "users, apps, operations"],
          bold_first=True)
    s.box(cx, 206, 320, 56, *PURPLE, ["Agent layer", "plans work, chooses actions"],
          bold_first=True)
    s.box(cx, 306, 320, 62, *YELLOW,
          ["Durable orchestration", "checkpoints, retries, recovery"], bold_first=True)
    s.box(1040, 306, 260, 62, *PURPLE,
          ["Observability & audit", "traces, action records"], bold_first=True)

    # the reconciliation band, with its two halves
    s.box(cx, 452, 640, 124, *GREEN, [""])
    s.text(cx, 412, "Side-effect reconciliation  (did-it-land)", size=17, weight="600",
           fill="#1f2328")
    s.box(cx - 150, 458, 240, 52, "#ffffff", GREEN[1],
          ["probe", "did the call land?"], bold_first=True)
    s.box(cx + 150, 458, 240, 52, "#ffffff", GREEN[1],
          ["undo", "run the compensation"], bold_first=True)
    s.text(cx, 502, "one capsule per operation: data, not code", size=13,
           fill="#57606a")

    ext = [
        (200, "Payment provider"), (440, "Object store"),
        (680, "Message service"), (920, "Relational database")]
    for x, label in ext[:3]:
        s.box(x, 650, 210, 54, *PINK, [label])
    s.cylinder(920, 650, 150, 74, *PINK, ["Relational", "database"])

    s.arrow(cx, 134, cx, 172)
    s.arrow(cx, 234, cx, 268)
    s.arrow(cx, 337, cx, 388, label="on recovery and rollback", lx=cx + 16, ly=366)
    s.arrow(722, 306, 908, 306, dashed=True, color="#999")
    # normal step calls bypass, drawn down the left margin
    s.path_arrow([(400, 306), (80, 306), (80, 650), (89, 650)], color="#999")
    s.text(96, 590, "normal step calls", size=13, fill="#8a939c", anchor="start")
    # reconciliation to the systems of record
    for x, _ in ext:
        s.arrow(cx + (x - cx) * 0.35, 514, x, 618)
    # the verdict returns to the orchestrator
    s.path_arrow([(760, 414), (760, 340)], color="#555", marker="aw", dashed=True)
    s.text(774, 380, "landed / not landed / unknown", size=13, fill="#57606a",
           anchor="start")

    s.signature()
    return s


def workflow() -> SVG:
    s = SVG(1240, 940)
    cx = 620
    s.text(cx, 42, "The crash-recovery workflow", size=20, fill="#57606a",
           weight="600")

    s.box(cx, 88, 150, 44, W_TEAL, W_TEAL, ["Start"], rx=22)
    s.lines_in(cx, 88, ["Start"], fill="#ffffff", weight="600")
    s.box(cx, 168, 340, 52, W_BLUE, W_BLUE, [""], rx=14)
    s.lines_in(cx, 168, ["A workflow step calls", "an external service"],
               fill="#ffffff", weight="600", gap=20)
    s.box(cx, 258, 340, 52, W_RED, W_RED, [""], rx=14)
    s.lines_in(cx, 258, ["The process crashes", "before the checkpoint"],
               fill="#ffffff", weight="600", gap=20)
    s.box(cx, 348, 340, 52, W_PURPLE, W_PURPLE, [""], rx=14)
    s.lines_in(cx, 348, ["Recovery probes with the", "operation's capsule"],
               fill="#ffffff", weight="600", gap=20)

    s.diamond(cx, 468, 220, 110, W_ORANGE, ["Did it", "land?"])

    s.box(280, 468, 280, 52, W_GREEN, W_GREEN, [""], rx=14)
    s.lines_in(280, 468, ["Skip the retry,", "reuse the result"], fill="#ffffff",
               weight="600", gap=20)
    s.box(960, 468, 280, 52, W_BLUE, W_BLUE, [""], rx=14)
    s.lines_in(960, 468, ["Run the step,", "same idempotency key"], fill="#ffffff",
               weight="600", gap=20)
    s.box(cx, 590, 280, 52, W_ORANGE, W_ORANGE, [""], rx=14)
    s.lines_in(cx, 590, ["Wait, then", "probe again"], fill="#ffffff", weight="600",
               gap=20)

    s.box(cx, 700, 340, 52, "#455a64", "#455a64", [""], rx=14)
    s.lines_in(cx, 700, ["Checkpoint written:", "exactly one effect"], fill="#ffffff",
               weight="600", gap=20)

    s.diamond(cx, 810, 210, 100, W_PURPLE, ["Roll", "back?"])
    s.box(960, 810, 280, 52, W_RED, W_RED, [""], rx=14)
    s.lines_in(960, 810, ["Unwind runs the", "compensation"], fill="#ffffff",
               weight="600", gap=20)
    s.box(280, 810, 150, 44, W_TEAL, W_TEAL, [""], rx=22)
    s.lines_in(280, 810, ["Done"], fill="#ffffff", weight="600")

    s.arrow(cx, 110, cx, 138)
    s.arrow(cx, 194, cx, 228)
    s.arrow(cx, 284, cx, 318)
    s.arrow(cx, 374, cx, 409)
    s.arrow(510, 468, 424, 468, label="yes", lx=452, ly=456)
    s.arrow(730, 468, 816, 468, label="no", lx=766, ly=456)
    s.arrow(cx, 523, cx, 560, label="unknown", lx=cx + 14, ly=546)
    # the re-probe loop back up the left side of the spine
    s.path_arrow([(480, 590), (170, 590), (170, 348), (446, 348)], color="#999")
    # both resolved branches meet at the checkpoint
    s.path_arrow([(280, 494), (280, 700), (446, 700)])
    s.path_arrow([(960, 494), (960, 700), (794, 700)])
    s.arrow(cx, 726, cx, 756)
    s.arrow(725, 810, 816, 810, label="yes", lx=756, ly=798)
    s.arrow(515, 810, 359, 810, label="no", lx=436, ly=798)
    s.path_arrow([(960, 836), (960, 900), (280, 900), (280, 836)])

    s.signature()
    return s


def sequence() -> SVG:
    s = SVG(1080, 660)
    # frame and its sd tab
    s.raw('<rect x="14" y="14" width="1052" height="590" fill="none" '
          f'stroke="{UML_LINE}" stroke-width="1.2"/>')
    s.raw(f'<path d="M14,14 h330 v26 l-12,12 H14 z" fill="{UML_HEAD}" '
          f'stroke="{UML_LINE}" stroke-width="1.2"/>')
    s.text(24, 40, "sd Did It Land ( orderId ) : outcome", size=15, weight="600",
           anchor="start", fill="#1f2328")

    heads = [
        (200, "engine : DurableWorkflow"), (470, "guard : ReconcileGuard"),
        (700, "capsules : EffectCorpus"), (930, "service : ExternalAPI")]
    for x, label in heads:
        s.raw(f'<rect x="{x - 105}" y="70" width="210" height="36" fill="{UML_HEAD}" '
              f'stroke="{UML_LINE}" stroke-width="1.4"/>')
        s.text(x, 93, label, size=14, weight="600",
               style='text-decoration="underline"')
        s.raw(f'<line x1="{x}" y1="106" x2="{x}" y2="560" stroke="{UML_LINE}" '
              'stroke-width="1" stroke-dasharray="6,5"/>')

    def act(x, y1, y2):
        s.raw(f'<rect x="{x - 6}" y="{y1}" width="12" height="{y2 - y1}" '
              f'fill="#ffffff" stroke="{UML_LINE}" stroke-width="1.2"/>')

    act(200, 150, 520)
    act(470, 162, 490)
    act(700, 216, 262)
    act(930, 318, 368)

    def call(x1, x2, y, label):
        s.arrow(x1 + 6, y, x2 - 6, y, color=UML_LINE, marker="am")
        s.text((x1 + x2) / 2, y - 8, label, size=14, fill="#1f2328")

    def ret(x1, x2, y, label):
        s.arrow(x1 - 6, y, x2 + 6, y, color=UML_LINE, marker="am", dashed=True)
        s.text((x1 + x2) / 2, y - 8, label, size=14, fill="#57606a")

    call(200, 470, 162, "reconcile ( orderId )")
    call(470, 700, 216, "lookup ( operation )")
    ret(700, 470, 258, "capsule")
    call(470, 930, 318, "probe ( orderId )")
    ret(930, 470, 364, "current state")
    ret(470, 200, 452, "landed | not_landed | unknown")

    s.signature()
    return s


def rasterise(svg_path: Path, png_path: Path, w: int, h: int, scale: int = 2) -> bool:
    chrome = next(
        (p for p in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("chromium") or "",
            shutil.which("google-chrome") or "") if p and os.path.exists(p)),
        None)
    if not chrome:
        print("no Chrome found; wrote SVG only", file=sys.stderr)
        return False
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={w},{h}",
         f"--force-device-scale-factor={scale}",
         f"--screenshot={png_path}", f"file://{svg_path}"],
        capture_output=True)
    return png_path.exists()


def main() -> None:
    dest = ROOT / "assets"
    dest.mkdir(exist_ok=True)
    for name, build in (
            ("architecture", architecture), ("workflow", workflow),
            ("sequence", sequence)):
        svg = build()
        svg_path = dest / f"{name}.svg"
        svg.write(svg_path)
        ok = rasterise(svg_path, dest / f"{name}.png", svg.w, svg.h)
        print(f"wrote assets/{name}.svg" + (f" + .png ({svg.w}x{svg.h} @2x)" if ok else ""))


if __name__ == "__main__":
    main()
