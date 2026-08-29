#!/usr/bin/env python3
"""Render the README's three diagrams: architecture, workflow, sequence.

Three deliberate styles, one per job. The architecture view uses draw.io's pastel
boxes-and-arrows language and neutral words (no vendor names) to show where
side-effect reconciliation sits in an enterprise agent stack. The workflow chart uses
flat bold flowchart color with decision diamonds. The sequence diagram is classic UML:
pale yellow lifeline heads, maroon lines, solid calls and dashed returns. Every image
carries the repo signature bottom-left, the same way the social preview does.

Readability rules learned the hard way: base type stays 16px or larger because GitHub
scales the image to its column, strokes stay 2.4px so the auto-scaled arrowheads read,
elbow arrows get rounded corners, and a line that must cross another hops over it.

Writes assets/{architecture,workflow,sequence}.svg and .png (2x, via headless Chrome).

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
STROKE = 2.4

# draw.io pastel pairs: fill, border
BLUE = ("#dae8fc", "#6c8ebf")
PURPLE = ("#e1d5e7", "#9673a6")
YELLOW = ("#fff2cc", "#d6b656")
GREEN = ("#d5e8d4", "#82b366")
PINK = ("#f8cecc", "#b85450")

# flat workflow palette
W_TEAL, W_BLUE, W_ORANGE = "#1a9988", "#3d7dd8", "#f0a030"
W_RED, W_GREEN, W_PURPLE = "#d9534f", "#3d9a50", "#7d5ba6"
W_SLATE = "#455a64"

# UML sequence
UML_LINE, UML_HEAD = "#9a2b2b", "#fefece"


def elbow_d(points, r=14):
    """Orthogonal path with rounded corners through the given points."""
    d = [f"M{points[0][0]},{points[0][1]}"]
    for i in range(1, len(points) - 1):
        (px, py), (cx, cy), (nx, ny) = points[i - 1], points[i], points[i + 1]
        ix = 0 if cx == px else (1 if cx > px else -1)
        iy = 0 if cy == py else (1 if cy > py else -1)
        ox = 0 if nx == cx else (1 if nx > cx else -1)
        oy = 0 if ny == cy else (1 if ny > cy else -1)
        d.append(f"L{cx - ix * r},{cy - iy * r}")
        d.append(f"Q{cx},{cy} {cx + ox * r},{cy + oy * r}")
    d.append(f"L{points[-1][0]},{points[-1][1]}")
    return " ".join(d)


class SVG:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">',
            '<defs>'
            '<marker id="ab" markerWidth="9" markerHeight="7" refX="7.5" refY="3.5" '
            'orient="auto"><path d="M0,0 L8.5,3.5 L0,7 z" fill="#444"/></marker>'
            '<marker id="am" markerWidth="9" markerHeight="7" refX="7.5" refY="3.5" '
            f'orient="auto"><path d="M0,0 L8.5,3.5 L0,7 z" fill="{UML_LINE}"/></marker>'
            '<marker id="ag" markerWidth="9" markerHeight="7" refX="7.5" refY="3.5" '
            'orient="auto"><path d="M0,0 L8.5,3.5 L0,7 z" fill="#8a939c"/></marker>'
            '</defs>',
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>']

    def raw(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, size=17, fill="#1f2328", anchor="middle", weight="normal",
             family=SANS, style=""):
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {style}>{s}</text>')

    def lines_in(self, cx, cy, rows, size=17, fill="#1f2328", weight="normal", gap=23):
        y0 = cy - gap * (len(rows) - 1) / 2 + size / 3
        for i, row in enumerate(rows):
            self.text(cx, y0 + i * gap, row, size=size, fill=fill, weight=weight)

    def box(self, cx, cy, w, h, fill, border, rows, size=17, rx=12, bold_first=False):
        self.parts.append(
            f'<rect x="{cx - w/2}" y="{cy - h/2}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{border}" stroke-width="{STROKE}"/>')
        if bold_first and len(rows) > 1:
            self.lines_in(cx, cy - 12, rows[:1], size=size + 1, weight="600")
            self.lines_in(cx, cy + 13, rows[1:], size=size - 1, fill="#57606a")
        elif rows and rows[0]:
            self.lines_in(cx, cy, rows, size=size,
                          weight="600" if bold_first else "normal")

    def flat(self, cx, cy, w, h, color, rows, rx=14, size=18):
        self.parts.append(
            f'<rect x="{cx - w/2}" y="{cy - h/2}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{color}"/>')
        self.lines_in(cx, cy, rows, size=size, fill="#ffffff", weight="600", gap=24)

    def cylinder(self, cx, cy, w, h, fill, border, rows):
        ry = 14
        self.parts.append(
            f'<path d="M{cx - w/2},{cy - h/2 + ry} '
            f'a{w/2},{ry} 0 0,1 {w},0 v{h - 2*ry} a{w/2},{ry} 0 0,1 -{w},0 z" '
            f'fill="{fill}" stroke="{border}" stroke-width="{STROKE}"/>')
        self.parts.append(
            f'<path d="M{cx - w/2},{cy - h/2 + ry} a{w/2},{ry} 0 0,0 {w},0" '
            f'fill="none" stroke="{border}" stroke-width="{STROKE}"/>')
        self.lines_in(cx, cy + 8, rows, size=16, gap=21)

    def diamond(self, cx, cy, w, h, fill, rows):
        self.parts.append(
            f'<path d="M{cx},{cy - h/2} L{cx + w/2},{cy} L{cx},{cy + h/2} '
            f'L{cx - w/2},{cy} z" fill="{fill}"/>')
        self.lines_in(cx, cy, rows, size=18, fill="#ffffff", weight="600", gap=24)

    def arrow(self, x1, y1, x2, y2, label="", dashed=False, color="#444",
              marker="ab", lx=None, ly=None, lsize=16, lfill="#57606a"):
        dash = ' stroke-dasharray="7,6"' if dashed else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{STROKE}" marker-end="url(#{marker})"{dash}/>')
        if label:
            self.text(lx if lx is not None else (x1 + x2) / 2 + 9,
                      ly if ly is not None else (y1 + y2) / 2 - 9,
                      label, size=lsize, fill=lfill,
                      anchor="middle" if lx is None else "start")

    def path_arrow(self, points, color="#444", marker="ab", dashed=False, d=None):
        d = d or elbow_d(points)
        dash = ' stroke-dasharray="7,6"' if dashed else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{STROKE}" '
            f'marker-end="url(#{marker})"{dash}/>')

    def signature(self):
        self.text(28, self.h - 24, SIG, size=18, fill="#6e7781", anchor="start",
                  family=MONO)

    def write(self, path: Path):
        self.parts.append("</svg>")
        path.write_text("\n".join(self.parts), encoding="utf-8")


def architecture() -> SVG:
    s = SVG(1280, 940)
    cx = 580
    s.text(cx, 52, "Where side-effect reconciliation sits in an enterprise agent stack",
           size=23, fill="#57606a", weight="600")

    s.box(cx, 128, 380, 70, *BLUE, ["Business channels", "users, apps, operations"],
          bold_first=True)
    s.box(cx, 240, 380, 70, *PURPLE, ["Agent layer", "plans work, chooses actions"],
          bold_first=True)
    s.box(cx, 352, 380, 74, *YELLOW,
          ["Durable orchestration", "checkpoints, retries, recovery"], bold_first=True)
    s.box(1080, 352, 330, 74, *PURPLE,
          ["Observability & audit", "traces, action records"], bold_first=True)

    # the reconciliation band, with its two halves
    s.box(cx, 540, 700, 150, *GREEN, [""])
    s.text(cx, 490, "Side-effect reconciliation  (did-it-land)", size=20,
           weight="600", fill="#1f2328")
    s.box(cx - 165, 542, 280, 66, "#ffffff", GREEN[1],
          ["probe", "did the call land?"], bold_first=True)
    s.box(cx + 165, 542, 280, 66, "#ffffff", GREEN[1],
          ["undo", "run the compensation"], bold_first=True)
    s.text(cx, 598, "one capsule per operation: data, not code", size=15,
           fill="#57606a")

    for x, label in (
            (210, "Payment provider"), (490, "Object store"),
            (770, "Message service")):
        s.box(x, 790, 250, 66, *PINK, [label], size=17)
    s.cylinder(1040, 790, 180, 92, *PINK, ["Relational", "database"])

    s.arrow(cx, 163, cx, 201)
    s.arrow(cx, 275, cx, 311)
    s.arrow(cx, 389, cx, 460, label="on recovery and rollback", lx=cx + 18, ly=428)
    s.arrow(772, 352, 911, 352, dashed=True, color="#8a939c", marker="ag")
    # reconciliation reaches the systems of record through an orthogonal bus:
    # one trunk down, one distribution bar, one clean drop per system
    s.raw(f'<line x1="{cx}" y1="615" x2="{cx}" y2="700" stroke="#444" '
          f'stroke-width="{STROKE}"/>')
    s.raw(f'<line x1="150" y1="700" x2="1040" y2="700" stroke="#444" '
          f'stroke-width="{STROKE}"/>')
    s.text(cx + 16, 662, "probe and compensate", size=15, fill="#57606a",
           anchor="start")
    for x in (210, 490, 770):
        s.arrow(x, 700, x, 751)
    s.arrow(1040, 700, 1040, 738)
    # normal step calls join the same bus from the left margin
    s.path_arrow([(390, 352), (66, 352), (66, 700), (142, 700)], color="#8a939c",
                 marker="ag")
    s.text(84, 676, "normal step calls", size=15, fill="#8a939c", anchor="start")
    # the verdict returns to the orchestrator
    s.path_arrow([(830, 465), (830, 392)], color="#555", dashed=True)
    s.text(846, 432, "landed / not landed / unknown", size=15, fill="#57606a",
           anchor="start")

    s.signature()
    return s


def workflow() -> SVG:
    s = SVG(1280, 1080)
    cx = 640
    s.text(cx, 50, "The crash-recovery workflow", size=23, fill="#57606a",
           weight="600")

    s.flat(cx, 106, 180, 54, W_TEAL, ["Start"], rx=27, size=19)
    s.flat(cx, 196, 410, 66, W_BLUE, ["A workflow step calls", "an external service"])
    s.flat(cx, 296, 410, 66, W_RED, ["The process crashes", "before the checkpoint"])
    s.flat(cx, 396, 410, 66, W_PURPLE,
           ["Recovery probes with the", "operation's capsule"])

    s.diamond(cx, 532, 260, 136, W_ORANGE, ["Did it", "land?"])

    s.flat(280, 532, 320, 66, W_GREEN, ["Skip the retry,", "reuse the result"])
    s.flat(1000, 532, 320, 66, W_BLUE, ["Run the step,", "same idempotency key"])
    s.flat(cx, 668, 310, 66, W_ORANGE, ["Wait, then", "probe again"])

    s.flat(cx, 800, 400, 66, W_SLATE, ["Checkpoint written:", "exactly one effect"])

    s.diamond(cx, 922, 240, 116, W_PURPLE, ["Roll", "back?"])
    s.flat(1000, 922, 320, 66, W_RED, ["Unwind runs the", "compensation"])
    s.flat(280, 922, 180, 54, W_TEAL, ["Done"], rx=27, size=19)

    s.arrow(cx, 133, cx, 159)
    s.arrow(cx, 229, cx, 259)
    s.arrow(cx, 329, cx, 359)
    s.arrow(cx, 429, cx, 460)
    s.arrow(510, 532, 444, 532, label="yes", lx=460, ly=516)
    s.arrow(770, 532, 836, 532, label="no", lx=792, ly=516)
    s.arrow(cx, 600, cx, 631, label="unknown", lx=cx + 16, ly=620)
    # the re-probe loop: left out of the wait box, up the margin, back into the
    # probe box, hopping over the yes branch's merge line at x=280
    s.path_arrow(
        None, color="#8a939c", marker="ag",
        d="M480,668 L293,668 A13,13 0 0 0 267,668 L172,668 Q158,668 158,654 "
          "L158,410 Q158,396 172,396 L431,396")
    # both resolved branches meet at the checkpoint
    s.path_arrow([(280, 565), (280, 800), (436, 800)])
    s.path_arrow([(1000, 565), (1000, 800), (844, 800)])
    s.arrow(cx, 833, cx, 860)
    s.arrow(765, 922, 836, 922, label="yes", lx=788, ly=906)
    s.arrow(515, 922, 374, 922, label="no", lx=436, ly=906)
    s.path_arrow([(1000, 955), (1000, 1020), (280, 1020), (280, 953)])

    s.signature()
    return s


def sequence() -> SVG:
    s = SVG(1200, 740)
    s.raw(f'<rect x="16" y="16" width="1168" height="650" fill="none" '
          f'stroke="{UML_LINE}" stroke-width="1.6"/>')
    s.raw(f'<path d="M16,16 h390 v32 l-14,14 H16 z" fill="{UML_HEAD}" '
          f'stroke="{UML_LINE}" stroke-width="1.6"/>')
    s.text(28, 48, "sd Did It Land ( orderId ) : outcome", size=18, weight="600",
           anchor="start", fill="#1f2328")

    heads = [
        (220, "engine : DurableWorkflow"), (520, "guard : ReconcileGuard"),
        (780, "capsules : EffectCorpus"), (1030, "service : ExternalAPI")]
    for x, label in heads:
        s.raw(f'<rect x="{x - 118}" y="88" width="236" height="42" fill="{UML_HEAD}" '
              f'stroke="{UML_LINE}" stroke-width="1.8"/>')
        s.text(x, 115, label, size=16, weight="600",
               style='text-decoration="underline"')
        s.raw(f'<line x1="{x}" y1="130" x2="{x}" y2="618" stroke="{UML_LINE}" '
              'stroke-width="1.2" stroke-dasharray="7,6"/>')

    def act(x, y1, y2):
        s.raw(f'<rect x="{x - 7}" y="{y1}" width="14" height="{y2 - y1}" '
              f'fill="#ffffff" stroke="{UML_LINE}" stroke-width="1.5"/>')

    act(220, 180, 590)
    act(520, 194, 556)
    act(780, 256, 310)
    act(1030, 376, 436)

    def call(x1, x2, y, label):
        s.arrow(x1 + 7, y, x2 - 7, y, color=UML_LINE, marker="am")
        s.text((x1 + x2) / 2, y - 10, label, size=17, fill="#1f2328")

    def ret(x1, x2, y, label):
        s.arrow(x1 - 7, y, x2 + 7, y, color=UML_LINE, marker="am", dashed=True)
        s.text((x1 + x2) / 2, y - 10, label, size=17, fill="#57606a")

    call(220, 520, 194, "reconcile ( orderId )")
    call(520, 780, 256, "lookup ( operation )")
    ret(780, 520, 306, "capsule")
    call(520, 1030, 376, "probe ( orderId )")
    ret(1030, 520, 432, "current state")
    ret(520, 220, 520, "landed | not_landed | unknown")

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
