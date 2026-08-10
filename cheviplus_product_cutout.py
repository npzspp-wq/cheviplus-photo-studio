"""Cheviplus Photo Studio 4.6 test: extract product first, then composite.

This patch keeps the lightweight u2netp model but changes the logic around it:
1) segment the product twice (original + contrast-normalized copy),
2) combine both masks to preserve light/chrome details and separate kit pieces,
3) remove only pale background regions that are truly connected to the photo edge,
4) apply the resulting alpha mask to the untouched original pixels,
5) let the existing compositor place that transparent cutout onto the selected brand background.

The key rule is product preservation first. We do not fill holes globally and do not
assume there is only one connected foreground object.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageOps

import app
from cheviplus_stability_patch import StableApp

APP_VERSION = "4.6"
APP_BUILD = "2026.08.10.01"


def _segment_alpha(image: Image.Image) -> Image.Image:
    from rembg import remove

    segmented = remove(
        image.convert("RGBA"),
        session=app.get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")
    return segmented.getchannel("A")


def _enhanced_model_input(image: Image.Image) -> Image.Image:
    """Make pale/chrome products easier for u2netp to see without altering export RGB."""
    rgb = image.convert("RGB")
    enhanced = ImageOps.autocontrast(rgb, cutoff=0.5)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.32)
    enhanced = ImageEnhance.Color(enhanced).enhance(1.10)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.08)
    return enhanced


def _meaningful_component_mask(alpha_array):
    import numpy as np
    from scipy import ndimage

    binary = alpha_array >= 24
    labels, count = ndimage.label(binary)
    if count <= 1:
        return binary

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = max(1, int(sizes.max()))
    h, w = binary.shape
    keep = np.zeros_like(binary, dtype=bool)

    for idx in range(1, count + 1):
        size = int(sizes[idx])
        if size <= 0:
            continue
        ys, xs = np.nonzero(labels == idx)
        if not len(xs):
            continue
        bw = int(xs.max() - xs.min() + 1)
        bh = int(ys.max() - ys.min() + 1)
        # Keep real kit pieces even when disconnected from the biggest item.
        sizeable = size >= max(45, int(largest * 0.006))
        extended = max(bw / max(1, w), bh / max(1, h)) >= 0.055 and size >= 28
        if sizeable or extended:
            keep |= labels == idx
    return keep


def _remove_edge_connected_backdrop(original: Image.Image, alpha_array):
    """Remove only low-confidence pale background connected to the image perimeter."""
    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    b = max(6, int(min(h, w) * 0.04))
    border = np.concatenate(
        [
            rgb[:b].reshape(-1, 3),
            rgb[-b:].reshape(-1, 3),
            rgb[:, :b].reshape(-1, 3),
            rgb[:, -b:].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border, axis=0)
    mad = np.maximum(np.median(np.abs(border - bg), axis=0), 7.0)
    distance = np.sqrt(np.sum(((rgb - bg) / mad) ** 2, axis=2))
    lum = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    # Candidate background must resemble the photographed backdrop.
    bg_like = (distance <= 5.0) | ((lum >= 192) & (chroma <= 38))
    bg_like = ndimage.binary_closing(
        bg_like,
        structure=np.ones((3, 3), dtype=bool),
        iterations=1,
        border_value=1,
    )
    labels, count = ndimage.label(bg_like)
    if not count:
        return alpha_array

    border_ids = set(np.unique(labels[0, :]).tolist())
    border_ids.update(np.unique(labels[-1, :]).tolist())
    border_ids.update(np.unique(labels[:, 0]).tolist())
    border_ids.update(np.unique(labels[:, -1]).tolist())
    border_ids.discard(0)
    if not border_ids:
        return alpha_array

    exterior = np.isin(labels, list(border_ids))
    # Never erase high-confidence foreground merely because it is pale. This is what
    # protects beige mats and chrome reflections.
    erase = exterior & (alpha_array < 150)
    cleaned = alpha_array.copy()
    cleaned[erase] = 0
    return cleaned


def build_product_mask(original: Image.Image) -> Image.Image:
    """Return a product-first alpha mask from two lightweight segmentation passes."""
    import numpy as np
    from scipy import ndimage

    alpha_original = np.asarray(_segment_alpha(original), dtype=np.uint8)
    alpha_enhanced = np.asarray(_segment_alpha(_enhanced_model_input(original)), dtype=np.uint8)

    # Union preserves product pixels that either view recognized. Weighted boost helps
    # weak light/chrome regions without turning every soft background pixel opaque.
    combined = np.maximum(alpha_original, alpha_enhanced)
    support = _meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)
    combined = _remove_edge_connected_backdrop(original, combined)

    # Keep natural edges; do not fill true holes. Only suppress tiny alpha noise.
    combined[combined < 10] = 0
    solid = combined >= 96
    solid = ndimage.binary_closing(solid, structure=np.ones((3, 3)), iterations=1)
    combined[solid] = np.maximum(combined[solid], 220)
    return Image.fromarray(combined, mode="L")


def extract_product(original: Image.Image):
    """Apply the product mask to untouched original pixels, producing a transparent cutout."""
    rgba = original.convert("RGBA")
    alpha = build_product_mask(original)
    rgba.putalpha(alpha)
    return rgba


def remove_background(
    img: Image.Image,
    cleanup=45,
    edge_expand=1,
    auto_settings=True,
    prevent_background_showthrough=True,
    strict_logo_cleanup=True,
):
    cutout = extract_product(img)
    recommendations = app.analyze_object_shape(cutout.getchannel("A"))
    return cutout, recommendations


class ProductCutoutApp(StableApp):
    def _build(self):
        super()._build()
        # Keep the existing stable interface. The header/version makes it clear that
        # this is the product-first test build; no extra heavy controls are required.


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
