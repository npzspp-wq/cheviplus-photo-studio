"""Cheviplus Photo Studio 5.0: fast local BiRefNet quality mode.

Quality mode now runs BiRefNet Lite once on a bounded working copy instead of twice
at full camera resolution. The resulting alpha mask is restored to original size and
passed through conservative product-preservation cleanup. This cuts inference time
and peak RAM while retaining the stronger BiRefNet segmentation.
"""

from __future__ import annotations

import threading
from PIL import Image
from tkinter import ttk

import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION = "5.0"
APP_BUILD = "2026.08.10.01"

MODE_FAST = "Быстро — локально"
MODE_QUALITY = "Максимальное качество AI — локально"
MODES = (MODE_FAST, MODE_QUALITY)

# 1600 px is enough for the catalogue output and dramatically cheaper than running
# the network on full-resolution phone/camera images. Never upscale small originals.
QUALITY_MAX_SIDE = 1600

_LOCAL = threading.local()
_QUALITY_SESSION_LOCAL = threading.local()
_ORIGINAL_COMPOSE = app.compose_image
_FAST_REMOVE = bq.remove_background


def get_quality_session():
    session = getattr(_QUALITY_SESSION_LOCAL, "session", None)
    if session is None:
        from rembg import new_session
        session = new_session("birefnet-general-lite")
        _QUALITY_SESSION_LOCAL.session = session
    return session


def _working_copy(image: Image.Image):
    w, h = image.size
    longest = max(w, h)
    if longest <= QUALITY_MAX_SIDE:
        return image.convert("RGBA"), (w, h)
    scale = QUALITY_MAX_SIDE / float(longest)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return image.convert("RGBA").resize(size, Image.Resampling.LANCZOS), (w, h)


def _quality_segment_alpha(image: Image.Image) -> Image.Image:
    from rembg import remove

    work, original_size = _working_copy(image)
    result = remove(
        work,
        session=get_quality_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")
    alpha = result.getchannel("A")
    if alpha.size != original_size:
        alpha = alpha.resize(original_size, Image.Resampling.LANCZOS)
    return alpha


def build_quality_mask(original: Image.Image) -> Image.Image:
    import numpy as np

    # One BiRefNet pass is both faster and substantially lighter on RAM. The previous
    # enhanced second pass doubled inference cost and caused allocation failures on
    # ordinary PCs. Conservative cleanup below protects disconnected kit components.
    alpha = np.asarray(_quality_segment_alpha(original), dtype=np.uint8)
    combined = bq._safe_background_cleanup(original, alpha)
    support = pc._meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)
    combined = pc._solidify_product_interior(combined)
    combined = pc._remove_detached_paper_components(original, combined)
    return Image.fromarray(combined, mode="L")


def remove_background(img: Image.Image, **kwargs):
    mode = getattr(_LOCAL, "mode", MODE_FAST)
    if mode != MODE_QUALITY:
        return _FAST_REMOVE(img, **kwargs)

    try:
        rgba = img.convert("RGBA")
        rgba.putalpha(build_quality_mask(img))
        recommendations = app.analyze_object_shape(rgba.getchannel("A"))
        return rgba, recommendations
    except Exception as exc:
        # ONNX Runtime reports memory exhaustion as an allocation error. Falling back
        # keeps batch processing alive instead of losing the whole job.
        message = str(exc).lower()
        if "allocate memory" in message or "onnxruntimeerror" in message:
            return _FAST_REMOVE(img, **kwargs)
        raise


def compose_image(*args, processing_mode=MODE_FAST, **kwargs):
    previous = getattr(_LOCAL, "mode", MODE_FAST)
    _LOCAL.mode = processing_mode if processing_mode in MODES else MODE_FAST
    try:
        return _ORIGINAL_COMPOSE(*args, **kwargs)
    finally:
        _LOCAL.mode = previous


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


class AIQualityApp(bq.BackdropQualityApp):
    def _build(self):
        super()._build()
        import tkinter as tk

        self.ai_quality_var = tk.StringVar(value=MODE_FAST)
        frame = _find_label_frame(self, "3. Стабильная ручная обработка")
        if frame is None:
            frame = self

        ttk.Label(frame, text="Качество AI:").grid(row=7, column=0, sticky="w", pady=(10, 4))
        combo = ttk.Combobox(frame, textvariable=self.ai_quality_var, values=MODES,
                             state="readonly", width=36)
        combo.grid(row=7, column=1, columnspan=4, sticky="w", padx=8, pady=(10, 4))
        ttk.Label(
            frame,
            text="Максимальное качество: BiRefNet Lite, ускоренный локальный режим; интернет не нужен.",
            wraplength=720,
        ).grid(row=8, column=0, columnspan=6, sticky="w", pady=(0, 4))

    def current_options(self):
        options = super().current_options()
        options["processing_mode"] = self.ai_quality_var.get()
        return options


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
app.compose_image = compose_image
