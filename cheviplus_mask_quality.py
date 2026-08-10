"""Mask-quality improvements for Cheviplus Photo Studio 4.2.

Targets two real-world failure modes seen in production photos:
1) chrome / glossy surfaces incorrectly becoming transparent because rembg
   interprets reflections of the old backdrop as background;
2) large pieces of the old light backdrop being kept as part of the product.

The patch is intentionally conservative and is applied on top of the existing
stability layer. It does not enable product-logo removal or aggressive cleanup.
"""

from __future__ import annotations

from PIL import Image

import app


APP_VERSION = "4.2"
APP_BUILD = "2026.08.10.01"


def _border_statistics(rgb):
    import numpy as np

    h, w, _ = rgb.shape
    b = max(6, int(min(h, w) * 0.045))
    border = np.concatenate(
        [
            rgb[:b].reshape(-1, 3),
            rgb[-b:].reshape(-1, 3),
            rgb[:, :b].reshape(-1, 3),
            rgb[:, -b:].reshape(-1, 3),
        ],
        axis=0,
    )
    median = np.median(border, axis=0)
    mad = np.median(np.abs(border - median), axis=0)
    return median.astype(np.float32), np.maximum(mad, 6.0).astype(np.float32)


def remove_border_connected_backdrop(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Remove old light backdrop only when it is connected to the image border.

    This targets large rectangular leftovers such as backdrop paper behind a floor
    mat. It deliberately avoids deleting isolated light areas inside the product.
    """

    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8).copy()
    h, w, _ = rgb.shape

    bg, mad = _border_statistics(rgb)
    scaled = (rgb - bg[None, None, :]) / mad[None, None, :]
    distance = np.sqrt(np.sum(scaled * scaled, axis=2))

    # Backdrops in the current workflow are normally pale/near-white. The adaptive
    # distance keeps this useful on slightly grey photographed backgrounds as well.
    lum = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    bg_like = (distance <= 5.8) | ((lum >= 185) & (chroma <= 48))
    bg_like = ndimage.binary_closing(bg_like, structure=np.ones((5, 5)), iterations=1)

    labels, count = ndimage.label(bg_like)
    if not count:
        return alpha

    border_ids = set()
    border_ids.update(np.unique(labels[0, :]).tolist())
    border_ids.update(np.unique(labels[-1, :]).tolist())
    border_ids.update(np.unique(labels[:, 0]).tolist())
    border_ids.update(np.unique(labels[:, -1]).tolist())
    border_ids.discard(0)
    if not border_ids:
        return alpha

    exterior = np.isin(labels, list(border_ids))
    exterior = ndimage.binary_dilation(exterior, structure=np.ones((3, 3)), iterations=1)

    # Do not punch through confident dark/coloured product pixels. This primarily
    # removes pale old-backdrop regions and lets later component cleanup discard
    # small logo islands that become detached.
    very_bg_like = exterior & ((distance <= 6.4) | ((lum >= 178) & (chroma <= 58)))
    a[very_bg_like] = 0
    return Image.fromarray(a, mode="L")


def recover_reflective_chrome(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Recover enclosed reflective regions that rembg mistook for holes.

    A real hole usually shows the actual studio backdrop and therefore resembles the
    sampled image border. Chrome reflects the environment but is typically darker,
    higher-contrast, or more chromatic than the direct backdrop. We only restore
    enclosed candidates inside a strong product silhouette and reject candidates
    whose appearance is too similar to the real backdrop.
    """

    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8).copy()
    h, w = a.shape

    strong = a >= 150
    if strong.sum() < 250:
        return alpha

    # Build a conservative local silhouette. Closing bridges reflective gaps without
    # flattening large concavities of the part.
    radius = max(2, min(9, int(min(h, w) * 0.012)))
    structure = np.ones((3, 3), dtype=bool)
    envelope = ndimage.binary_closing(strong, structure=structure, iterations=radius)
    envelope = ndimage.binary_fill_holes(envelope)

    weak = a < 115
    candidates = envelope & weak
    labels, count = ndimage.label(candidates)
    if not count:
        return alpha

    bg, mad = _border_statistics(rgb)
    scaled = (rgb - bg[None, None, :]) / mad[None, None, :]
    bg_distance = np.sqrt(np.sum(scaled * scaled, axis=2))
    luminance = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    # Local gradient helps identify reflective detail/metal texture.
    gray = luminance
    gx = ndimage.sobel(gray, axis=1)
    gy = ndimage.sobel(gray, axis=0)
    gradient = np.hypot(gx, gy)

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    max_area = max(120, int(envelope.sum() * 0.18))
    min_area = max(18, int(envelope.sum() * 0.00045))

    recover = np.zeros_like(candidates, dtype=bool)
    for idx in range(1, count + 1):
        size = int(sizes[idx])
        if size < min_area or size > max_area:
            continue
        component = labels == idx
        ys, xs = np.nonzero(component)
        if not len(xs):
            continue

        # Candidate must be genuinely internal to the product silhouette.
        if xs.min() <= 1 or ys.min() <= 1 or xs.max() >= w - 2 or ys.max() >= h - 2:
            continue

        mean_bg_distance = float(np.median(bg_distance[component]))
        mean_gradient = float(np.mean(gradient[component]))
        mean_lum = float(np.mean(luminance[component]))
        mean_chroma = float(np.mean(chroma[component]))

        ring = ndimage.binary_dilation(component, iterations=2) & ~component
        ring_object_fraction = float(strong[ring].mean()) if ring.any() else 0.0

        # Direct backdrop-like holes are intentionally left transparent. Reflective
        # metal is restored only with strong contextual support from surrounding part.
        visually_not_backdrop = (
            mean_bg_distance >= 7.2
            or mean_lum <= float(bg.mean()) - 28.0
            or mean_chroma >= 54.0
        )
        reflective_detail = mean_gradient >= 8.0 or mean_chroma >= 42.0
        if ring_object_fraction >= 0.42 and visually_not_backdrop and reflective_detail:
            recover |= component

    if not recover.any():
        return alpha

    # Restore a solid interior and retain a narrow transition around the recovered
    # region so chrome edges do not look pasted in.
    inner = ndimage.binary_erosion(recover, iterations=1)
    edge = recover & ~inner
    a[inner] = 255
    a[edge] = np.maximum(a[edge], 205)
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
        session=app.get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")

    raw_alpha = result.getchannel("A")
    recommendations = app.analyze_object_shape(raw_alpha)

    # Stage 1: remove large border-connected old backdrop regions before normal
    # alpha cleanup. Stage 2: recover chrome that rembg interpreted as background.
    raw_alpha = remove_border_connected_backdrop(img, raw_alpha)
    raw_alpha = recover_reflective_chrome(img, raw_alpha)

    if auto_settings:
        cleanup = recommendations["cleanup"]
        edge_expand = recommendations["edge_expand"]

    cleaned_alpha = app.clean_alpha_mask(raw_alpha, cleanup, edge_expand)
    cleaned_alpha = app.suppress_old_background(
        cleaned_alpha,
        strict=strict_logo_cleanup,
    )
    result.putalpha(cleaned_alpha)
    result = app.remove_isolated_artifacts(result, strength=cleanup)

    if prevent_background_showthrough:
        opacity_floor = recommendations["opacity_floor"] if auto_settings else 128
        result.putalpha(app.harden_alpha(result.getchannel("A"), opacity_floor))

    return result, recommendations


def install():
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD
    app.remove_background = remove_background


install()
