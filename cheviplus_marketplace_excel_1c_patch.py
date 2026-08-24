"""Compatibility for the current 1C applicability Excel export headers."""

import cheviplus_marketplace_catalog as catalog
import app

APP_VERSION = "5.16"
APP_BUILD = "2026.08.24.03"

_ORIGINAL_HEADER_MAP = catalog._header_map


def header_map_1c(row):
    mapping = _ORIGINAL_HEADER_MAP(row)
    for idx, value in enumerate(row):
        key = catalog._normalize_header(value)
        if key in {"марканаименованиеполное", "марканаименование"}:
            mapping["brand"] = idx
            break
    return mapping


catalog._header_map = header_map_1c
catalog.APP_VERSION = APP_VERSION
catalog.APP_BUILD = APP_BUILD
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
