#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate PWA icons from the main logo.
Run this script once to create the required icon sizes.
"""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow is required. Install with: pip install Pillow")
    exit(1)

STATIC_DIR = Path(__file__).parent.parent / "kuasarr" / "static"
LOGO_PATH = STATIC_DIR / "logo.png"


def generate_icons():
    if not LOGO_PATH.exists():
        print(f"Logo not found at {LOGO_PATH}")
        return

    img = Image.open(LOGO_PATH)

    # Convert to RGBA if necessary
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Generate 192x192 icon
    icon_192 = img.copy()
    icon_192.thumbnail((192, 192), Image.Resampling.LANCZOS)
    # Create a new 192x192 image and paste centered
    final_192 = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
    offset = ((192 - icon_192.width) // 2, (192 - icon_192.height) // 2)
    final_192.paste(icon_192, offset, icon_192)
    final_192.save(STATIC_DIR / "logo-192.png", "PNG")
    print(f"Created: {STATIC_DIR / 'logo-192.png'}")

    # Generate maskable icon (512x512 with padding for safe zone)
    # Maskable icons need ~10% padding on each side (safe zone is 80% of icon)
    maskable_size = 512
    safe_zone = int(maskable_size * 0.8)
    padding = (maskable_size - safe_zone) // 2

    icon_maskable = img.copy()
    icon_maskable.thumbnail((safe_zone, safe_zone), Image.Resampling.LANCZOS)

    # Create maskable icon with background color
    final_maskable = Image.new("RGBA", (maskable_size, maskable_size), (24, 26, 27, 255))  # #181a1b
    offset = (
        padding + (safe_zone - icon_maskable.width) // 2,
        padding + (safe_zone - icon_maskable.height) // 2
    )
    final_maskable.paste(icon_maskable, offset, icon_maskable)
    final_maskable.save(STATIC_DIR / "logo-maskable.png", "PNG")
    print(f"Created: {STATIC_DIR / 'logo-maskable.png'}")

    print("PWA icons generated successfully!")


if __name__ == "__main__":
    generate_icons()
