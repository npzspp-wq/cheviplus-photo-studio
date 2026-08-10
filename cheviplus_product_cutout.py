"""Cheviplus Photo Studio 4.6 test: extract product first, then composite.

Pipeline:
1) segment product twice (original + contrast-normalized copy),
2) combine masks to preserve light/chrome details and disconnected kit pieces,
3) remove only low-confidence pale backdrop connected to the photo edge,
4) make confident product interiors fully opaque while keeping a soft outer edge,
5) remove only *detached* paper-like instruction sheets when they are safe to drop,
6) apply the final mask to untouched original pixels,
7) let the existing compositor place that transparent cutout on the selected background.

The key rule is product preservation first. We never globally fill holes and never erase
an overlapping instruction sheet if doing so would punch a rectangular hole through the
product underneath it.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageOps

import app
from cheviplus_stability_patch import StableApp

APP_VERSION = "4.6"
APP_BUILD = "2026.08.10.02"


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
    erase = exterior & (alpha_array < 150)
    cleaned = alpha_array.copy()
    cleaned[erase] = 0
    return cleaned


def _solidify_product_interior(alpha_array):
    """Stop replacement background from showing through a detected product.

    Confident and medium-confidence foreground becomes opaque. Only the narrow weak
    transition band remains soft. This is deliberately different from filling holes:
    zero/near-zero openings stay zero, so true bumper holes remain transparent.
    """
    import numpy as np
    from scipy import ndimage

    a = alpha_array.astype(np.uint8, copy=True)
    core = a >= 52
    # Close only one-pixel speckle gaps inside already detected material.
    core = ndimage.binary_closing(core, structure=np.ones((3, 3), dtype=bool), iterations=1)
    a[core] = 255

    edge = (a >= 18) & ~core
    # Raise weak edge opacity without converting true background to product.
    if edge.any():
        boosted = np.clip(a[edge].astype(np.int16) * 2 + 28, 0, 210).astype(np.uint8)
        a[edge] = np.maximum(a[edge], boosted)
    a[a < 18] = 0
    return a


def _remove_detached_paper_components(original: Image.Image, alpha_array):
    """Drop only paper-like foreground components that are detached from the product.

    If a sheet overlaps a mat/part, it shares the same foreground component. We keep
    it rather than create a fake transparent rectangle where the hidden product cannot
    be reconstructed from the source photo.
    """
    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = alpha_array.copy()
    foreground = a >= 120
    labels, count = ndimage.label(foreground)
    if count <= 1:
        return a

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = max(1, int(sizes.max()))
    image_area = foreground.size
    luminance = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    for idx in range(1, count + 1):
        component = labels == idx
        size = int(sizes[idx])
        if size <= 0 or size >= largest * 0.45:
            continue
        ys, xs = np.nonzero(component)
        if not len(xs):
            continue
        bw = int(xs.max() - xs.min() + 1)
        bh = int(ys.max() - ys.min() + 1)
        bbox_area = max(1, bw * bh)
        fill = size / bbox_area
        aspect = bw / max(1, bh)
        area_fraction = size / image_area
        pale_fraction = float(((luminance[component] >= 178) & (chroma[component] <= 52)).mean())

        paper_like = (
            0.0007 <= area_fraction <= 0.045
            and 0.48 <= aspect <= 2.8
            and fill >= 0.42
            and pale_fraction >= 0.56
        )
        if paper_like:
            a[component] = 0
    return a


def build_product_mask(original: Image.Image) -> Image.Image:
    """Return a product-first alpha mask from two lightweight segmentation passes."""
    import numpy as np

    alpha_original = np.asarray(_segment_alpha(original), dtype=np.uint8)
    alpha_enhanced = np.asarray(_segment_alpha(_enhanced_model_input(original)), dtype=np.uint8)

    combined = np.maximum(alpha_original, alpha_enhanced)
    support = _meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)
    combined = _remove_edge_connected_backdrop(original, combined)
    combined = _solidify_product_interior(combined)
    combined = _remove_detached_paper_components(original, combined)
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


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
