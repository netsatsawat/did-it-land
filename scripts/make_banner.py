#!/usr/bin/env python3
"""Render assets/banner-light.png and assets/banner-dark.png.

Matches the family banner language: big lowercase repo name, accent bar, a two-line
tagline, the GitHub URL bottom-left, and a product motif on the right. The motif here
is a small terminal card replaying the demo's verdict. Needs Pillow:

    python3 scripts/make_banner.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1600, 400

ACCENT = "#8250df"


def font(path_size_pairs):
    for path, size in path_size_pairs:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def name_font(size):
    return font([
        ("/System/Library/Fonts/HelveticaNeue.ttc", size),
        ("/System/Library/Fonts/Helvetica.ttc", size)])


def mono_font(size):
    return font([
        ("/System/Library/Fonts/Menlo.ttc", size),
        ("/System/Library/Fonts/Monaco.ttf", size)])


def rounded(draw, box, radius, fill, outline, width):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render(dark: bool) -> Image.Image:
    if dark:
        bg, fg, muted = "#0d1117", "#e6edf3", "#8b949e"
        card_bg, card_edge = "#161b22", "#30363d"
        term_bg = "#0a0d12"
    else:
        bg, fg, muted = "#ffffff", "#1f2328", "#6e7781"
        card_bg, card_edge = "#f6f8fa", "#d0d7de"
        term_bg = "#22272e"
    green, red, amber = "#3fb950", "#f85149", "#e8a112"

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # left: name, accent bar, tagline, url
    d.text((80, 62), "did-it-land", font=name_font(74), fill=fg)
    d.rectangle([84, 168, 84 + 100, 168 + 8], fill=ACCENT)
    tagline = name_font(33)
    d.text((80, 206), "The worker died mid-charge. Did it land,", font=tagline, fill=fg)
    d.text((80, 250), "and how do you undo it?", font=tagline, fill=fg)
    d.text((80, 330), "github.com/netsatsawat", font=mono_font(20), fill=muted)

    # right: terminal card replaying the verdict
    cx0, cy0, cx1, cy1 = 1010, 44, 1552, 356
    rounded(d, (cx0, cy0, cx1, cy1), 14, card_bg, card_edge, 2)
    rounded(d, (cx0 + 22, cy0 + 22, cx1 - 22, cy1 - 22), 10, term_bg, None, 0)
    mono = mono_font(21)
    lines = [
        ("$ did-it-land demo", "#7ee787"),
        ("", None),
        ("naive retry     2 charges", red),
        ("", None),
        ("reconcile()  -> landed", "#a5d6ff"),
        ("with capsule    1 charge", green),
        ("unwind()     -> refunded", amber)]
    y = cy0 + 48
    for text, color in lines:
        if text:
            d.text((cx0 + 48, y), text, font=mono, fill=color)
        y += 34

    return img


def main() -> None:
    dest = ROOT / "assets"
    dest.mkdir(exist_ok=True)
    for dark, name in ((False, "banner-light.png"), (True, "banner-dark.png")):
        img = render(dark)
        img.save(dest / name)
        print(f"wrote assets/{name}")


if __name__ == "__main__":
    main()
