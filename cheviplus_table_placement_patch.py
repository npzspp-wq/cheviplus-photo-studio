"""Refined virtual acrylic-table placement for Cheviplus Photo Studio.

Adds automatic support-based placement plus an optional manual vertical offset.
The normal "Масштаб товара" control now also applies to the acrylic-table mode.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import app
import cheviplus_plexiglass as plexi

APP_VERSION = "5.15"
APP_BUILD = "2026.08.18.04"

_ORIGINAL_REBUILD = plexi._rebuild_product_cutout
_ORIGINAL_BUILD = app.App._build
_ORIGINAL_CURRENT_OPTIONS = app.App.current_options
_ORIGINAL_SETTINGS_PAYLOAD = app.App.settings_payload
_ORIGINAL_LOAD_SETTINGS = app.App.load_settings
_ORIGINAL_RESET_SETTINGS = app.App.reset_settings


def _support_row(product: Image.Image) -> int:
    alpha = np.asarray(product.getchannel("A"), dtype=np.uint8)
    solid = alpha >= 96
    row_counts = solid.sum(axis=1)
    if row_counts.max(initial=0) <= 0:
        return max(0, product.height - 1)
    threshold = max(3, int(product.width * 0.025))
    rows = np.flatnonzero(row_counts >= threshold)
    if len(rows) == 0:
        return max(0, product.height - 1)
    idx = min(len(rows) - 1, int(round((len(rows) - 1) * 0.96)))
    return int(rows[idx])


def _scale_for_table(product: Image.Image, cw: int, ch: int, product_fill: float = 0.86):
    """Size for table while respecting the user's existing product-scale slider.

    86% is the historical/default scale. Values below/above it shrink/enlarge
    the table product proportionally, while safety caps prevent clipping.
    """
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
        max_w, max_h = cw * 0.70, ch * 0.56
        contact = ch * 0.69

    fill = max(0.60, min(0.94, float(product_fill)))
    scale_factor = fill / 0.86
    target_w = min(cw * 0.94, max_w * scale_factor)
    target_h = min(ch * 0.68, max_h * scale_factor)
    ratio = min(target_w / max(1, product.width), target_h / max(1, product.height))
    size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    return product.resize(size, Image.Resampling.LANCZOS), int(contact)


def rebuild_product_for_table(source, options, table_mode=False):
    product, x, y = _ORIGINAL_REBUILD(source, options, table_mode=False)
    if not table_mode:
        return product, x, y

    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    product_fill = float(options.get("product_fill", 0.86))
    product, contact_y = _scale_for_table(product, cw, ch, product_fill)
    support = _support_row(product)

    x = (cw - product.width) // 2
    y = contact_y - support

    if options.get("table_manual_position", False):
        offset_pct = max(-25, min(25, int(options.get("table_vertical_offset", 0))))
        y += int(ch * offset_pct / 100.0)

    y = max(-int(product.height * 0.08), min(y, ch - int(product.height * 0.20)))
    x = max(int(cw * 0.035), min(x, int(cw * 0.965) - product.width))
    return product, x, y


def short_reflection_layer(product, canvas_size, x, y, intensity):
    w, h = canvas_size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    support = _support_row(product)
    visible = product.crop((0, 0, product.width, min(product.height, support + 1)))
    reflection = visible.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    target_h = max(8, int(product.height * 0.40))
    reflection = reflection.resize((product.width, target_h), Image.Resampling.LANCZOS)

    alpha = np.asarray(reflection.getchannel("A"), dtype=np.float32)
    fade = np.linspace(0.48, 0.0, target_h, dtype=np.float32)[:, None]
    strength = 0.38 + max(15, min(75, int(intensity))) / 210.0
    alpha = np.clip(alpha * fade * strength, 0, 255).astype(np.uint8)
    reflection.putalpha(Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(radius=max(0.8, h / 900))))

    contact_y = y + support
    paste_y = max(0, min(h - 1, contact_y + 1))
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


def _find_box(root, text):
    for widget in root.winfo_children():
        try:
            if isinstance(widget, ttk.LabelFrame) and widget.cget("text") == text:
                return widget
        except Exception:
            pass
        found = _find_box(widget, text)
        if found is not None:
            return found
    return None


def build_with_manual_position(self):
    _ORIGINAL_BUILD(self)
    self.table_manual_position = tk.BooleanVar(master=self, value=False)
    self.table_vertical_offset = tk.IntVar(master=self, value=0)

    effect_box = _find_box(self, "4. Эффекты")
    if effect_box is None:
        return

    ttk.Separator(effect_box, orient="horizontal").grid(row=3, column=0, columnspan=6, sticky="ew", pady=(8, 6))
    ttk.Checkbutton(effect_box, text="Ручное положение товара на столе", variable=self.table_manual_position).grid(row=4, column=0, columnspan=6, sticky="w")
    self._scale_row(effect_box, 5, "Положение вверх / вниз", self.table_vertical_offset, -25, 25, lambda v: f"{float(v):+.0f}%")
    ttk.Label(effect_box, text="− вверх   •   0 автоматически   •   + вниз. После изменения нажмите «ПРЕДПРОСМОТР».").grid(row=6, column=0, columnspan=6, sticky="w", pady=(3, 0))


def current_options_with_manual_position(self):
    options = _ORIGINAL_CURRENT_OPTIONS(self)
    manual = getattr(self, "table_manual_position", None)
    offset = getattr(self, "table_vertical_offset", None)
    options["table_manual_position"] = bool(manual.get()) if manual is not None else False
    options["table_vertical_offset"] = int(offset.get()) if offset is not None else 0
    return options


def settings_payload_with_manual_position(self):
    data = _ORIGINAL_SETTINGS_PAYLOAD(self)
    manual = getattr(self, "table_manual_position", None)
    offset = getattr(self, "table_vertical_offset", None)
    data["table_manual_position"] = bool(manual.get()) if manual is not None else False
    data["table_vertical_offset"] = int(offset.get()) if offset is not None else 0
    return data


def load_settings_with_manual_position(self):
    _ORIGINAL_LOAD_SETTINGS(self)
    if not app.SETTINGS_FILE.exists():
        return
    try:
        data = json.loads(app.SETTINGS_FILE.read_text(encoding="utf-8"))
        self.table_manual_position.set(bool(data.get("table_manual_position", False)))
        self.table_vertical_offset.set(max(-25, min(25, int(data.get("table_vertical_offset", 0)))))
    except Exception:
        pass


def reset_settings_with_manual_position(self):
    _ORIGINAL_RESET_SETTINGS(self)
    if hasattr(self, "table_manual_position"):
        self.table_manual_position.set(False)
    if hasattr(self, "table_vertical_offset"):
        self.table_vertical_offset.set(0)


plexi._rebuild_product_cutout = rebuild_product_for_table
plexi._reflection_layer = short_reflection_layer
plexi._compose_table_scene = compose_table_scene_refined
plexi.APP_VERSION = APP_VERSION
plexi.APP_BUILD = APP_BUILD

app.App._build = build_with_manual_position
app.App.current_options = current_options_with_manual_position
app.App.settings_payload = settings_payload_with_manual_position
app.App.load_settings = load_settings_with_manual_position
app.App.reset_settings = reset_settings_with_manual_position
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
