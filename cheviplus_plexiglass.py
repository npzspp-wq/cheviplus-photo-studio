"""Cheviplus plexiglass studio background and product placement.

The approved look is implemented as a real selectable background with a virtual
acrylic table. Products are automatically scaled and placed on the table contact
line, then reflected into the glossy surface. There is no visible glass edge.
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
APP_BUILD = "2026.08.18.01"
DEFAULT_INTENSITY = 45
MIN_ENABLED_INTENSITY = 15
TABLE_BACKGROUND_NAME = "Фон 4 — Cheviplus Оргстекло"
TABLE_HORIZON = 0.58
TABLE_CONTACT = 0.665
TABLE_BG_PATH = app.APP_DIR / "generated_backgrounds" / "cheviplus_plexiglass_studio.jpg"

_ORIGINAL_COMPOSE = app.compose_image
_ORIGINAL_BUILD = app.App._build
_ORIGINAL_CURRENT_OPTIONS = app.App.current_options
_ORIGINAL_SETTINGS_PAYLOAD = app.App.settings_payload
_ORIGINAL_LOAD_SETTINGS = app.App.load_settings
_ORIGINAL_RESET_SETTINGS = app.App.reset_settings


def _make_plexiglass_background() -> Path:
    """Create the approved wall + glossy acrylic table from the existing brand background."""
    try:
        TABLE_BG_PATH.parent.mkdir(parents=True, exist_ok=True)
        source = app.DEFAULT_BG_1 if app.DEFAULT_BG_1.exists() else next(iter(app.BUILTIN_BACKGROUNDS.values()))
        src = Image.open(source).convert("RGB")
        w, h = 1600, 1066
        wall_h = int(h * TABLE_HORIZON)

        wall = app.fit_cover(src, (w, wall_h))
        canvas = Image.new("RGB", (w, h), (245, 246, 247))
        canvas.paste(wall, (0, 0))

        # The table reflects the branded wall but becomes brighter and softer with distance.
        reflected = wall.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        floor_h = h - wall_h
        reflected = reflected.resize((w, floor_h), Image.Resampling.LANCZOS)
        reflected = reflected.filter(ImageFilter.GaussianBlur(radius=1.4))
        floor = Image.new("RGB", (w, floor_h), (247, 248, 249))
        floor = Image.blend(floor, reflected, 0.22)

        # Fade the reflected logos gradually into a white acrylic surface.
        arr = np.asarray(floor, dtype=np.float32)
        fade = np.linspace(0.94, 0.28, floor_h, dtype=np.float32)[:, None, None]
        white = np.full_like(arr, 249.0)
        arr = arr * fade + white * (1.0 - fade)
        floor = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        canvas.paste(floor, (0, wall_h))

        rgba = canvas.convert("RGBA")
        # Thin horizon/contact seam; it reads as a studio cyclorama, not a glass edge.
        seam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(seam)
        sd.rectangle((0, wall_h - 2, w, wall_h + 3), fill=(160, 166, 171, 24))
        seam = seam.filter(ImageFilter.GaussianBlur(radius=3))
        rgba = Image.alpha_composite(rgba, seam)

        # Long soft light streaks across the acrylic plane, matching the approved example.
        gloss = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gloss)
        for center, alpha in ((250, 44), (710, 34), (1220, 48), (1480, 28)):
            band = 22
            gd.polygon([
                (center - 40, wall_h - 10),
                (center + band, wall_h - 10),
                (center + 250, h),
                (center + 165, h),
            ], fill=(255, 255, 255, alpha))
        gloss = gloss.filter(ImageFilter.GaussianBlur(radius=20))
        rgba = Image.alpha_composite(rgba, gloss)

        rgba.convert("RGB").save(TABLE_BG_PATH, "JPEG", quality=93, optimize=True, progressive=True)
    except Exception:
        return app.DEFAULT_BG_1
    return TABLE_BG_PATH


def _is_table_background(path) -> bool:
    try:
        return Path(path).resolve() == TABLE_BG_PATH.resolve()
    except Exception:
        return str(path).lower().endswith("cheviplus_plexiglass_studio.jpg")


def _extract_options(args, kwargs):
    options = dict(kwargs)
    names = [
        "background_path", "logo_path", "canvas_width", "canvas_height", "product_fill", "add_logo",
        "shadow", "shadow_strength", "cleanup", "edge_expand", "sharpness", "straighten", "auto_settings",
        "prevent_background_showthrough", "strict_logo_cleanup", "remove_product_logo", "logo_remove_strength"
    ]
    for name, value in zip(names, args):
        options.setdefault(name, value)
    return options


def _rebuild_product_cutout(source, options, table_mode=False):
    """Create the segmented product once and size it for normal or virtual-table placement."""
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
    if options.get("straighten"):
        product = app.trim_transparency(app.auto_straighten(product))
    if options.get("remove_product_logo"):
        product = app.remove_product_logo_region(product, options.get("logo_remove_strength", 55))

    sharpness = max(0, min(100, int(options.get("sharpness", 45))))
    rgb = ImageEnhance.Contrast(product.convert("RGB")).enhance(1.02)
    if sharpness:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.65 + sharpness / 180, percent=45 + int(sharpness * 1.25), threshold=2))
    product = Image.merge("RGBA", (*rgb.split(), product.getchannel("A")))

    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    aspect = product.width / max(1, product.height)

    if table_mode:
        # Virtual-table placement rules. Keep enough floor visible for a realistic reflection.
        if aspect >= 3.0:          # long trim, pipes, mouldings
            max_w, max_h = cw * 0.84, ch * 0.30
            contact = ch * 0.66
        elif aspect <= 0.45:       # tall parts
            max_w, max_h = cw * 0.44, ch * 0.48
            contact = ch * 0.69
        elif aspect >= 1.65:       # wide assemblies
            max_w, max_h = cw * 0.70, ch * 0.40
            contact = ch * 0.665
        else:                      # normal parts
            max_w, max_h = cw * 0.60, ch * 0.43
            contact = ch * 0.665
        ratio = min(max_w / max(1, product.width), max_h / max(1, product.height))
        product = product.resize((max(1, int(product.width * ratio)), max(1, int(product.height * ratio))), Image.Resampling.LANCZOS)
        x = (cw - product.width) // 2
        y = int(contact - product.height)
        y = max(int(ch * 0.10), min(y, int(ch * 0.73) - product.height))
    else:
        product_fill = float(options.get("product_fill", 0.86))
        if options.get("auto_settings"):
            product_fill = auto_info.get("fill", product_fill)
        ratio = min((cw * product_fill) / max(1, product.width), (ch * product_fill) / max(1, product.height))
        product = product.resize((max(1, int(product.width * ratio)), max(1, int(product.height * ratio))), Image.Resampling.LANCZOS)
        x = (cw - product.width) // 2
        y = int(ch * 0.54 - product.height / 2)
        y = max(20, min(y, ch - product.height - 20))
    return product, x, y


def _add_logo(base, options):
    logo_path = Path(options.get("logo_path") or app.DEFAULT_LOGO)
    if not options.get("add_logo") or not logo_path.exists():
        return
    w, h = base.size
    logo = Image.open(logo_path).convert("RGBA")
    scale = min(1.0, (w * 0.15) / max(1, logo.width))
    logo = logo.resize((max(1, int(logo.width * scale)), max(1, int(logo.height * scale))), Image.Resampling.LANCZOS)
    margin = int(min(w, h) * 0.025)
    base.alpha_composite(logo, (w - logo.width - margin, h - logo.height - margin))


def _reflection_layer(product, canvas_size, x, y, intensity):
    w, h = canvas_size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    reflection = product.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    reflected_h = max(1, int(product.height * 0.88))
    reflection = reflection.resize((product.width, reflected_h), Image.Resampling.LANCZOS)
    alpha = np.asarray(reflection.getchannel("A"), dtype=np.float32)
    fade = np.linspace(0.62, 0.0, reflected_h, dtype=np.float32)[:, None]
    strength = 0.26 + max(MIN_ENABLED_INTENSITY, intensity) / 155.0
    alpha = np.clip(alpha * fade * strength, 0, 255).astype(np.uint8)
    reflection.putalpha(Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(radius=max(0.8, h / 1000))))
    paste_y = y + product.height - max(1, int(product.height * 0.025))
    if paste_y < h:
        reflection = reflection.crop((0, 0, reflection.width, min(reflection.height, h - paste_y)))
        layer.alpha_composite(reflection, (x, paste_y))
    return layer


def _compose_table_scene(source, options, intensity):
    cw = int(options.get("canvas_width", 1280))
    ch = int(options.get("canvas_height", 960))
    bg_path = Path(options["background_path"])
    base = app.fit_cover(Image.open(bg_path).convert("RGB"), (cw, ch)).convert("RGBA")
    product, x, y = _rebuild_product_cutout(source, options, table_mode=True)

    # Reflection belongs under the part on the imaginary acrylic table.
    base = Image.alpha_composite(base, _reflection_layer(product, (cw, ch), x, y, intensity))

    # Contact shadow is short and soft; never let it replace the reflection.
    if options.get("shadow", True):
        shadow_strength = min(42, max(16, int(options.get("shadow_strength", 28))))
        app.add_shadow(base, product, (x, y), shadow_strength)
    base.alpha_composite(product, (x, y))
    _add_logo(base, options)
    return base


def apply_plexiglass_from_product(image, product, x, y, intensity=DEFAULT_INTENSITY):
    base = image.convert("RGBA")
    layer = _reflection_layer(product, base.size, x, y, intensity)
    base = Image.alpha_composite(base, layer)
    return base


def compose_with_plexiglass(source, *args, plexiglass_enabled=False, plexiglass_intensity=DEFAULT_INTENSITY, **kwargs):
    options = _extract_options(args, kwargs)
    background_path = options.get("background_path")
    intensity = int(plexiglass_intensity)
    if intensity < MIN_ENABLED_INTENSITY:
        intensity = DEFAULT_INTENSITY

    # Selecting the dedicated background automatically activates correct table placement and reflection.
    if background_path and _is_table_background(background_path):
        try:
            return _compose_table_scene(source, options, intensity)
        except Exception:
            return _ORIGINAL_COMPOSE(source, *args, **kwargs)

    result = _ORIGINAL_COMPOSE(source, *args, **kwargs)
    if not plexiglass_enabled:
        return result
    try:
        product, x, y = _rebuild_product_cutout(source, options, table_mode=False)
        return apply_plexiglass_from_product(result, product, x, y, intensity)
    except Exception:
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

    ttk.Checkbutton(
        effect_box,
        text="Эффект оргстекла — отражение детали на глянцевой поверхности",
        variable=self.plexiglass_enabled,
    ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 5))
    self._scale_row(effect_box, 1, "Видимость отражения", self.plexiglass_intensity_var, MIN_ENABLED_INTENSITY, 75, lambda v: f"{float(v):.0f}%")
    ttk.Label(effect_box, text="Для готового студийного вида выберите «Фон 4 — Cheviplus Оргстекло»: деталь сама встанет на виртуальный стол.").grid(row=2, column=0, columnspan=6, sticky="w", pady=(3, 0))


def current_options_with_plexiglass(self):
    options = _ORIGINAL_CURRENT_OPTIONS(self)
    enabled_var = getattr(self, "plexiglass_enabled", None)
    intensity_var = getattr(self, "plexiglass_intensity_var", None)
    options["plexiglass_enabled"] = bool(enabled_var.get()) if enabled_var is not None else False
    options["plexiglass_intensity"] = int(intensity_var.get()) if intensity_var is not None else DEFAULT_INTENSITY
    return options


def settings_payload_with_plexiglass(self):
    data = _ORIGINAL_SETTINGS_PAYLOAD(self)
    data.update(current_options_with_plexiglass(self))
    return data


def load_settings_with_plexiglass(self):
    _ORIGINAL_LOAD_SETTINGS(self)
    if not app.SETTINGS_FILE.exists():
        return
    try:
        import json
        data = json.loads(app.SETTINGS_FILE.read_text(encoding="utf-8"))
        self.plexiglass_enabled.set(bool(data.get("plexiglass_enabled", False)))
        self.plexiglass_intensity_var.set(max(MIN_ENABLED_INTENSITY, int(data.get("plexiglass_intensity", DEFAULT_INTENSITY))))
    except Exception:
        pass


def reset_settings_with_plexiglass(self):
    _ORIGINAL_RESET_SETTINGS(self)
    if hasattr(self, "plexiglass_enabled"):
        self.plexiglass_enabled.set(False)
    if hasattr(self, "plexiglass_intensity_var"):
        self.plexiglass_intensity_var.set(DEFAULT_INTENSITY)


def install():
    table_bg = _make_plexiglass_background()
    app.DEFAULT_BACKGROUND_NAMES[TABLE_BACKGROUND_NAME] = table_bg
    app.BUILTIN_BACKGROUNDS[TABLE_BACKGROUND_NAME] = table_bg
    app.compose_image = compose_with_plexiglass
    app.App._build = build_with_plexiglass
    app.App.current_options = current_options_with_plexiglass
    app.App.settings_payload = settings_payload_with_plexiglass
    app.App.load_settings = load_settings_with_plexiglass
    app.App.reset_settings = reset_settings_with_plexiglass
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD


install()
