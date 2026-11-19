"""Regenerate icon/pdf_toolbox.ico from icon/pdf_icon.png.

Usage: python -B packaging_support/make_icon.py

The source PNG is 1536x1024 with transparent margins, so the artwork is cropped to
its visible bounds, centred on a transparent square, and each ICO size is resampled
separately with LANCZOS (sharper than letting the ICO writer downscale one image).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "icon" / "pdf_icon.png"
TARGET = ROOT / "icon" / "pdf_toolbox.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
ALPHA_THRESHOLD = 16  # ignore near-invisible fringe pixels when finding the artwork bounds
MARGIN_RATIO = 0.03  # transparent padding around the artwork, per side


def square_artwork(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    mask = image.getchannel("A").point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox() or (0, 0, image.width, image.height)
    artwork = image.crop(bbox)
    side = round(max(artwork.size) * (1 + 2 * MARGIN_RATIO))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(artwork, ((side - artwork.width) // 2, (side - artwork.height) // 2))
    return canvas


def main() -> None:
    square = square_artwork(Image.open(SOURCE))
    frames = [square.resize((size, size), Image.Resampling.LANCZOS) for size in SIZES]
    largest = frames[-1]
    largest.save(
        TARGET,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=frames[:-1],
    )
    print(f"Wrote {TARGET} ({', '.join(str(size) for size in SIZES)})")


if __name__ == "__main__":
    main()
