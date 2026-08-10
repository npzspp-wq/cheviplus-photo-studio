"""Cheviplus Photo Studio 4.3 test patch: ISNet model + safe backdrop cleanup."""

from __future__ import annotations

import threading
from PIL import Image

import app

APP_VERSION = "4.3"
APP_BUILD = "2026.08.10.01"

_SESSION_LOCAL = threading.local()


def get_rembg_session():
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        from rembg import new_session
        session = new_session("isnet-general-use")
        _SESSION_LOCAL.session = session
    return session


def _is_long_part(alpha: Image.Image) -> bool:
    import numpy as np

    a = np.asarray(alpha, dtype=np.uint8)
    ys, xs = np.nonzero(a >= 90)
    if len(xs) < 50:
        return False
    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    aspect = max(bw / max(1, bh), bh / max(1, bw))
    occupancy = float((a >= 90).sum()) / float(max(1, bw * bh))
    return aspect >= 2.35 and occupancy <= 0.68


def remove_border_connected_backdrop(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Keep the successful rug cleanup, but never apply it to long bumper-like parts."""
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

    bg_like = (distance <= 5.8) | ((lum >= 185) & (chroma <= 48))
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
    exterior = ndimage.binary_dilation(exterior, structure=np.ones((3, 3)), iterations=1)
    remove = exterior & ((distance <= 6.4) | ((lum >= 178) & (chroma <= 58)))
    a[remove] = 0
    return Image.fromarray(a, mode="L")


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
    raw_alpha = remove_border_connected_backdrop(img, raw_alpha)

    if auto_settings:
        cleanup = recommendations["cleanup"]
        edge_expand = recommendations["edge_expand"]

    cleaned_alpha = app.clean_alpha_mask(raw_alpha, cleanup, edge_expand)
    cleaned_alpha = app.suppress_old_background(cleaned_alpha, strict=strict_logo_cleanup)
    result.putalpha(cleaned_alpha)
    result = app.remove_isolated_artifacts(result, strength=cleanup)

    if prevent_background_showthrough:
        opacity_floor = recommendations["opacity_floor"] if auto_settings else 128
        result.putalpha(app.harden_alpha(result.getchannel("A"), opacity_floor))

    return result, recommendations


def install():
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD
    app.get_rembg_session = get_rembg_session
    app.remove_background = remove_background


install()
