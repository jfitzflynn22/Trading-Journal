#!/usr/bin/env python
"""Draw the app icon and build Trading Journal.app/Contents/Resources/AppIcon.icns.

    .venv/bin/python bin/make-icon.py

Colours are the app's own: the dark card and edge greys from views/theme.py,
and the same green and red the calendar uses for an up and a down day. Drawn
at 4x and downsampled, which is cheaper than hand-rolling antialiasing and
gives clean edges on the rounded corners and the wicks.

Rerun after editing; then bin/build-launcher.sh to re-sign the bundle.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "Trading Journal.app"
RESOURCES = BUNDLE / "Contents" / "Resources"
ICONSET = ROOT / "build" / "AppIcon.iconset"

S = 4                      # supersample factor
SIZE = 1024                # master icon size

# macOS icon geometry: the artwork sits inside a rounded square with a margin,
# rather than filling the canvas -- that margin is what makes it line up with
# every other icon in the Dock.
MARGIN = 100
RADIUS = 185

BG_TOP = (45, 47, 49)      # --card
BG_BOTTOM = (31, 31, 31)   # page background
EDGE = (68, 71, 70)        # --edge
GREEN = (34, 197, 94)      # win / up day
RED = (239, 68, 68)        # loss / down day


def draw_master() -> Image.Image:
    w = SIZE * S
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))

    # Vertical gradient, painted into a rounded-rect mask so the corners stay
    # transparent instead of being squared off against the Dock background.
    grad = Image.new("RGBA", (w, w))
    gd = ImageDraw.Draw(grad)
    for y in range(w):
        t = y / (w - 1)
        gd.line(
            [(0, y), (w, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,),
        )

    mask = Image.new("L", (w, w), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [MARGIN * S, MARGIN * S, (SIZE - MARGIN) * S, (SIZE - MARGIN) * S],
        radius=RADIUS * S,
        fill=255,
    )
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # Hairline edge, the same one the cards and panels carry in the app.
    d.rounded_rectangle(
        [MARGIN * S, MARGIN * S, (SIZE - MARGIN) * S, (SIZE - MARGIN) * S],
        radius=RADIUS * S,
        outline=EDGE + (255,),
        width=3 * S,
    )

    # Four candles, ascending, one red among them: enough to read as trading at
    # 32px without turning into mush. Coordinates are in master (1024) space.
    #        x_centre, body_top, body_bottom, wick_top, wick_bottom, colour
    candles = [
        (330, 560, 700, 500, 760, RED),
        (450, 470, 620, 415, 680, GREEN),
        (574, 380, 540, 320, 600, GREEN),
        (694, 285, 455, 235, 515, GREEN),
    ]
    body_w, wick_w = 78, 14

    for cx, top, bottom, wtop, wbottom, colour in candles:
        d.rounded_rectangle(
            [(cx - wick_w // 2) * S, wtop * S, (cx + wick_w // 2) * S, wbottom * S],
            radius=(wick_w // 2) * S,
            fill=colour + (255,),
        )
        d.rounded_rectangle(
            [(cx - body_w // 2) * S, top * S, (cx + body_w // 2) * S, bottom * S],
            radius=14 * S,
            fill=colour + (255,),
        )

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def build_icns(master: Image.Image) -> Path:
    if ICONSET.exists():
        for f in ICONSET.iterdir():
            f.unlink()
    ICONSET.mkdir(parents=True, exist_ok=True)

    # The names are fixed by iconutil; every one of them has to be present or
    # the icon silently falls back at some size.
    for base in (16, 32, 128, 256, 512):
        master.resize((base, base), Image.LANCZOS).save(ICONSET / f"icon_{base}x{base}.png")
        master.resize((base * 2, base * 2), Image.LANCZOS).save(
            ICONSET / f"icon_{base}x{base}@2x.png"
        )

    RESOURCES.mkdir(parents=True, exist_ok=True)
    out = RESOURCES / "AppIcon.icns"
    subprocess.run(
        ["/usr/bin/iconutil", "--convert", "icns", str(ICONSET), "--output", str(out)],
        check=True,
    )
    return out


def main() -> int:
    master = draw_master()
    preview = ROOT / "build" / "icon-preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    master.save(preview)
    out = build_icns(master)
    print(f"preview: {preview}")
    print(f"icns:    {out}  ({out.stat().st_size:,} bytes)")
    print("\nNow run bin/build-launcher.sh to re-sign the bundle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
