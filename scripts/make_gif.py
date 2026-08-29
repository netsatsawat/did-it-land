#!/usr/bin/env python3
"""Render assets/demo.gif: a terminal-style replay of the real demo run.

Captures a live `did-it-land demo` and replays it line by line, in the same style the
sibling repos use. Needs Pillow, which is not a package dependency:

    python3 scripts/make_gif.py
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

BG = "#1a1a19"
FG = "#d6d5cd"
PROMPT = "#0ca30c"
MUTED = "#898781"
GOOD = "#3fb950"
BAD = "#f85149"
AMBER = "#e8a112"
BLUE = "#79b8ff"

W, PAD, LINE_H, FONT_SIZE = 860, 22, 19, 13


def load_font():
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/System/Library/Fonts/Monaco.ttf"):
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def color_for(line):
    if line.startswith("$"):
        return PROMPT
    if "double charged" in line:
        return BAD
    if "no double charge" in line:
        return GOOD
    if "-> landed" in line:
        return BLUE
    if line.startswith("Unwind"):
        return AMBER
    if line.startswith("==="):
        return FG
    if line.startswith("Run "):
        return FG
    if line.lstrip().startswith(("attempt", "recovery")):
        return MUTED
    return FG


def frame(lines, font, height):
    img = Image.new("RGB", (W, height), BG)
    draw = ImageDraw.Draw(img)
    y = PAD
    for text, color in lines:
        draw.text((PAD, y), text, fill=color, font=font)
        y += LINE_H
    return img


def main() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "did_it_land.cli", "demo"],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT / "python" / "src"), "PATH": "/usr/bin:/bin"}).stdout
    body = [ln.rstrip() for ln in out.splitlines()]
    while body and not body[-1]:
        body.pop()

    font = load_font()
    height = PAD * 2 + LINE_H * (len(body) + 2)

    lines = [("$ did-it-land demo", PROMPT)]
    frames = [frame(lines, font, height)]
    durations = [1100]
    for ln in body:
        lines.append((ln, color_for(ln)))
        frames.append(frame(lines, font, height))
        durations.append(120 if not ln else 420)
    durations[-1] = 5000  # hold the verdict

    dest = ROOT / "assets" / "demo.gif"
    dest.parent.mkdir(exist_ok=True)
    frames[0].save(dest, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    frames[-1].save(ROOT / "assets" / "demo-last-frame.png")
    print(f"wrote {dest} ({dest.stat().st_size // 1024} KB, {len(frames)} frames)")


if __name__ == "__main__":
    sys.exit(main())
