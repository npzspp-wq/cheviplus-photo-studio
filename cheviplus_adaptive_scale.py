"""Adaptive product scale for the 1280x960 reference profile.

The reference photo set uses generous margins for compact/ring-like parts, while long
trim pieces, bumpers and rails should use substantially more horizontal space.  This
module derives scale from the *actual segmented mask*, not from filename/product type.
"""
from __future__ import annotations

import numpy as np
import app

REFERENCE_PROFILE_PREFIX = "1С — эталон 1280×960"
_ORIGINAL_ANALYZE = app.analyze_object_shape
_ORIGINAL_CURRENT_OPTIONS = app.App.current_options


def _mask_geometry(alpha):
    arr = np.asarray(alpha, dtype=np.uint8)
    ys, xs = np.nonzero(arr > 32)
    if len(xs) < 40:
        return None
    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    bbox_area = max(1, w * h)
    solid = float(np.count_nonzero(arr[ys.min():ys.max()+1, xs.min():xs.max()+1] > 96)) / bbox_area
    aspect = w / max(1.0, float(h))
    return w, h, aspect, solid


def adaptive_reference_fill(alpha):
    """Return target max-frame fill based on segmented product geometry.

    Tuned against the supplied 1280x960 reference examples:
    - open/ring-like mouldings: ~55% frame
    - ordinary compact parts: 58-66%
    - medium elongated parts: 70-78%
    - very long/thin parts: 84-90%
    """
    geo = _mask_geometry(alpha)
    if not geo:
        return 0.58
    _, _, aspect, solid = geo

    # Rings / open mouldings occupy a large bounding box but contain little material.
    if 0.72 <= aspect <= 1.45 and solid < 0.34:
        return 0.55

    # Very long mouldings, rails, bumpers, hoses: maximise readable length.
    if aspect >= 3.4:
        return 0.90
    if aspect >= 2.5:
        return 0.86
    if aspect >= 1.9:
        return 0.80
    if aspect >= 1.45:
        return 0.72

    # Tall narrow objects (filters/boxes/lamps standing vertically).
    if aspect <= 0.42:
        return 0.72
    if aspect <= 0.62:
        return 0.66

    # Compact/square objects retain the generous margins seen in the reference set.
    if solid > 0.72:
        return 0.60
    return 0.58


def analyze_object_shape_reference(alpha):
    info = dict(_ORIGINAL_ANALYZE(alpha))
    info["fill"] = adaptive_reference_fill(alpha)
    info["adaptive_reference_scale"] = True
    return info


def current_options_reference(self):
    options = _ORIGINAL_CURRENT_OPTIONS(self)
    try:
        is_reference = str(self.profile_var.get()).startswith(REFERENCE_PROFILE_PREFIX)
    except Exception:
        is_reference = False
    # app.compose_image already consumes recommendations['fill'] when auto_settings=True.
    # We enable only the geometry-based scale recommendation for the reference profile;
    # cleanup controls remain explicitly set by the stable pipeline.
    if is_reference:
        options["auto_settings"] = True
    return options


def install():
    app.analyze_object_shape = analyze_object_shape_reference
    app.App.current_options = current_options_reference


install()
