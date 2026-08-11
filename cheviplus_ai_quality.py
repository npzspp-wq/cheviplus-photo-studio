"""Cheviplus Photo Studio 5.4: faster AUTO mode without changing manual max quality."""
from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
import threading
from PIL import Image, ImageFilter, ImageStat
from tkinter import ttk
import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION = "5.4"
APP_BUILD = "2026.08.11.01"
MODE_AUTO = "AUTO — скорость + качество"
MODE_FAST = "Быстро — локально"
MODE_QUALITY = "Максимальное качество AI — локально"
MODES = (MODE_AUTO, MODE_FAST, MODE_QUALITY)

QUALITY_MAX_SIDE = 1600
AUTO_SIMPLE_SIDE = 1024
AUTO_COMPLEX_SIDE = 1280
MASK_CACHE_LIMIT = 16

_LOCAL = threading.local()
_ORIGINAL_COMPOSE = app.compose_image
_FAST_REMOVE = bq.remove_background
_QUALITY_SESSION = None
_SESSION_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()
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


def _auto_metrics(image):
    probe = image.convert("RGB")
    probe.thumbnail((320, 320), Image.Resampling.BILINEAR)
    gray = probe.convert("L")
    edge_mean = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
    contrast = ImageStat.Stat(gray).stddev[0]
    return edge_mean, contrast


def _auto_plan(image):
    """Return (engine, side) using only a very cheap 320 px analysis.

    AUTO never uses the expensive 1600 px BiRefNet pass. That proven full-quality
    path remains available as the separate manual Maximum quality mode.
    """
    edge_mean, contrast = _auto_metrics(image)

    # Clear/simple product photos are routed to the lightweight existing engine.
    # Conservative thresholds keep difficult low-contrast/busy images on BiRefNet.
    if edge_mean < 10.5 and contrast > 52:
        return "fast", None

    # Most images use 1024 px BiRefNet; visibly busy or low-contrast scenes get 1280.
    if edge_mean > 21 or contrast < 34:
        return "birefnet", AUTO_COMPLEX_SIDE
    return "birefnet", AUTO_SIMPLE_SIDE


def _working_copy(image, max_side):
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image.convert("RGBA"), (w, h)
    scale = max_side / float(longest)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return image.convert("RGBA").resize(size, Image.Resampling.LANCZOS), (w, h)


def _quality_segment_alpha(image, max_side=QUALITY_MAX_SIDE):
    from rembg import remove
    work, original_size = _working_copy(image, max_side)
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


def _cache_key_from_source(source, mode, side):
    if mode not in (MODE_AUTO, MODE_QUALITY):
        return None
    try:
        path = Path(source).resolve()
        stat = path.stat()
        return (str(path).lower(), stat.st_mtime_ns, stat.st_size, mode, side)
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


def _restore_real_holes(raw_alpha, cleaned):
    import numpy as np
    from scipy import ndimage
    raw = np.asarray(raw_alpha, dtype=np.uint8)
    out = np.asarray(cleaned, dtype=np.uint8).copy()
    h, w = raw.shape
    area = h * w
    labels, count = ndimage.label((raw <= 24) & (out >= 160))
    min_area = max(20, int(area * 0.00003))
    max_area = max(min_area + 1, int(area * 0.08))
    margin = max(2, int(min(h, w) * 0.004))
    for idx in range(1, count + 1):
        ys, xs = np.where(labels == idx)
        n = len(xs)
        if n < min_area or n > max_area:
            continue
        if xs.min() <= margin or ys.min() <= margin or xs.max() >= w - 1 - margin or ys.max() >= h - 1 - margin:
            continue
        hole = ndimage.binary_dilation(labels == idx, iterations=1)
        out[hole] = np.minimum(out[hole], raw[hole])
    return out.astype(np.uint8)


def build_quality_mask(original, max_side=QUALITY_MAX_SIDE):
    import numpy as np
    alpha = np.asarray(_quality_segment_alpha(original, max_side), dtype=np.uint8)
    combined = bq._safe_background_cleanup(original, alpha)
    support = pc._meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)
    combined = pc._solidify_product_interior(combined)
    combined = _restore_real_holes(alpha, combined)
    combined = pc._remove_detached_paper_components(original, combined)
    return Image.fromarray(combined, mode="L")


def remove_background(img, **kwargs):
    mode = getattr(_LOCAL, "mode", MODE_FAST)
    if mode == MODE_FAST:
        return _FAST_REMOVE(img, **kwargs)

    try:
        if mode == MODE_AUTO:
            engine, side = _auto_plan(img)
            if engine == "fast":
                result, info = _FAST_REMOVE(img, **kwargs)
                if isinstance(info, dict):
                    info["auto_engine"] = "fast"
                return result, info
        else:
            engine, side = "birefnet", QUALITY_MAX_SIDE

        source = getattr(_LOCAL, "source", None)
        key = _cache_key_from_source(source, mode, side)
        mask = _cache_get(key)
        cache_hit = mask is not None
        if mask is None:
            mask = build_quality_mask(img, side)
            _cache_put(key, mask)

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)
        info = app.analyze_object_shape(mask)
        info["mask_cache_hit"] = cache_hit
        info["ai_input_side"] = side
        info["auto_engine"] = engine if mode == MODE_AUTO else "birefnet-max"
        return rgba, info
    except Exception as exc:
        message = str(exc).lower()
        if "allocate memory" in message or "onnxruntimeerror" in message:
            return _FAST_REMOVE(img, **kwargs)
        raise


def compose_image(*args, processing_mode=MODE_AUTO, **kwargs):
    previous_mode = getattr(_LOCAL, "mode", MODE_FAST)
    previous_source = getattr(_LOCAL, "source", None)
    mode = processing_mode if processing_mode in MODES else MODE_AUTO
    _LOCAL.mode = mode
    _LOCAL.source = args[0] if args else kwargs.get("source")
    try:
        return _ORIGINAL_COMPOSE(*args, **kwargs)
    finally:
        _LOCAL.mode = previous_mode
        _LOCAL.source = previous_source


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
        self.ai_quality_var = tk.StringVar(value=MODE_AUTO)
        frame = _find_label_frame(self, "3. Стабильная ручная обработка") or self
        ttk.Label(frame, text="Качество AI:").grid(row=7, column=0, sticky="w", pady=(10, 4))
        ttk.Combobox(
            frame,
            textvariable=self.ai_quality_var,
            values=MODES,
            state="readonly",
            width=36,
        ).grid(row=7, column=1, columnspan=4, sticky="w", padx=8, pady=(10, 4))
        ttk.Label(
            frame,
            text="AUTO: простые фото — быстрый движок, остальные — BiRefNet 1024/1280. Максимальное качество 1600 доступно отдельно.",
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
        if self.ai_quality_var.get() in (MODE_AUTO, MODE_QUALITY):
            self.status.set("Предпросмотр готов • результат сохранён для быстрой повторной обработки")

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
