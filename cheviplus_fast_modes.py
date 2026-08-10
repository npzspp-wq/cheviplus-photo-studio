"""Cheviplus Photo Studio 4.5: fast processing modes on the stable 4.1 core.

This patch deliberately keeps the lightweight u2netp model. The operator can choose
a safer mask strategy for different automotive products without loading heavy models.
"""

from __future__ import annotations

import threading
from PIL import Image, ImageEnhance, ImageOps
from tkinter import ttk

import app
from cheviplus_stability_patch import StableApp

APP_VERSION = "4.5"
APP_BUILD = "2026.08.10.02"

MODE_NORMAL = "Обычная деталь"
MODE_CHROME = "Длинная / хром"
MODE_CARPET = "Ковёр / светлый старый фон"
MODE_LIGHT = "Светлый товар / светлые ковры"
MODE_KIT = "Комплект / несколько деталей"
MODES = (MODE_NORMAL, MODE_CHROME, MODE_CARPET, MODE_LIGHT, MODE_KIT)

_MODE_LOCAL = threading.local()
_ORIGINAL_COMPOSE_IMAGE = app.compose_image
_ORIGINAL_REMOVE_BACKGROUND = app.remove_background


def _normalize_mode(value):
    return value if value in MODES else MODE_NORMAL


def _border_statistics(rgb):
    import numpy as np

    h, w, _ = rgb.shape
    b = max(6, int(min(h, w) * 0.045))
    border = np.concatenate(
        [
            rgb[:b].reshape(-1, 3),
            rgb[-b:].reshape(-1, 3),
            rgb[:, :b].reshape(-1, 3),
            rgb[:, -b:].reshape(-1, 3),
        ],
        axis=0,
    )
    median = np.median(border, axis=0)
    mad = np.maximum(np.median(np.abs(border - median), axis=0), 6.0)
    return median.astype(np.float32), mad.astype(np.float32)


