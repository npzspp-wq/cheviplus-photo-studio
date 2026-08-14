"""Adaptive product scale for the 1280x960 reference profile.

The reference photo set uses generous margins for compact/ring-like parts, while long
trim pieces, bumpers and rails should use substantially more horizontal space. This
module derives scale from the actual segmented mask, not from filename/product type.
"""
from __future__ import annotations

import numpy as np
import app

REFERENCE_PROFILE_PREFIX = "1С — эталон 1280×960"
_ORIGINAL_ANALYZE = app.analyze_object_shape


def _mask_geometry(alpha):
    arr = np.asarray(alpha, dtype=np.uint8)
    ys, xs = np.nonzero(arr > 32)
    if len(xs) < 40:
        return None
    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    bbox_area = max(1, w * h)
    crop = arr[ys.min():ys.max()+1, xs.min():xs.max()+1]
    solid = float(np.count_nonzero(crop > 96)) / bbox_area
    aspect = w / max(1.0, float(h))
    return w, h, aspect, solid


def adaptive_reference_fill(alpha):
    """Return target max-frame fill based on segmented product geometry."""
    geo = _mask_geometry(alpha)
    if not geo:
        return 0.58
    _, _, aspect, solid = geo

    # Open/ring-like mouldings: match the supplied wheel-arch trim references.
    if 0.72 <= aspect <= 1.45 and solid < 0.34:
        return 0.55

    # Long mouldings, rails, bumpers and hoses should use the available width.
    if aspect >= 3.4:
        return 0.90
    if aspect >= 2.5:
        return 0.86
    if aspect >= 1.9:
        return 0.80
    if aspect >= 1.45:
        return 0.72

    # Tall/narrow items such as filters, boxes and lamps.
    if aspect <= 0.42:
        return 0.72
    if aspect <= 0.62:
        return 0.66

    # Compact/square objects retain generous margins.
    if solid > 0.72:
        return 0.60
    return 0.58


def analyze_object_shape_reference(alpha):
    info = dict(_ORIGINAL_ANALYZE(alpha))
    info["fill"] = adaptive_reference_fill(alpha)
    info["adaptive_reference_scale"] = True
    return info


def enable_reference_autoscale_for_class(cls):
    original = cls.current_options
    if getattr(original, "_cheviplus_reference_autoscale", False):
        return

    def wrapped(self):
        options = original(self)
        try:
            is_reference = str(self.profile_var.get()).startswith(REFERENCE_PROFILE_PREFIX)
        except Exception:
            is_reference = False
        if is_reference:
            options["auto_settings"] = True
        return options

    wrapped._cheviplus_reference_autoscale = True
    cls.current_options = wrapped


def install():
    app.analyze_object_shape = analyze_object_shape_reference
    enable_reference_autoscale_for_class(app.App)
    try:
        import cheviplus_ai_quality as aq
        enable_reference_autoscale_for_class(aq.AIQualityApp)
    except Exception:
        pass


install()
