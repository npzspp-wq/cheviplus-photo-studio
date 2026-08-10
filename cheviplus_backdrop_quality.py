"""Cheviplus Photo Studio 4.7: improve old-backdrop removal without sacrificing product parts.

This layer builds on the 4.6 product-first cutout. The main change is that the two
u2netp passes are no longer collapsed immediately with a simple maximum. Pixels that
look like the photographed backdrop and are connected to the outer frame can now be
removed even when one pass falsely calls them foreground, while pixels supported by
both model passes are protected.
"""

from __future__ import annotations

from PIL import Image

import app
import cheviplus_product_cutout as pc

APP_VERSION = "4.7"
APP_BUILD = "2026.08.10.01"


def _agreement_backdrop_cleanup(original: Image.Image, alpha_original, alpha_enhanced):
    """Remove edge-connected photographed backdrop using two-pass agreement.

    Product preservation rules:
    - strong agreement from both segmentation passes is never erased;
    - only regions visually compatible with the sampled frame background are eligible;
    - eligibility must be connected to an outer image edge;
    - textured/contrasty regions receive additional protection.
    """
    import numpy as np
    from scipy import ndimage

    a1 = np.asarray(alpha_original, dtype=np.uint8)
    a2 = np.asarray(alpha_enhanced, dtype=np.uint8)
    combined = np.maximum(a1, a2).astype(np.uint8)
    agreement = np.minimum(a1, a2).astype(np.uint8)

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

    gx = ndimage.sobel(lum, axis=1)
    gy = ndimage.sobel(lum, axis=0)
    gradient = np.hypot(gx, gy)

    # Candidate background is intentionally broad, but still must be connected to
    # the border before it can be removed.
    bg_like = (distance <= 5.4) | ((lum >= 188) & (chroma <= 46))
    bg_like = ndimage.binary_closing(
        bg_like,
        structure=np.ones((3, 3), dtype=bool),
        iterations=1,
        border_value=1,
    )
    labels, count = ndimage.label(bg_like)
    if not count:
        return combined

    border_ids = set(np.unique(labels[0, :]).tolist())
    border_ids.update(np.unique(labels[-1, :]).tolist())
    border_ids.update(np.unique(labels[:, 0]).tolist())
    border_ids.update(np.unique(labels[:, -1]).tolist())
    border_ids.discard(0)
    if not border_ids:
        return combined

    exterior = np.isin(labels, list(border_ids))

    # Both passes agreeing strongly is the most important product-preservation guard.
    strongly_agreed_product = agreement >= 158

    # If only one pass sees foreground, allow removal when the region is visually
    # smooth/background-like. This targets the large rectangular old-backdrop residue
    # seen in real carpet photos.
    weak_disagreement = agreement < 118
    smooth = gradient < 32.0
    obvious_low_confidence = combined < 148

    erase = exterior & ~strongly_agreed_product & (
        obvious_low_confidence | (weak_disagreement & smooth)
    )

    cleaned = combined.copy()
    cleaned[erase] = 0

    # Feather only the outer transition of removed backdrop. Never blur/fill holes.
    removed_edge = ndimage.binary_dilation(erase, iterations=1) & ~erase
    soft = removed_edge & (cleaned < 120) & ~strongly_agreed_product
    cleaned[soft] = np.minimum(cleaned[soft], 72)
    return cleaned


def build_product_mask(original: Image.Image) -> Image.Image:
    """Create a 4.7 product mask with agreement-aware backdrop cleanup."""
    import numpy as np

    alpha_original = np.asarray(pc._segment_alpha(original), dtype=np.uint8)
    alpha_enhanced = np.asarray(
        pc._segment_alpha(pc._enhanced_model_input(original)), dtype=np.uint8
    )

    combined = _agreement_backdrop_cleanup(original, alpha_original, alpha_enhanced)
    support = pc._meaningful_component_mask(combined)
    combined = np.where(support, combined, 0).astype(np.uint8)

    # Keep the conservative 4.6 cleanup as a second pass for genuinely weak residue.
    combined = pc._remove_edge_connected_backdrop(original, combined)
    combined = pc._solidify_product_interior(combined)
    combined = pc._remove_detached_paper_components(original, combined)
    return Image.fromarray(combined, mode="L")


def extract_product(original: Image.Image):
    rgba = original.convert("RGBA")
    rgba.putalpha(build_product_mask(original))
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


class BackdropQualityApp(pc.ProductCutoutApp):
    pass


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
app.remove_background = remove_background
