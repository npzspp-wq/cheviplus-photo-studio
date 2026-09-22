"""Cheviplus Photo Studio 5.31 workspace cleanup.

Splits the crowded operator UI into two simple workspaces without rewriting any
existing processing or marketplace logic:
- Фото для 1С: photo processing, background, scale, plexiglass, source/actions.
- Маркетплейсы: catalog lookup and marketplace card workflow only.

A separate service toggle exposes administrator/statistics/manual technical
blocks when they are actually needed.

Also installs a final compose router so the plexiglass checkbox works on normal
backgrounds and the dedicated acrylic-table background keeps its refined table
placement/reflection renderer.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import app
import cheviplus_plexiglass as plexi
import cheviplus_table_placement_patch as table_patch
import cheviplus_marketplace_text_layout as text_layout

APP_VERSION = "5.31"
APP_BUILD = "2026.08.25.05"

_ORIGINAL_BUILD = app.App._build

_SERVICE_HINTS = (
    "статистика рабочего места",
    "лицензия рабочего места",
    "администрирование рабочего места",
    "стабильная ручная обработка",
    "журнал",
)
_MARKET_HINTS = ("маркетплейс", "ozon")


def _walk(root):
    yield root
    for child in root.winfo_children():
        yield from _walk(child)


def _widget_text(widget):
    try:
        return str(widget.cget("text") or "").strip()
    except Exception:
        return ""


def _contains_hint(widget, hints):
    for node in _walk(widget):
        text = _widget_text(node).lower()
        if text and any(h in text for h in hints):
            return True
    return False


def _find_market_widget(root):
    """Return the marketplace LabelFrame introduced by the catalog patch."""
    for node in _walk(root):
        try:
            if isinstance(node, ttk.LabelFrame):
                text = _widget_text(node).lower()
                if "маркетплейс" in text:
                    return node
        except Exception:
            pass
    return None


def _top_child(widget, ancestor):
    current = widget
    while current is not None and current.master is not ancestor:
        current = current.master
    return current


def _clean_pack_info(widget):
    try:
        info = dict(widget.pack_info())
    except Exception:
        return {}
    info.pop("in", None)
    return info


def _restore_packed(widget, info):
    if not widget.winfo_exists():
        return
    try:
        widget.pack(**info)
    except Exception:
        try:
            widget.pack(fill="x", pady=(6, 0))
        except Exception:
            pass


def _apply_workspace(self):
    left = getattr(self, "_workspace_left", None)
    modebar = getattr(self, "_workspace_modebar", None)
    entries = getattr(self, "_workspace_entries", [])
    market_top = getattr(self, "_workspace_market_top", None)
    if left is None or modebar is None:
        return

    mode = self.workspace_mode.get()
    show_service = bool(self.workspace_service.get())

    # Repack in the exact original order; this prevents layout drift after
    # repeatedly switching modes.
    for widget, _info, _is_market, _is_service in entries:
        try:
            widget.pack_forget()
        except Exception:
            pass

    for widget, info, is_market, is_service in entries:
        if mode == "marketplace":
            visible = is_market
        else:
            visible = (not is_market) and (show_service or not is_service)
        if visible:
            _restore_packed(widget, info)

    # Keep the selector above all content.
    try:
        modebar.pack_forget()
        first_visible = next((w for w, _i, _m, _s in entries if w.winfo_manager() == "pack"), None)
        if first_visible is not None:
            modebar.pack(fill="x", pady=(0, 10), before=first_visible)
        else:
            modebar.pack(fill="x", pady=(0, 10))
    except Exception:
        pass

    if mode == "marketplace":
        self.status.set("Режим: карточки маркетплейсов")
    else:
        self.status.set("Режим: фото для 1С")


def build_workspaces(self):
    _ORIGINAL_BUILD(self)
    market = _find_market_widget(self)
    if market is None:
        return

    # Marketplace and original photo controls are inserted into the same scroll
    # content frame. Work only with that frame's direct packed children.
    left = market.master
    market_top = _top_child(market, left) or market
    children = [w for w in left.winfo_children() if w.winfo_manager() == "pack"]

    self.workspace_mode = tk.StringVar(master=self, value="1c")
    self.workspace_service = tk.BooleanVar(master=self, value=False)

    modebar = ttk.LabelFrame(left, text="Рабочий режим", padding=10)
    top = ttk.Frame(modebar)
    top.pack(fill="x")
    ttk.Radiobutton(
        top,
        text="1. ФОТО ДЛЯ 1С",
        value="1c",
        variable=self.workspace_mode,
        command=lambda: _apply_workspace(self),
    ).pack(side="left", padx=(0, 18))
    ttk.Radiobutton(
        top,
        text="2. МАРКЕТПЛЕЙСЫ",
        value="marketplace",
        variable=self.workspace_mode,
        command=lambda: _apply_workspace(self),
    ).pack(side="left")
    ttk.Checkbutton(
        top,
        text="Показать служебные настройки",
        variable=self.workspace_service,
        command=lambda: _apply_workspace(self),
    ).pack(side="right")
    ttk.Label(
        modebar,
        text="1С: обработка фото и оргстекло  •  Маркетплейсы: база товара и создание карточек",
    ).pack(anchor="w", pady=(6, 0))

    entries = []
    for widget in children:
        info = _clean_pack_info(widget)
        is_market = widget is market_top or _contains_hint(widget, _MARKET_HINTS)
        is_service = _contains_hint(widget, _SERVICE_HINTS)
        entries.append((widget, info, is_market, is_service))

    self._workspace_left = left
    self._workspace_market_top = market_top
    self._workspace_entries = entries
    self._workspace_modebar = modebar
    _apply_workspace(self)


# Final, explicit plexiglass router. Later marketplace/UI modules must not be
# able to bypass the effect chain.
def compose_with_restored_plexiglass(source, *args, **kwargs):
    options = plexi._extract_options(args, kwargs)
    background_path = options.get("background_path")
    intensity = int(kwargs.get("plexiglass_intensity", plexi.DEFAULT_INTENSITY))
    if intensity < plexi.MIN_ENABLED_INTENSITY:
        intensity = plexi.DEFAULT_INTENSITY

    if background_path and plexi._is_table_background(background_path):
        return table_patch.compose_table_scene_refined(source, options, intensity)

    forwarded = dict(kwargs)
    forwarded.pop("table_manual_position", None)
    forwarded.pop("table_vertical_offset", None)
    return plexi.compose_with_plexiglass(source, *args, **forwarded)


app.compose_image = compose_with_restored_plexiglass
app.App._build = build_workspaces
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
plexi.APP_VERSION = APP_VERSION
plexi.APP_BUILD = APP_BUILD
table_patch.APP_VERSION = APP_VERSION
table_patch.APP_BUILD = APP_BUILD
text_layout.APP_VERSION = APP_VERSION
text_layout.APP_BUILD = APP_BUILD
