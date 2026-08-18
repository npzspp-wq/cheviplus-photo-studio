"""Refined virtual acrylic-table placement for Cheviplus Photo Studio.

Fixes observed in real branch testing:
- products were too small;
- the bottom bounding-box pixel was treated as the support point;
- reflections looked like a second full product.

The patch uses a robust lower support band from the alpha mask, larger catalog
scale, and a short rapidly fading reflection that starts exactly at the support
line of the imaginary acrylic table.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import app
import cheviplus_plexiglass as plexi

APP_VERSION = "5.15"
APP_BUILD = "2026.08.18.02"


def _support_row(product: Image.Image) -> int:
    """Return a robust visual support row instead of the single lowest pixel."""
    alpha = np.asarray(product.getchannel("A"), dtype=np.uint8)
    solid = alpha >= 96
    row_counts = solid.sum(axis=1)
    if row_counts.max(initial=0) <= 0:
        return max(0, product.height - 1)

    # Ignore isolated hairs/antialias pixels. A support row must contain a
    # meaningful horizontal footprint of the object.
    threshold = max(3, int(product.width * 0.025))
    rows = np.flatnonzero(row_counts >= threshold)
    if len(rows) == 0:
        return max(0, product.height - 1)

    # Use the 96th percentile so a protruding corner cannot make the whole
    # product appear to float above the table.
    idx = min(len(rows) - 1, int(round((len(rows) - 1) * 0.96)))
    return int(rows[idx])


def _scale_for_table(product: Image.Image, cw: int, ch: int):
    """Catalog-friendly scale: the product is dominant but leaves reflection room."""
    aspect = product.width / max(1, product.height)
    if aspect >= 3.0:
        max_w, max_h = cw * 0.90, ch * 0.34
        contact = ch * 0.67
    elif aspect <= 0.48:
        max_w, max_h = cw * 0.50, ch * 0.58
        contact = ch * 0.70
    elif aspect >= 1.65:
        max_w, max_h = cw * 0.78, ch * 0.48
        contact = ch * 0.68
    else:
        # Caps, pumps, lamps, control units and most normal catalog items.
        max_w, max_h = cw * 0.70, ch * 0.56
        contact = ch * 0.69

    ratio = min(max_w / max(1, product.width), max_h / max(1, product.height))
    size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    return product.resize(size, Image.Resampling.LANCZOS), int(contact)


def rebuild_product_for_table(source, options, table_mode=False):
    # Reuse the existing cutout and sharpening logic first.
    product, x, y = _ORIGINAL_REBUILD(source, options, table_mode=False)
    if not table_mode:
        return product, x, y

    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    product, contact_y = _scale_for_table(product, cw, ch)
    support = _support_row(product)

    x = (cw - product.width) // 2
    y = contact_y - support

    # Keep the object clear of both frame edges while preserving support contact.
    top_margin = int(ch * 0.07)
    if y < top_margin:
        y = top_margin
    if x < int(cw * 0.035):
        x = int(cw * 0.035)
    if x + product.width > int(cw * 0.965):
        x = int(cw * 0.965) - product.width
    return product, x, y


def short_reflection_layer(product, canvas_size, x, y, intensity):
    """Acrylic reflection: short, attached to support, and rapidly fading."""
    w, h = canvas_size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    support = _support_row(product)

    # Reflect the visible part above the support row, not empty transparent rows.
    visible = product.crop((0, 0, product.width, min(product.height, support + 1)))
    reflection = visible.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # 35-45% of product height is enough to read as acrylic, not a duplicate.
    target_h = max(8, int(product.height * 0.40))
    reflection = reflection.resize((product.width, target_h), Image.Resampling.LANCZOS)

    alpha = np.asarray(reflection.getchannel("A"), dtype=np.float32)
    fade = np.linspace(0.48, 0.0, target_h, dtype=np.float32)[:, None]
    strength = 0.38 + max(15, min(75, int(intensity))) / 210.0
    alpha = np.clip(alpha * fade * strength, 0, 255).astype(np.uint8)
    reflection.putalpha(
        Image.fromarray(alpha, "L").filter(
            ImageFilter.GaussianBlur(radius=max(0.8, h / 900))
        )
    )

    contact_y = y + support
    paste_y = min(h - 1, contact_y + 1)
    if paste_y < h:
        reflection = reflection.crop((0, 0, reflection.width, min(reflection.height, h - paste_y)))
        layer.alpha_composite(reflection, (x, paste_y))
    return layer


def compose_table_scene_refined(source, options, intensity):
    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    bg_path = options["background_path"]
    base = app.fit_cover(Image.open(bg_path).convert("RGB"), (cw, ch)).convert("RGBA")
    product, x, y = rebuild_product_for_table(source, options, table_mode=True)
    support = _support_row(product)

    # Reflection first, then a very short contact shadow, then the product.
    base = Image.alpha_composite(base, short_reflection_layer(product, (cw, ch), x, y, intensity))

    if options.get("shadow", True):
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        cx = x + product.width // 2
        cy = y + support + max(2, int(ch * 0.004))
        sw = max(24, int(product.width * 0.55))
        sh = max(8, int(product.height * 0.035))
        draw.ellipse((cx - sw // 2, cy - sh // 2, cx + sw // 2, cy + sh // 2), fill=(0, 0, 0, 42))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(8, int(sh * 1.7))))
        base = Image.alpha_composite(base, shadow)

    base.alpha_composite(product, (x, y))
    plexi._add_logo(base, options)
    return base


_ORIGINAL_REBUILD = plexi._rebuild_product_cutout
plexi._rebuild_product_cutout = rebuild_product_for_table
plexi._reflection_layer = short_reflection_layer
plexi._compose_table_scene = compose_table_scene_refined
plexi.APP_VERSION = APP_VERSION
plexi.APP_BUILD = APP_BUILD
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
