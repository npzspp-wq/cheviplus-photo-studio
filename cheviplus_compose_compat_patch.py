"""Compatibility wrapper for custom table-placement options.

Prevents table-only UI options from leaking into older compose_image signatures,
while preserving them for the dedicated plexiglass-table renderer.
"""
from __future__ import annotations

import app
import cheviplus_plexiglass as plexi
import cheviplus_table_placement_patch as table_patch

APP_VERSION = "5.15"
APP_BUILD = "2026.08.18.05"

_PREVIOUS_COMPOSE = app.compose_image
_CUSTOM_KEYS = {"table_manual_position", "table_vertical_offset"}


def compose_image_compat(source, *args, **kwargs):
    options = plexi._extract_options(args, kwargs)
    background_path = options.get("background_path")

    # Dedicated acrylic-table background: use the refined renderer directly so
    # manual positioning and scale controls are consumed here, not by legacy code.
    if background_path and plexi._is_table_background(background_path):
        intensity = int(kwargs.get("plexiglass_intensity", plexi.DEFAULT_INTENSITY))
        if intensity < plexi.MIN_ENABLED_INTENSITY:
            intensity = plexi.DEFAULT_INTENSITY
        return table_patch.compose_table_scene_refined(source, options, intensity)

    # All other backgrounds go through the normal pipeline, but table-only
    # keywords must never reach legacy compose_image implementations.
    forwarded = dict(kwargs)
    for key in _CUSTOM_KEYS:
        forwarded.pop(key, None)
    return _PREVIOUS_COMPOSE(source, *args, **forwarded)


app.compose_image = compose_image_compat
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
table_patch.APP_VERSION = APP_VERSION
table_patch.APP_BUILD = APP_BUILD
plexi.APP_VERSION = APP_VERSION
plexi.APP_BUILD = APP_BUILD
