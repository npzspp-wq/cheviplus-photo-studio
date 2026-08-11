"""Cheviplus Photo Studio 5.1: faster repeated AI processing."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import threading
from PIL import Image
from tkinter import ttk

import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION = "5.1"
APP_BUILD = "2026.08.11.01"
MODE_FAST = "Быстро — локально"
MODE_QUALITY = "Максимальное качество AI — локально"
MODES = (MODE_FAST, MODE_QUALITY)
QUALITY_MAX_SIDE = 1600
MASK_CACHE_LIMIT = 16

_LOCAL = threading.local()
_ORIGINAL_COMPOSE = app.compose_image
_FAST_REMOVE = bq.remove_background

# One shared BiRefNet session for the whole application. Earlier builds kept one
# session per worker thread, so Preview and Process could each load the model again.
_QUALITY_SESSION = None
_SESSION_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()

# Small in-memory LRU cache. The mask from Preview can be reused by Process when the
# source file has not changed. Only masks are cached; finished photos are not.
_MASK_CACHE = OrderedDict()
_MASK_CACHE_LOCK = threading.Lock()


def get_quality_session():
    global _QUALITY_SESSION
    if _QUALITY_SESSION is None:
        with _SESSION_LOCK:
            if _QUALITY_SESSION is None:
                from rembg import new_session
                _QUALITY_SESSION = new_session("birefnet-general-lite")
    return _QUALITY_SESSION


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
    # Serializing the heavy inference prevents two workers from competing for RAM.
    # Non-AI work (resize/export/background) can still run in parallel elsewhere.
    with _INFERENCE_LOCK:
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


def _cache_key_from_source(source, mode):
    if mode != MODE_QUALITY:
        return None
    try:
        path = Path(source).resolve()
        stat = path.stat()
        return (str(path).lower(), stat.st_mtime_ns, stat.st_size, mode)
    except Exception:
        return None


def _cache_get(key):
    if key is None:
        return None
    with _MASK_CACHE_LOCK:
        mask = _MASK_CACHE.get(key)
        if mask is None:
            return None
        _MASK_CACHE.move_to_end(key)
        return mask.copy()


def _cache_put(key, mask):
    if key is None:
        return
    with _MASK_CACHE_LOCK:
        _MASK_CACHE[key] = mask.copy()
        _MASK_CACHE.move_to_end(key)
        while len(_MASK_CACHE) > MASK_CACHE_LIMIT:
            _MASK_CACHE.popitem(last=False)


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
        cache_key = getattr(_LOCAL, "cache_key", None)
        mask = _cache_get(cache_key)
        cache_hit = mask is not None
        if mask is None:
            mask = build_quality_mask(img)
            _cache_put(cache_key, mask)

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)
        info = app.analyze_object_shape(mask)
        info["mask_cache_hit"] = cache_hit
        return rgba, info
    except Exception as exc:
        message = str(exc).lower()
        if "allocate memory" in message or "onnxruntimeerror" in message:
            return _FAST_REMOVE(img, **kwargs)
        raise


def compose_image(*args, processing_mode=MODE_FAST, **kwargs):
    previous_mode = getattr(_LOCAL, "mode", MODE_FAST)
    previous_key = getattr(_LOCAL, "cache_key", None)
    mode = processing_mode if processing_mode in MODES else MODE_FAST
    _LOCAL.mode = mode
    source = args[0] if args else kwargs.get("source")
    _LOCAL.cache_key = _cache_key_from_source(source, mode)
    try:
        return _ORIGINAL_COMPOSE(*args, **kwargs)
    finally:
        _LOCAL.mode = previous_mode
        _LOCAL.cache_key = previous_key


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
        ttk.Label(
            frame,
            text="Максимальное качество: BiRefNet Lite. Маска предпросмотра повторно используется при обработке.",
            wraplength=720,
        ).grid(row=8, column=0, columnspan=6, sticky="w", pady=(0, 4))

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
        if self.ai_quality_var.get() == MODE_QUALITY:
            self.status.set("Предпросмотр готов • AI-маска сохранена для быстрой обработки")

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
