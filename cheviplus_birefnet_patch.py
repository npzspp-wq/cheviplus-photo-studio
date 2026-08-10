"""Cheviplus Photo Studio 4.4 test patch: BiRefNet with minimal post-processing.

Goal: preserve real automotive parts first, especially chrome, glossy surfaces,
long bumpers, and multiple-piece kits. Aggressive cleanup is intentionally avoided.
"""

from __future__ import annotations

import threading
from PIL import Image

import app

APP_VERSION = "4.4"
APP_BUILD = "2026.08.10.01"

_SESSION_LOCAL = threading.local()


def get_rembg_session():
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        from rembg import new_session
        session = new_session("birefnet-general")
        _SESSION_LOCAL.session = session
    return session


def _is_long_part(alpha: Image.Image) -> bool:
    import numpy as np

    a = np.asarray(alpha, dtype=np.uint8)
    ys, xs = np.nonzero(a >= 80)
    if len(xs) < 50:
        return False
    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    aspect = max(bw / max(1, bh), bh / max(1, bw))
    occupancy = float((a >= 80).sum()) / float(max(1, bw * bh))
    return aspect >= 2.3 and occupancy <= 0.72


def remove_border_connected_backdrop(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Conservative cleanup for pale old backdrops; skipped for long parts."""
    import numpy as np
    from scipy import ndimage

    if _is_long_part(alpha):
        return alpha

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8).copy()
    h, w, _ = rgb.shape
    b = max(6, int(min(h, w) * 0.045))
    border = np.concatenate([
        rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
        rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3),
    ], axis=0)
    bg = np.median(border, axis=0)
    mad = np.maximum(np.median(np.abs(border - bg), axis=0), 6.0)
    distance = np.sqrt(np.sum(((rgb - bg) / mad) ** 2, axis=2))
    lum = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    bg_like = (distance <= 5.2) | ((lum >= 190) & (chroma <= 42))
    bg_like = ndimage.binary_closing(
        bg_like, structure=np.ones((5, 5)), iterations=1, border_value=1
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
    remove = exterior & ((distance <= 5.8) | ((lum >= 185) & (chroma <= 48)))
    a[remove] = 0
    return Image.fromarray(a, mode="L")


def _minimal_alpha_cleanup(alpha: Image.Image, long_part: bool) -> Image.Image:
    """Only remove extremely weak alpha noise; preserve holes and disconnected kit pieces."""
    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8).copy()
    arr[arr < 6] = 0

    # Keep soft edge information. Never fill holes globally.
    if long_part:
        # Long chrome parts are especially fragile: no component pruning.
        return Image.fromarray(arr, mode="L")

    binary = arr >= 18
    labels, count = ndimage.label(binary)
    if count <= 1:
        return Image.fromarray(arr, mode="L")

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = max(1, int(sizes.max()))
    keep = np.zeros_like(binary, dtype=bool)
    h, w = binary.shape

    for idx in range(1, count + 1):
        size = int(sizes[idx])
        if size <= 0:
            continue
        ys, xs = np.nonzero(labels == idx)
        bw = int(xs.max() - xs.min() + 1)
        bh = int(ys.max() - ys.min() + 1)
        meaningful = size >= max(28, int(largest * 0.003))
        extended = max(bw / max(1, w), bh / max(1, h)) >= 0.045 and size >= 20
        if meaningful or extended:
            keep |= labels == idx

    arr[~keep] = 0
    return Image.fromarray(arr, mode="L")


def remove_background(
    img: Image.Image,
    cleanup=45,
    edge_expand=1,
    auto_settings=True,
    prevent_background_showthrough=True,
    strict_logo_cleanup=True,
):
    from rembg import remove

    result = remove(
        img.convert("RGBA"),
        session=get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")

    raw_alpha = result.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)
    long_part = _is_long_part(raw_alpha)

    # Preserve the model's geometry first. The rug/background helper runs only on
    # non-long parts and is deliberately conservative.
    raw_alpha = remove_border_connected_backdrop(img, raw_alpha)
    cleaned_alpha = _minimal_alpha_cleanup(raw_alpha, long_part)
    result.putalpha(cleaned_alpha)

    # Do not call suppress_old_background/remove_isolated_artifacts/harden_alpha in
    # this test path: those operations can erase chrome, fill true holes, or drop kit
    # pieces. We want to evaluate the model itself before adding cleanup back.
    return result, recommendations


def install():
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD
    app.get_rembg_session = get_rembg_session
    app.remove_background = remove_background


install()
