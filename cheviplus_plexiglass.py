"""Seamless full-surface plexiglass effect for Cheviplus Photo Studio.

The effect is intentionally edge-free: it does not draw a visible glass rectangle.
It creates a clearly visible, soft mirror reflection below the product plus broad
surface highlights, matching the approved visual reference.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

import app

APP_VERSION = "5.15"
APP_BUILD = "2026.08.17.04"
DEFAULT_INTENSITY = 42
MIN_ENABLED_INTENSITY = 15

_ORIGINAL_COMPOSE = app.compose_image
_ORIGINAL_BUILD = app.App._build
_ORIGINAL_CURRENT_OPTIONS = app.App.current_options
_ORIGINAL_SETTINGS_PAYLOAD = app.App.settings_payload
_ORIGINAL_LOAD_SETTINGS = app.App.load_settings
_ORIGINAL_RESET_SETTINGS = app.App.reset_settings


def _product_mask(final_img: Image.Image, background_path: Path) -> np.ndarray:
    w, h = final_img.size
    bg = app.fit_cover(Image.open(background_path).convert("RGB"), (w, h))
    a = np.asarray(final_img.convert("RGB"), dtype=np.int16)
    b = np.asarray(bg, dtype=np.int16)
    diff = np.max(np.abs(a - b), axis=2)
    mask = diff > 22

    yy, xx = np.ogrid[:h, :w]
    central = (xx > w * 0.05) & (xx < w * 0.95) & (yy > h * 0.08) & (yy < h * 0.84)
    mask &= central
    mask = ndimage.binary_closing(mask, iterations=2)
    labels, count = ndimage.label(mask)
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        main_id = int(sizes.argmax())
        main = labels == main_id
        distance = ndimage.distance_transform_edt(~main)
        keep = main.copy()
        main_size = max(1, int(sizes[main_id]))
        for idx in range(1, count + 1):
            if idx == main_id or sizes[idx] <= 0:
                continue
            comp = labels == idx
            if sizes[idx] >= main_size * 0.012 and float(distance[comp].min()) < max(22, min(w, h) * 0.05):
                keep |= comp
        mask = keep
    return mask


def apply_plexiglass_effect(image: Image.Image, background_path: Path, intensity: int = DEFAULT_INTENSITY) -> Image.Image:
    """Add the approved acrylic-floor look: visible reflection, no visible glass edge."""
    intensity = max(0, min(70, int(intensity)))
    if intensity <= 0:
        return image

    base = image.convert("RGBA")
    w, h = base.size
    mask = _product_mask(base, Path(background_path))
    ys, xs = np.nonzero(mask)
    if len(xs) < 100:
        return base

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    foreground = base.crop((x0, y0, x1, y1)).copy()
    alpha = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8), mode="L")
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(0.4, h / 1700)))
    foreground.putalpha(alpha)

    reflection = foreground.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    rw, rh = reflection.size
    reflected_h = max(1, int(rh * 0.92))
    reflection = reflection.resize((rw, reflected_h), Image.Resampling.LANCZOS)

    arr = np.asarray(reflection.getchannel("A"), dtype=np.float32)
    # Strong near the contact point, then smoothly disappears downward.
    fade = np.linspace(0.78, 0.0, reflected_h, dtype=np.float32)[:, None]
    opacity = 0.38 + intensity / 115.0
    arr = np.clip(arr * fade * opacity, 0, 255).astype(np.uint8)
    alpha_ref = Image.fromarray(arr, mode="L").filter(
        ImageFilter.GaussianBlur(radius=max(0.7, h / 950))
    )
    reflection.putalpha(alpha_ref)

    # Put the mirror image directly under the part so it reads as polished acrylic.
    paste_y = min(h - 1, y1 - max(3, int(rh * 0.075)))
    max_h = max(0, h - paste_y)
    if max_h > 0:
        reflection = reflection.crop((0, 0, rw, min(reflected_h, max_h)))
        base.alpha_composite(reflection, (x0, paste_y))

    # A gentle contact glow anchors the part to the glossy surface without changing its normal shadow.
    contact = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(contact)
    cx = (x0 + x1) // 2
    contact_w = max(24, int((x1 - x0) * 0.72))
    contact_h = max(10, int((y1 - y0) * 0.06))
    cy = min(h - 1, y1 + max(1, int(contact_h * 0.10)))
    cd.ellipse(
        (cx - contact_w // 2, cy - contact_h // 2, cx + contact_w // 2, cy + contact_h // 2),
        fill=(255, 255, 255, int(10 + intensity * 0.28)),
    )
    contact = contact.filter(ImageFilter.GaussianBlur(radius=max(8, int(contact_h * 1.6))))
    base = Image.alpha_composite(base, contact)

    # Full-surface reflections: broad, soft, edge-free streaks.
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheen)
    highlight_alpha = int(18 + intensity * 0.48)
    band = max(26, int(w * 0.026))
    for center in (int(w * 0.16), int(w * 0.76)):
        draw.polygon(
            [
                (center - band * 3, 0),
                (center - band, 0),
                (center + band * 3, h),
                (center + band, h),
            ],
            fill=(255, 255, 255, highlight_alpha),
        )
    sheen = sheen.filter(ImageFilter.GaussianBlur(radius=max(18, int(w * 0.018))))
    base = Image.alpha_composite(base, sheen)

    # Slightly brighter lower half makes the whole surface read as acrylic, without a visible border.
    lift = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    lift_alpha = np.zeros((h, w), dtype=np.uint8)
    start = int(h * 0.43)
    if start < h:
        vals = np.linspace(0, min(30, 10 + intensity // 2), h - start, dtype=np.uint8)
        lift_alpha[start:, :] = vals[:, None]
    lift.putalpha(
        Image.fromarray(lift_alpha, mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(6, h // 160))
        )
    )
    return Image.alpha_composite(base, lift)


def compose_with_plexiglass(source, *args, plexiglass_enabled=False, plexiglass_intensity=DEFAULT_INTENSITY, **kwargs):
    result = _ORIGINAL_COMPOSE(source, *args, **kwargs)
    if plexiglass_enabled:
        intensity = int(plexiglass_intensity)
        if intensity < MIN_ENABLED_INTENSITY:
            intensity = DEFAULT_INTENSITY
        background_path = kwargs.get("background_path")
        if background_path is None and args:
            background_path = args[0]
        if background_path:
            result = apply_plexiglass_effect(result, Path(background_path), intensity)
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
            self.status.set("Эффект оргстекла включён — отражение 42%")

    ttk.Checkbutton(
        effect_box,
        text="Эффект оргстекла — отражение детали на всей поверхности",
        variable=self.plexiglass_enabled,
        command=on_toggle,
    ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 5))
    self._scale_row(
        effect_box,
        1,
        "Видимость отражения",
        self.plexiglass_intensity_var,
        MIN_ENABLED_INTENSITY,
        70,
        lambda v: f"{float(v):.0f}%",
    )
    ttk.Label(
        effect_box,
        text="Как на образце: заметное отражение товара вниз, фон виден, края стекла нет.",
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
