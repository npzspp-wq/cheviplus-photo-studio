"""Cheviplus Photo Studio 4.8: product-preserving segmentation for large kits.

Real product photos can contain several overlapping floor mats occupying most of the
frame. In that situation an edge-connected colour cleanup is unsafe: the product itself
touches the image edge and can resemble the pale studio backdrop. 4.8 therefore treats
AI segmentation as the authority for product geometry and uses colour only on pixels
that BOTH segmentation passes already consider weak background.
"""

from __future__ import annotations

from PIL import Image

import app
import cheviplus_product_cutout as pc

APP_VERSION = "4.8"
APP_BUILD = "2026.08.10.01"


def _product_preserving_merge(alpha_original, alpha_enhanced):
    """Merge two masks without deleting real pieces from a large/overlapping kit."""
    import numpy as np
    from scipy import ndimage

    a1 = np.asarray(alpha_original, dtype=np.uint8)
    a2 = np.asarray(alpha_enhanced, dtype=np.uint8)
    hi = np.maximum(a1, a2)
    lo = np.minimum(a1, a2)

    # One confident pass is enough to keep a possible product pixel. This is crucial
    # for beige/grey mats, chrome and narrow disconnected pieces.
    keep = hi >= 72

    # Recover weak bridges between overlapping parts, but only next to already strong
    # foreground. This avoids breaking a set into several missing pieces.
    strong = hi >= 150
    near_strong = ndimage.binary_dilation(strong, iterations=3)
    keep |= near_strong & (hi >= 34)

    merged = hi.copy()
    merged[~keep] = 0

    # Where both passes agree, trust the agreement and make product interiors opaque.
    agreed = lo >= 96
    merged[agreed] = 255
    return merged.astype(np.uint8)


def _safe_background_cleanup(original: Image.Image, alpha_array):
    """Clean only AI-weak background; never infer product deletion from colour alone."""
    import numpy as np
    from scipy import ndimage

    a = alpha_array.copy()
    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    b = max(5, int(min(h, w) * 0.025))
    border = np.concatenate([
        rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
        rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)
    ])
    bg = np.median(border, axis=0)
    mad = np.maximum(np.median(np.abs(border - bg), axis=0), 9.0)
    distance = np.sqrt(np.sum(((rgb - bg) / mad) ** 2, axis=2))

    # Critical safety rule: colour similarity may erase ONLY pixels whose merged AI
    # confidence is already very low. A mat touching the frame cannot be removed just
    # because its colour resembles the backdrop.
    candidate = (distance <= 4.2) & (a < 58)
    labels, count = ndimage.label(candidate)
    if count:
        ids = set(np.unique(labels[0]).tolist()) | set(np.unique(labels[-1]).tolist())
        ids |= set(np.unique(labels[:, 0]).tolist()) | set(np.unique(labels[:, -1]).tolist())
        ids.discard(0)
        if ids:
            a[np.isin(labels, list(ids))] = 0

    a[a < 20] = 0
    return a


def build_product_mask(original: Image.Image) -> Image.Image:
    import numpy as np

    alpha_original = np.asarray(pc._segment_alpha(original), dtype=np.uint8)
    alpha_enhanced = np.asarray(pc._segment_alpha(pc._enhanced_model_input(original)), dtype=np.uint8)

    combined = _product_preserving_merge(alpha_original, alpha_enhanced)
    combined = _safe_background_cleanup(original, combined)

    # Do NOT use 4.6 edge-connected backdrop deletion here: real floor mats frequently
    # touch the frame. Keep every meaningful disconnected component of the kit.
    support = pc._meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)
    combined = pc._solidify_product_interior(combined)

    # Paper removal remains conservative: overlapping instruction sheets are retained
    # because the hidden product pixels cannot be reconstructed from a single photo.
    combined = pc._remove_detached_paper_components(original, combined)
    return Image.fromarray(combined, mode="L")


def extract_product(original: Image.Image):
    rgba = original.convert("RGBA")
    rgba.putalpha(build_product_mask(original))
    return rgba


def remove_background(img: Image.Image, cleanup=45, edge_expand=1, auto_settings=True,
                      prevent_background_showthrough=True, strict_logo_cleanup=True):
    cutout = extract_product(img)
    recommendations = app.analyze_object_shape(cutout.getchannel("A"))
    return cutout, recommendations


class BackdropQualityApp(pc.ProductCutoutApp):
    pass


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
