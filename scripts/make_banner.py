#!/usr/bin/env python3
"""Render the repo's card-style brand assets.

assets/banner-light.png and assets/banner-dark.png head the README, and
assets/social_preview.png (1280x640) is what GitHub shows when the repo link is shared,
uploaded once under Settings > Social preview. All three speak the family card language:
big lowercase repo name, accent bar, tagline, GitHub URL, and a terminal-card motif
replaying the demo's verdict. The dark satsawat.ai circuit background is deliberately
not used here; that background belongs to the personal surfaces (site OG, LinkedIn),
while the repos stay on the flat light card. Needs Pillow:

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


def chip(d, x, y, w, h, big, small, color, big_f, small_f):
    rounded(d, (x, y, x + w, y + h), 12, None, color, 3)
    bw = d.textlength(big, font=big_f)
    sw = d.textlength(small, font=small_f)
    d.text((x + (w - bw) / 2, y + 14), big, font=big_f, fill=color)
    d.text((x + (w - sw) / 2, y + 52), small, font=small_f, fill="#6e7781")


def render_social() -> Image.Image:
    W2, H2 = 1280, 640
    bg, fg, muted = "#fafafa", "#1f2328", "#6e7781"
    card_bg, card_edge, term_bg = "#f6f8fa", "#d0d7de", "#22272e"
    green, red, amber = "#3fb950", "#f85149", "#e8a112"
    blue, purple = "#2a78d6", ACCENT

    img = Image.new("RGB", (W2, H2), bg)
    d = ImageDraw.Draw(img)

    d.text((70, 56), "did-it-land", font=name_font(64), fill=fg)
    d.rectangle([74, 148, 74 + 96, 148 + 8], fill=ACCENT)
    d.text((70, 190), "Did the side-effect land,", font=name_font(40), fill=fg)
    d.text((70, 240), "and how do you undo it?", font=name_font(40), fill=purple)
    sub = name_font(26)
    d.text((70, 314), "Per-vendor probes and compensations for durable", font=sub, fill=fg)
    d.text((70, 348), "workflows, shipped as data. No API keys.", font=sub, fill=fg)

    big_f, small_f = name_font(30), name_font(18)
    chip(d, 70, 428, 180, 88, "4 capsules", "sourced, tested", blue, big_f, small_f)
    chip(d, 266, 428, 180, 88, "no keys", "runs offline", green, big_f, small_f)
    chip(d, 462, 428, 180, 88, "Py + TS", "one corpus", purple, big_f, small_f)

    d.text((70, 576), "github.com/netsatsawat/did-it-land", font=mono_font(20), fill=muted)

    cx0, cy0, cx1, cy1 = 790, 120, 1216, 520
    rounded(d, (cx0, cy0, cx1, cy1), 14, card_bg, card_edge, 2)
    rounded(d, (cx0 + 20, cy0 + 20, cx1 - 20, cy1 - 20), 10, term_bg, None, 0)
    mono = mono_font(20)
    lines = [
        ("$ did-it-land demo", "#7ee787"),
        ("", None),
        ("crash mid-charge", "#d6d5cd"),
        ("", None),
        ("naive retry", red),
        ("   2 charges", red),
        ("", None),
        ("reconcile()", "#a5d6ff"),
        ("   -> landed", "#a5d6ff"),
        ("   1 charge", green),
        ("unwind() -> refund", amber)]
    y = cy0 + 44
    for text, color in lines:
        if text:
            d.text((cx0 + 44, y), text, font=mono, fill=color)
        y += 31

    return img


def main() -> None:
    dest = ROOT / "assets"
    dest.mkdir(exist_ok=True)
    for dark, name in ((False, "banner-light.png"), (True, "banner-dark.png")):
        img = render(dark)
        img.save(dest / name)
        print(f"wrote assets/{name}")
    render_social().save(dest / "social_preview.png")
    print("wrote assets/social_preview.png")


if __name__ == "__main__":
    main()
