"""Clipboard usability for marketplace article search."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import app

APP_VERSION = "5.20"
APP_BUILD = "2026.08.24.08"
_ORIGINAL_BUILD = app.App._build


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _paste_from_clipboard(entry):
    try:
        text = entry.clipboard_get()
    except Exception:
        return "break"
    try:
        entry.delete("sel.first", "sel.last")
    except Exception:
        pass
    entry.insert("insert", text)
    return "break"


def _show_menu(entry, event):
    menu = tk.Menu(entry, tearoff=0)
    menu.add_command(label="Вставить", command=lambda: _paste_from_clipboard(entry))
    menu.add_command(label="Копировать", command=lambda: entry.event_generate("<<Copy>>"))
    menu.add_command(label="Вырезать", command=lambda: entry.event_generate("<<Cut>>"))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def build_with_clipboard(self):
    _ORIGINAL_BUILD(self)
    target_var = getattr(self, "marketplace_article_var", None)
    if target_var is None:
        return
    target_name = str(target_var)
    for widget in _walk(self):
        if isinstance(widget, ttk.Entry):
            try:
                if str(widget.cget("textvariable")) != target_name:
                    continue
            except Exception:
                continue
            widget.bind("<Control-v>", lambda _e, w=widget: _paste_from_clipboard(w))
            widget.bind("<Control-V>", lambda _e, w=widget: _paste_from_clipboard(w))
            widget.bind("<Shift-Insert>", lambda _e, w=widget: _paste_from_clipboard(w))
            widget.bind("<Button-3>", lambda e, w=widget: _show_menu(w, e))
            break


app.App._build = build_with_clipboard
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
