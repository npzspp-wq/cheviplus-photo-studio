"""Runtime stability fixes for Cheviplus Photo Studio.

The original app.py is intentionally left mostly intact.  This module patches only
risk areas found during the audit: conservative component preservation during mask
cleanup, Tkinter grid placement, safer option parsing, cancellation behavior and
cross-platform output opening.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Iterable

from PIL import Image

import app


def _component_bboxes(labels, count):
    import numpy as np

    boxes = {}
    for idx in range(1, count + 1):
        ys, xs = np.nonzero(labels == idx)
        if len(xs):
            boxes[idx] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return boxes


def _bbox_area(box):
    x0, y0, x1, y1 = box
    return max(1, (x1 - x0 + 1) * (y1 - y0 + 1))


def _keep_meaningful_components(binary, min_abs=60, min_fraction=0.006):
    """Keep several real kit parts instead of assuming one largest object only."""
    import numpy as np
    from scipy import ndimage

    labels, count = ndimage.label(binary)
    if count <= 1:
        return binary, labels, count

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = max(1, int(sizes.max()))
    boxes = _component_bboxes(labels, count)
    h, w = binary.shape
    keep = np.zeros_like(binary, dtype=bool)

    for idx in range(1, count + 1):
        size = int(sizes[idx])
        if size <= 0:
            continue
        x0, y0, x1, y1 = boxes.get(idx, (0, 0, -1, -1))
        bw = x1 - x0 + 1
        bh = y1 - y0 + 1
        long_real_part = max(bw / max(1, w), bh / max(1, h)) >= 0.08 and size >= min_abs
        large_part = size >= max(min_abs, int(largest * min_fraction))
        if large_part or long_real_part:
            keep |= labels == idx

    return keep, labels, count


def suppress_old_background(alpha: Image.Image, strict=True):
    """Remove edge-connected background leakage while preserving separated kit parts.

    The previous version kept any sufficiently large component.  On product photos
    shot against a branded banner/table this could preserve large pieces of the old
    scene.  This version treats components connected to the image border as likely
    background, while keeping confident interior components (including separate
    brackets/plates from a kit).
    """
    if not strict:
        return alpha

    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8)
    h, w = arr.shape
    image_area = max(1, h * w)

    # Build a confident core. A light erosion breaks thin accidental bridges between
    # the product and banner/table before connected-component analysis.
    core0 = arr >= 170
    eroded = ndimage.binary_erosion(core0, structure=np.ones((3, 3)), iterations=1)
    labels, count = ndimage.label(eroded)
    if count == 0:
        return alpha

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    boxes = _component_bboxes(labels, count)
    keep_core = np.zeros_like(core0, dtype=bool)

    margin_y = max(2, int(h * 0.012))
    margin_x = max(2, int(w * 0.012))
    min_part = max(36, int(image_area * 0.00018))
    largest = max(1, int(sizes.max()))

    for idx in range(1, count + 1):
        size = int(sizes[idx])
        if size < min_part:
            continue
        x0, y0, x1, y1 = boxes.get(idx, (0, 0, -1, -1))
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        touches_border = (
            x0 <= margin_x or y0 <= margin_y
            or x1 >= w - 1 - margin_x or y1 >= h - 1 - margin_y
        )
        # Interior sizeable pieces are product candidates.  A border component is
        # accepted only when it is dominant and spans the central image area; this
        # avoids deleting a legitimately cropped large product.
        cx = (x0 + x1) * 0.5
        cy = (y0 + y1) * 0.5
        central = (0.12 * w <= cx <= 0.88 * w and 0.10 * h <= cy <= 0.90 * h)
        dominant = size >= largest * 0.55 and bw >= w * 0.28 and bh >= h * 0.08
        if (not touches_border) or (dominant and central):
            keep_core |= labels == idx

    if not keep_core.any():
        # Fail safe: never return an empty mask.
        main_id = int(sizes.argmax())
        keep_core = labels == main_id

    # Restore the one-pixel erosion and allow only a narrow natural alpha fringe.
    keep_core = ndimage.binary_dilation(keep_core, structure=np.ones((3, 3)), iterations=1)
    support = arr >= 24
    distance = ndimage.distance_transform_edt(~keep_core)
    candidate = support & (keep_core | (distance <= 6.0))

    # Preserve separate real kit pieces that are confidently segmented and interior.
    confident = arr >= 205
    c_labels, c_count = ndimage.label(confident)
    if c_count:
        c_sizes = np.bincount(c_labels.ravel())
        c_sizes[0] = 0
        c_boxes = _component_bboxes(c_labels, c_count)
        for idx in range(1, c_count + 1):
            size = int(c_sizes[idx])
            if size < min_part:
                continue
            x0, y0, x1, y1 = c_boxes.get(idx, (0, 0, -1, -1))
            touches_border = (
                x0 <= margin_x or y0 <= margin_y
                or x1 >= w - 1 - margin_x or y1 >= h - 1 - margin_y
            )
            if not touches_border:
                part = c_labels == idx
                # Include the original soft edge around the confident component.
                d = ndimage.distance_transform_edt(~part)
                candidate |= support & (d <= 5.0)

    # Any weak region still connected to the outer frame is old-scene leakage.
    weak = candidate & (arr < 150)
    border_seed = np.zeros_like(weak, dtype=bool)
    border_seed[0, :] = weak[0, :]
    border_seed[-1, :] = weak[-1, :]
    border_seed[:, 0] |= weak[:, 0]
    border_seed[:, -1] |= weak[:, -1]
    if border_seed.any():
        edge_leak = ndimage.binary_propagation(border_seed, mask=weak)
        candidate &= ~edge_leak

    result = np.where(candidate, arr, 0).astype(np.uint8)
    result[keep_core] = 255
    result[result < 22] = 0
    return Image.fromarray(result, mode="L")

def remove_isolated_artifacts(rgba: Image.Image, strength=82):
    """Remove small floating artefacts while keeping real separated set items."""
    import numpy as np
    from scipy import ndimage

    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    binary = alpha >= 52
    labels, count = ndimage.label(binary)
    if count <= 1:
        return rgba

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = max(1, int(sizes.max()))
    main_id = int(sizes.argmax())
    main_mask = labels == main_id
    distance = ndimage.distance_transform_edt(~main_mask)
    boxes = _component_bboxes(labels, count)
    h, w = alpha.shape

    keep = main_mask.copy()
    for idx in range(1, count + 1):
        if idx == main_id or sizes[idx] == 0:
            continue
        component = labels == idx
        size = int(sizes[idx])
        x0, y0, x1, y1 = boxes.get(idx, (0, 0, -1, -1))
        bw = x1 - x0 + 1
        bh = y1 - y0 + 1
        close = float(distance[component].min()) <= max(14, min(alpha.shape) * 0.03)
        real_size = size >= max(35, int(largest * 0.010))
        real_separate_part = (
            size >= max(90, int(largest * 0.018))
            and max(bw / max(1, w), bh / max(1, h)) >= 0.06
        )
        if (close and real_size) or real_separate_part:
            keep |= component

    cleaned_alpha = np.where(keep, alpha, 0).astype(np.uint8)
    result = rgba.copy()
    result.putalpha(Image.fromarray(cleaned_alpha, mode="L"))
    return result


def _safe_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _safe_float(value, default, minimum=None, maximum=None):
    try:
        parsed = float(str(value).strip())
    except Exception:
        parsed = float(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _widget_text(widget):
    try:
        return widget.cget("text")
    except Exception:
        return ""


def _walk_widgets(root) -> Iterable[object]:
    for child in root.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _fix_basic_grid(root):
    """Repair the audited Tkinter/grid placement without rebuilding the UI."""
    width_label = None
    shadow_check = None
    for widget in _walk_widgets(root):
        text = _widget_text(widget)
        if text == "Ширина:":
            width_label = widget
        elif text == "Мягкая тень":
            shadow_check = widget

    if width_label is not None:
        width_label.grid_configure(row=1, column=0, sticky="w", pady=(10, 0))
    if shadow_check is not None:
        shadow_check.grid_configure(row=3, column=0, sticky="w", pady=(10, 0))


def current_options(self):
    return dict(
        background_path=Path(self.bg_var.get()),
        logo_path=Path(self.logo_var.get()),
        canvas_width=_safe_int(self.width_var.get(), 1024, 200, 6000),
        canvas_height=_safe_int(self.height_var.get(), 685, 200, 6000),
        product_fill=_safe_float(self.fill_var.get(), 0.86, 0.25, 0.98),
        add_logo=bool(self.logo_enabled.get()),
        shadow=bool(self.shadow_enabled.get()),
        shadow_strength=_safe_int(self.shadow_strength_var.get(), 35, 0, 80),
        cleanup=_safe_int(self.cleanup_var.get(), 82, 0, 100),
        edge_expand=_safe_int(round(float(self.edge_expand_var.get())), 1, 0, 4),
        sharpness=_safe_int(self.sharpness_var.get(), 45, 0, 100),
        straighten=bool(self.straighten_var.get()),
        auto_settings=False,
        prevent_background_showthrough=bool(self.prevent_showthrough_var.get()),
        # Keep conservative defaults: do not remove product logos or kit pieces aggressively.
        strict_logo_cleanup=False,
        remove_product_logo=False,
        logo_remove_strength=_safe_int(self.logo_remove_strength_var.get(), 55, 0, 100),
    )


def open_output(self):
    path = Path(self.output_var.get())
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def batch_worker(self, files):
    options = self.current_options()
    input_root = Path(self.input_var.get())
    output_root = Path(self.output_var.get())
    workers = _safe_int(self.workers_var.get(), 2, 1, 4)
    completed = ok = errors = 0

    def one(source):
        if self.cancel_requested:
            return source, None, "Остановлено"
        target_dir = output_root
        try:
            if input_root.exists() and input_root in source.parents:
                target_dir = output_root / source.parent.relative_to(input_root)
        except Exception:
            pass
        image = app.compose_image(source, **options)
        out = app.save_result(
            image,
            source,
            target_dir,
            self.format_var.get(),
            target_kb=_safe_int(self.target_kb_var.get() or 0, 0, 0, 100000),
            jpeg_quality=_safe_int(self.jpeg_quality_var.get() or 88, 88, 45, 95),
        )
        return source, out, None

    try:
        iterator = iter(files)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}

            def submit_more():
                while not self.cancel_requested and len(futures) < workers:
                    try:
                        source = next(iterator)
                    except StopIteration:
                        return
                    futures[executor.submit(one, source)] = source

            submit_more()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    source = futures.pop(future)
                    try:
                        _, out, error = future.result()
                        if error:
                            errors += 1
                            self.ui_queue.put(("log", f"ПРОПУЩЕНО {source.name}: {error}"))
                        else:
                            ok += 1
                            self.ui_queue.put(("log", f"OK {source.name} → {out}"))
                    except Exception as exc:
                        errors += 1
                        self.ui_queue.put(("log", f"ОШИБКА {source.name}: {exc}"))
                    completed += 1
                    self.ui_queue.put(("progress", completed, len(files), source.name))
                submit_more()
        self.ui_queue.put(("done", ok, errors, self.cancel_requested))
    except Exception:
        import traceback

        self.ui_queue.put(("error", traceback.format_exc()))


def process_ui_queue(self):
    try:
        while True:
            event = self.ui_queue.get_nowait()
            kind = event[0]
            if kind == "preview":
                self.show_preview(event[1], event[2])
            elif kind == "log":
                self.write_log(event[1])
            elif kind == "progress":
                done, total, name = event[1:]
                self.progress["value"] = done
                self.status.set(f"Обработка {done} из {total}: {name}")
            elif kind == "done":
                ok, errors, stopped = event[1:]
                self.start_btn.config(state="normal")
                self.cancel_btn.config(state="disabled")
                self.status.set(f"Готово. Успешно: {ok}; ошибок: {errors}")
                title = "Обработка остановлена" if stopped else "Обработка завершена"
                app.messagebox.showinfo(title, f"Обработано: {ok}\nОшибок: {errors}")
            elif kind == "error":
                self.start_btn.config(state="normal")
                self.cancel_btn.config(state="disabled")
                self.status.set("Ошибка")
                app.messagebox.showerror("Ошибка", event[1])
    except queue.Empty:
        pass
    self.after(100, self.process_ui_queue)


class StableApp(app.App):
    def _build(self):
        super()._build()
        _fix_basic_grid(self)


# Patch functions used by app.compose_image and by inherited App methods.
app.suppress_old_background = suppress_old_background
app.remove_isolated_artifacts = remove_isolated_artifacts
app.App.current_options = current_options
app.App.open_output = open_output
app.App.batch_worker = batch_worker
app.App.process_ui_queue = process_ui_queue
