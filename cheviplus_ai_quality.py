"""Cheviplus Photo Studio 5.0: fast local BiRefNet quality mode."""

from __future__ import annotations

import threading
from PIL import Image
from tkinter import ttk

import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION = "5.0"
APP_BUILD = "2026.08.10.02"
MODE_FAST = "Быстро — локально"
MODE_QUALITY = "Максимальное качество AI — локально"
MODES = (MODE_FAST, MODE_QUALITY)
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
    result = remove(work, session=get_quality_session(), alpha_matting=False,
                    post_process_mask=False).convert("RGBA")
    alpha = result.getchannel("A")
    if alpha.size != original_size:
        alpha = alpha.resize(original_size, Image.Resampling.LANCZOS)
    return alpha


def build_quality_mask(original: Image.Image) -> Image.Image:
    import numpy as np
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
        return rgba, app.analyze_object_shape(rgba.getchannel("A"))
    except Exception as exc:
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
        self._ai_busy = False
        self._ai_busy_phase = 0
        self.ai_quality_var = tk.StringVar(value=MODE_FAST)
        frame = _find_label_frame(self, "3. Стабильная ручная обработка") or self
        ttk.Label(frame, text="Качество AI:").grid(row=7, column=0, sticky="w", pady=(10, 4))
        combo = ttk.Combobox(frame, textvariable=self.ai_quality_var, values=MODES,
                             state="readonly", width=36)
        combo.grid(row=7, column=1, columnspan=4, sticky="w", padx=8, pady=(10, 4))
        ttk.Label(frame,
                  text="Максимальное качество: BiRefNet Lite, ускоренный локальный режим; интернет не нужен.",
                  wraplength=720).grid(row=8, column=0, columnspan=6, sticky="w", pady=(0, 4))

    def current_options(self):
        options = super().current_options()
        options["processing_mode"] = self.ai_quality_var.get()
        return options

    def _begin_ai_indicator(self, text):
        self._ai_busy = True
        self._ai_busy_phase = 0
        self._ai_busy_text = text
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self._animate_ai_indicator()

    def _animate_ai_indicator(self):
        if not self._ai_busy:
            return
        frames = ("● ○ ○", "○ ● ○", "○ ○ ●", "○ ● ○")
        self.status.set(f"{self._ai_busy_text}  {frames[self._ai_busy_phase % len(frames)]}")
        self._ai_busy_phase += 1
        self.after(350, self._animate_ai_indicator)

    def _end_ai_indicator(self):
        self._ai_busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")

    def start_preview(self):
        super().start_preview()
        if self.status.get().startswith("Создание предпросмотра"):
            self._begin_ai_indicator("AI обрабатывает фото — пожалуйста, подождите")

    def show_preview(self, image, name):
        self._end_ai_indicator()
        super().show_preview(image, name)

    def start(self):
        super().start()
        if str(self.start_btn.cget("state")) == "disabled":
            self._begin_ai_indicator("AI обрабатывает фотографии")

    def batch_worker(self, files):
        try:
            return super().batch_worker(files)
        finally:
            self.after(0, self._end_ai_indicator)


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
app.compose_image = compose_image