def remove_border_connected_backdrop(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Remove pale old backdrop connected to an outer image edge.

    Used only in the explicit old-background carpet mode. It is intentionally not
    used for light products because beige/grey mats can resemble the pale backdrop.
    """
    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8).copy()
    bg, mad = _border_statistics(rgb)
    scaled = (rgb - bg[None, None, :]) / mad[None, None, :]
    distance = np.sqrt(np.sum(scaled * scaled, axis=2))
    lum = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    bg_like = (distance <= 5.8) | ((lum >= 185) & (chroma <= 48))
    bg_like = ndimage.binary_closing(
        bg_like,
        structure=np.ones((5, 5)),
        iterations=1,
        border_value=1,
    )
    labels, count = ndimage.label(bg_like)
    if not count:
        return alpha

    border_ids = set(np.unique(labels[0, :]).tolist())
    border_ids.update(np.unique(labels[-1, :]).tolist())
    border_ids.update(np.unique(labels[:, 0]).tolist())
    border_ids.update(np.unique(labels[:, -1]).tolist())
    border_ids.discard(0)
    if not border_ids:
        return alpha

    exterior = np.isin(labels, list(border_ids))
    exterior = ndimage.binary_dilation(exterior, structure=np.ones((3, 3)), iterations=1)
    remove = exterior & ((distance <= 6.4) | ((lum >= 178) & (chroma <= 58)))
    a[remove] = 0
    return Image.fromarray(a, mode="L")


def _segment(image: Image.Image):
    from rembg import remove

    return remove(
        image.convert("RGBA"),
        session=app.get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")


def _remove_background_carpet(img: Image.Image, cleanup=82, edge_expand=1, **_kwargs):
    result = _segment(img)
    raw_alpha = result.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)
    raw_alpha = remove_border_connected_backdrop(img, raw_alpha)
    cleaned = app.clean_alpha_mask(raw_alpha, cleanup=max(55, int(cleanup)), edge_expand=edge_expand)
    result.putalpha(cleaned)
    result = app.remove_isolated_artifacts(result, strength=cleanup)
    result.putalpha(app.harden_alpha(result.getchannel("A"), 118))
    return result, recommendations


def _remove_background_light(img: Image.Image, cleanup=82, edge_expand=1, **_kwargs):
    """Special path for beige/light-grey products on a pale photo backdrop.

    u2netp can miss these almost completely when product and background have similar
    brightness. We therefore segment a contrast-normalized copy, but apply the mask
    to the untouched original RGB. This remains a single lightweight model pass.
    Aggressive pale-background cleanup is deliberately disabled in this mode.
    """
    original = img.convert("RGBA")
    rgb = img.convert("RGB")

    # Stretch tonal range first, then add moderate local visual separation. This is
    # only the model input; the exported product keeps the original colours.
    model_input = ImageOps.autocontrast(rgb, cutoff=0.6)
    model_input = ImageEnhance.Contrast(model_input).enhance(1.38)
    model_input = ImageEnhance.Color(model_input).enhance(1.16)
    model_input = ImageEnhance.Sharpness(model_input).enhance(1.12)

    segmented = _segment(model_input)
    raw_alpha = segmented.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)

    # Preserve weak pale-product probabilities instead of treating them as dirt.
    cleaned = app.clean_alpha_mask(raw_alpha, cleanup=12, edge_expand=1)
    original.putalpha(cleaned)
    # Low hardening threshold prevents the branded replacement background from
    # showing through light rubber while retaining a narrow natural edge.
    original.putalpha(app.harden_alpha(original.getchannel("A"), 72))
    return original, recommendations


def _remove_background_chrome(img: Image.Image, cleanup=82, edge_expand=1, **_kwargs):
    """Gentle path for long reflective parts."""
    result = _segment(img)
    raw_alpha = result.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)
    cleaned = app.clean_alpha_mask(raw_alpha, cleanup=24, edge_expand=1)
    result.putalpha(cleaned)
    result.putalpha(app.harden_alpha(result.getchannel("A"), 88))
    return result, recommendations


def _remove_background_kit(img: Image.Image, cleanup=82, edge_expand=1, **_kwargs):
    """Preserve multiple disconnected real parts and avoid single-object assumptions."""
    result = _segment(img)
    raw_alpha = result.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)
    cleaned = app.clean_alpha_mask(raw_alpha, cleanup=36, edge_expand=max(0, min(1, int(edge_expand))))
    result.putalpha(cleaned)
    result = app.remove_isolated_artifacts(result, strength=36)
    return result, recommendations


def remove_background(img: Image.Image, **kwargs):
    mode = _normalize_mode(getattr(_MODE_LOCAL, "mode", MODE_NORMAL))
    if mode == MODE_CARPET:
        return _remove_background_carpet(img, **kwargs)
    if mode == MODE_LIGHT:
        return _remove_background_light(img, **kwargs)
    if mode == MODE_CHROME:
        return _remove_background_chrome(img, **kwargs)
    if mode == MODE_KIT:
        return _remove_background_kit(img, **kwargs)
    return _ORIGINAL_REMOVE_BACKGROUND(img, **kwargs)


def compose_image(*args, processing_mode=MODE_NORMAL, **kwargs):
    previous = getattr(_MODE_LOCAL, "mode", MODE_NORMAL)
    _MODE_LOCAL.mode = _normalize_mode(processing_mode)
    try:
        return _ORIGINAL_COMPOSE_IMAGE(*args, **kwargs)
    finally:
        _MODE_LOCAL.mode = previous


def _find_label_frame(root, title):
    for child in root.winfo_children():
        try:
            if isinstance(child, ttk.LabelFrame) and child.cget("text") == title:
                return child
        except Exception:
            pass
        found = _find_label_frame(child, title)
        if found is not None:
            return found
    return None


class FastModeApp(StableApp):
    def _build(self):
        super()._build()
        import tkinter as tk

        self.processing_mode_var = tk.StringVar(value=MODE_NORMAL)
        advanced = _find_label_frame(self, "3. Стабильная ручная обработка")
        if advanced is not None:
            ttk.Label(advanced, text="Режим детали:").grid(
                row=5, column=0, sticky="w", pady=(10, 4)
            )
            combo = ttk.Combobox(
                advanced,
                textvariable=self.processing_mode_var,
                values=MODES,
                state="readonly",
                width=34,
            )
            combo.grid(row=5, column=1, columnspan=4, sticky="w", padx=8, pady=(10, 4))
            ttk.Label(
                advanced,
                text=(
                    "Хром — мягкая маска; светлый товар — усиление контраста только для AI; "
                    "ковёр — очистка светлой старой подложки; комплект — сохраняет отдельные детали."
                ),
                wraplength=720,
            ).grid(row=6, column=0, columnspan=6, sticky="w", pady=(0, 4))

    def current_options(self):
        options = super().current_options()
        options["processing_mode"] = _normalize_mode(self.processing_mode_var.get())
        return options


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
app.compose_image = compose_image
