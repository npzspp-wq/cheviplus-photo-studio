"""Seamless full-surface plexiglass effect for Cheviplus Photo Studio.

Version 5.15. The reflection is built from the actual segmented product cutout,
not from differences between the final image and the branded backdrop. This makes
the acrylic reflection visible and stable even when the backdrop contains logos.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

import app
import cheviplus_ai_quality as aq

APP_VERSION = "5.15"
APP_BUILD = "2026.08.17.05"
DEFAULT_INTENSITY = 45
MIN_ENABLED_INTENSITY = 15

_ORIGINAL_COMPOSE = app.compose_image
_ORIGINAL_BUILD = app.App._build
_ORIGINAL_CURRENT_OPTIONS = app.App.current_options
_ORIGINAL_SETTINGS_PAYLOAD = app.App.settings_payload
_ORIGINAL_LOAD_SETTINGS = app.App.load_settings
_ORIGINAL_RESET_SETTINGS = app.App.reset_settings


def _rebuild_product_cutout(source, options):
    """Recreate the exact positioned product used by the processing pipeline."""
    original = Image.open(source)
    processing_mode = options.get("processing_mode", aq.MODE_FAST)
    previous_mode = getattr(aq._LOCAL, "mode", aq.MODE_FAST)
    previous_key = getattr(aq._LOCAL, "cache_key", None)
    aq._LOCAL.mode = processing_mode if processing_mode in aq.MODES else aq.MODE_FAST
    aq._LOCAL.cache_key = aq._cache_key_from_source(source, aq._LOCAL.mode)
    try:
        product, auto_info = aq.remove_background(
            original,
            cleanup=options.get("cleanup", 82),
            edge_expand=options.get("edge_expand", 1),
            auto_settings=options.get("auto_settings", False),
            prevent_background_showthrough=options.get("prevent_background_showthrough", True),
            strict_logo_cleanup=options.get("strict_logo_cleanup", False),
        )
    finally:
        aq._LOCAL.mode = previous_mode
        aq._LOCAL.cache_key = previous_key

    product = app.trim_transparency(product)
    product_fill = float(options.get("product_fill", 0.86))
    if options.get("auto_settings"):
        product_fill = auto_info.get("fill", product_fill)
    if options.get("straighten"):
        product = app.trim_transparency(app.auto_straighten(product))
    if options.get("remove_product_logo"):
        product = app.remove_product_logo_region(product, options.get("logo_remove_strength", 55))

    sharpness = max(0, min(100, int(options.get("sharpness", 45))))
    rgb = product.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.02)
    if sharpness:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.65 + sharpness / 180, percent=45 + int(sharpness * 1.25), threshold=2))
    product = Image.merge("RGBA", (*rgb.split(), product.getchannel("A")))

    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    max_w = int(cw * product_fill)
    max_h = int(ch * product_fill)
    ratio = min(max_w / max(1, product.width), max_h / max(1, product.height))
    product = product.resize((max(1, int(product.width * ratio)), max(1, int(product.height * ratio))), Image.Resampling.LANCZOS)
    x = (cw - product.width) // 2
    y = int(ch * 0.54 - product.height / 2)
    y = max(20, min(y, ch - product.height - 20))
    return product, x, y


def _add_floor_gloss(base: Image.Image, intensity: int):
    """Add broad acrylic highlights over the whole lower surface, with no border."""
    w, h = base.size
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheen)
    alpha = int(18 + intensity * 0.42)
    band = max(28, int(w * 0.03))
    for center in (int(w * 0.14), int(w * 0.78)):
        draw.polygon([
            (center - band * 3, int(h * 0.36)),
            (center - band, int(h * 0.36)),
            (center + band * 3, h),
            (center + band, h),
        ], fill=(255, 255, 255, alpha))
    sheen = sheen.filter(ImageFilter.GaussianBlur(radius=max(20, int(w * 0.02))))
    return Image.alpha_composite(base, sheen)


def apply_plexiglass_from_product(image: Image.Image, product: Image.Image, x: int, y: int, intensity: int = DEFAULT_INTENSITY) -> Image.Image:
    """Apply approved visible acrylic-floor reflection under the actual product."""
    intensity = max(0, min(75, int(intensity)))
    if intensity <= 0:
        return image

    base = image.convert("RGBA")
    w, h = base.size
    reflection = product.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    rw, rh = reflection.size

    # Preserve most product height like the approved reference, but softly stretch vertically.
    reflected_h = max(1, int(rh * 0.92))
    reflection = reflection.resize((rw, reflected_h), Image.Resampling.LANCZOS)

    alpha = np.asarray(reflection.getchannel("A"), dtype=np.float32)
    fade = np.linspace(0.72, 0.02, reflected_h, dtype=np.float32)[:, None]
    strength = 0.38 + intensity / 125.0
    alpha = np.clip(alpha * fade * strength, 0, 255).astype(np.uint8)
    reflection.putalpha(
        Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(radius=max(0.7, h / 1100)))
    )

    # The mirror begins immediately at the product's contact line.
    paste_y = min(h - 1, y + product.height - max(2, int(product.height * 0.045)))
    available = h - paste_y
    if available > 0:
        reflection = reflection.crop((0, 0, rw, min(reflected_h, available)))
        base.alpha_composite(reflection, (x, paste_y))

    # Soft contact darkening makes the product sit on the acrylic while keeping its existing shadow.
    contact = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(contact)
    cx = x + product.width // 2
    cw = max(30, int(product.width * 0.72))
    ch = max(10, int(product.height * 0.055))
    cy = min(h - 1, y + product.height)
    cd.ellipse((cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2), fill=(0, 0, 0, int(18 + intensity * 0.22)))
    contact = contact.filter(ImageFilter.GaussianBlur(radius=max(10, int(ch * 1.8))))
    base = Image.alpha_composite(base, contact)

    base = _add_floor_gloss(base, intensity)

    # A subtle lower-half brightness gives continuous transparent acrylic with no visible edge.
    lift = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    arr = np.zeros((h, w), dtype=np.uint8)
    start = int(h * 0.46)
    if start < h:
        arr[start:, :] = np.linspace(0, min(20, 5 + intensity // 4), h - start, dtype=np.uint8)[:, None]
    lift.putalpha(Image.fromarray(arr, mode="L").filter(ImageFilter.GaussianBlur(radius=max(8, h // 150))))
    return Image.alpha_composite(base, lift)


def compose_with_plexiglass(source, *args, plexiglass_enabled=False, plexiglass_intensity=DEFAULT_INTENSITY, **kwargs):
    # Keep a copy because the wrapped AI compose consumes processing_mode itself.
    reflection_options = dict(kwargs)
    if args:
        names = [
            "background_path", "logo_path", "canvas_width", "canvas_height", "product_fill", "add_logo",
            "shadow", "shadow_strength", "cleanup", "edge_expand", "sharpness", "straighten", "auto_settings",
            "prevent_background_showthrough", "strict_logo_cleanup", "remove_product_logo", "logo_remove_strength"
        ]
        for name, value in zip(names, args[1:]):
            reflection_options.setdefault(name, value)
    result = _ORIGINAL_COMPOSE(source, *args, **kwargs)
    if not plexiglass_enabled:
        return result

    intensity = int(plexiglass_intensity)
    if intensity < MIN_ENABLED_INTENSITY:
        intensity = DEFAULT_INTENSITY
    try:
        product, x, y = _rebuild_product_cutout(source, reflection_options)
        return apply_plexiglass_from_product(result, product, x, y, intensity)
    except Exception:
        # Never break normal photo processing if the optional effect fails.
        return result


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


def build_with_plexiglass(self):
    _ORIGINAL_BUILD(self)
    self.plexiglass_enabled = tk.BooleanVar(master=self, value=False)
    self.plexiglass_intensity_var = tk.IntVar(master=self, value=DEFAULT_INTENSITY)

    source_box = _find_box(self, "4. Добавить фотографии")
    if source_box is None:
        return
    parent = source_box.master
    effect_box = ttk.LabelFrame(parent, text="4. Эффекты", padding=12)
    effect_box.pack(fill="x", pady=(10, 0), before=source_box)
    try:
        source_box.configure(text="5. Добавить фотографии")
    except Exception:
        pass

    def on_toggle():
        if self.plexiglass_enabled.get() and self.plexiglass_intensity_var.get() < MIN_ENABLED_INTENSITY:
            self.plexiglass_intensity_var.set(DEFAULT_INTENSITY)
        if self.plexiglass_enabled.get():
            self.status.set("Эффект оргстекла включён — отражение детали + глянец поверхности")

    ttk.Checkbutton(
        effect_box,
        text="Эффект оргстекла — отражение детали на глянцевой поверхности",
        variable=self.plexiglass_enabled,
        command=on_toggle,
    ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 5))
    self._scale_row(
        effect_box, 1, "Видимость отражения", self.plexiglass_intensity_var,
        MIN_ENABLED_INTENSITY, 75, lambda v: f"{float(v):.0f}%"
    )
    ttk.Label(
        effect_box,
        text="Эталон: отражается сама деталь, есть мягкий глянец; фирменный фон виден, края стекла нет.",
    ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(3, 0))


def current_options_with_plexiglass(self):
    options = _ORIGINAL_CURRENT_OPTIONS(self)
    enabled_var = getattr(self, "plexiglass_enabled", None)
    intensity_var = getattr(self, "plexiglass_intensity_var", None)
    enabled = bool(enabled_var.get()) if enabled_var is not None else False
    intensity = int(intensity_var.get()) if intensity_var is not None else DEFAULT_INTENSITY
    if enabled and intensity < MIN_ENABLED_INTENSITY:
        intensity = DEFAULT_INTENSITY
    options["plexiglass_enabled"] = enabled
    options["plexiglass_intensity"] = intensity
    return options


def settings_payload_with_plexiglass(self):
    data = _ORIGINAL_SETTINGS_PAYLOAD(self)
    enabled_var = getattr(self, "plexiglass_enabled", None)
    intensity_var = getattr(self, "plexiglass_intensity_var", None)
    enabled = bool(enabled_var.get()) if enabled_var is not None else False
    intensity = int(intensity_var.get()) if intensity_var is not None else DEFAULT_INTENSITY
    if enabled and intensity < MIN_ENABLED_INTENSITY:
        intensity = DEFAULT_INTENSITY
    data["plexiglass_enabled"] = enabled
    data["plexiglass_intensity"] = intensity
    return data


def load_settings_with_plexiglass(self):
    _ORIGINAL_LOAD_SETTINGS(self)
    if not app.SETTINGS_FILE.exists():
        return
    try:
        import json
        data = json.loads(app.SETTINGS_FILE.read_text(encoding="utf-8"))
        enabled = bool(data.get("plexiglass_enabled", False))
        intensity = int(data.get("plexiglass_intensity", DEFAULT_INTENSITY))
        if enabled and intensity < MIN_ENABLED_INTENSITY:
            intensity = DEFAULT_INTENSITY
        self.plexiglass_enabled.set(enabled)
        self.plexiglass_intensity_var.set(intensity)
    except Exception:
        pass


def reset_settings_with_plexiglass(self):
    _ORIGINAL_RESET_SETTINGS(self)
    if hasattr(self, "plexiglass_enabled"):
        self.plexiglass_enabled.set(False)
    if hasattr(self, "plexiglass_intensity_var"):
        self.plexiglass_intensity_var.set(DEFAULT_INTENSITY)


def install():
    app.compose_image = compose_with_plexiglass
    app.App._build = build_with_plexiglass
    app.App.current_options = current_options_with_plexiglass
    app.App.settings_payload = settings_payload_with_plexiglass
    app.App.load_settings = load_settings_with_plexiglass
    app.App.reset_settings = reset_settings_with_plexiglass
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD


install()
