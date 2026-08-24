"""Manual editor for marketplace product data.

Edits are stored separately from the imported Excel/SQLite catalog so reloading
the source Excel does not destroy local corrections.
"""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import app
import cheviplus_marketplace_catalog as catalog

APP_VERSION = "5.22"
APP_BUILD = "2026.08.24.10"
OVERRIDES_FILE = catalog.CATALOG_DIR / "manual_overrides.json"

_ORIGINAL_BUILD = app.App._build
_ORIGINAL_LOOKUP = catalog.lookup_product


def _load_overrides() -> dict:
    try:
        if OVERRIDES_FILE.exists():
            data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_overrides(data: dict) -> None:
    catalog.CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _keys_for_product(product: dict) -> list[str]:
    keys = []
    for value in (product.get("query"), product.get("article"), product.get("code")):
        key = catalog.normalize_key(value)
        if key and key not in keys:
            keys.append(key)
    return keys


def _override_for_product(product: dict) -> dict:
    data = _load_overrides()
    for key in _keys_for_product(product):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def lookup_product_with_override(query: str):
    product = _ORIGINAL_LOOKUP(query)
    if not product:
        return None
    override = _override_for_product(product)
    if not override:
        return product
    merged = dict(product)
    for field in ("name", "article", "code", "applicability"):
        if field in override:
            merged[field] = override[field]
    merged["manual_override"] = True
    return merged


def _find_marketplace_box(root):
    for widget in root.winfo_children():
        try:
            if isinstance(widget, ttk.LabelFrame) and "Маркетплейсы" in widget.cget("text"):
                return widget
        except Exception:
            pass
        found = _find_marketplace_box(widget)
        if found is not None:
            return found
    return None


def _refresh_result(self, product: dict):
    self.marketplace_selected_product = product
    self.marketplace_result_var.set(catalog._format_result(product))
    suffix = " • исправлено вручную" if product.get("manual_override") else ""
    self.status.set(f"Товар: {product.get('article') or product.get('code') or ''}{suffix}")


def _open_editor(self):
    product = getattr(self, "marketplace_selected_product", None)
    if not product:
        messagebox.showwarning("Маркетплейсы", "Сначала найдите товар.")
        return

    win = tk.Toplevel(self)
    win.title("Редактирование данных товара")
    win.geometry("780x650")
    win.minsize(680, 560)
    win.transient(self)
    win.grab_set()

    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)

    name_var = tk.StringVar(value=product.get("name", ""))
    article_var = tk.StringVar(value=product.get("article", ""))
    code_var = tk.StringVar(value=product.get("code", ""))

    ttk.Label(frame, text="Наименование").pack(anchor="w")
    name_entry = ttk.Entry(frame, textvariable=name_var)
    name_entry.pack(fill="x", pady=(4, 10))

    ids = ttk.Frame(frame)
    ids.pack(fill="x", pady=(0, 10))
    left = ttk.Frame(ids); left.pack(side="left", fill="x", expand=True, padx=(0, 8))
    right = ttk.Frame(ids); right.pack(side="left", fill="x", expand=True)
    ttk.Label(left, text="Артикул").pack(anchor="w")
    ttk.Entry(left, textvariable=article_var).pack(fill="x", pady=(4, 0))
    ttk.Label(right, text="Код номенклатуры").pack(anchor="w")
    ttk.Entry(right, textvariable=code_var).pack(fill="x", pady=(4, 0))

    ttk.Label(frame, text="Применяемость — одна строка = один вариант").pack(anchor="w")
    text = tk.Text(frame, height=16, wrap="word")
    text.pack(fill="both", expand=True, pady=(4, 8))
    text.insert("1.0", "\n".join(product.get("applicability") or []))

    hint = ttk.Label(frame, text="Можно добавлять, удалять и исправлять строки. Исходный Excel не изменяется.")
    hint.pack(anchor="w", pady=(0, 10))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def save():
        apps = [line.strip() for line in text.get("1.0", "end").splitlines() if line.strip()]
        override = {
            "name": name_var.get().strip(),
            "article": article_var.get().strip(),
            "code": code_var.get().strip(),
            "applicability": apps,
        }
        data = _load_overrides()
        keys = _keys_for_product(product)
        new_keys = [catalog.normalize_key(override["article"]), catalog.normalize_key(override["code"])]
        all_keys = [k for k in keys + new_keys if k]
        for key in all_keys:
            data[key] = override
        _save_overrides(data)
        updated = dict(product)
        updated.update(override)
        updated["manual_override"] = True
        _refresh_result(self, updated)
        win.destroy()

    def reset_manual():
        data = _load_overrides()
        changed = False
        for key in _keys_for_product(product):
            if key in data:
                data.pop(key, None)
                changed = True
        if changed:
            _save_overrides(data)
        original = _ORIGINAL_LOOKUP(product.get("query") or product.get("article") or product.get("code") or "")
        if original:
            _refresh_result(self, original)
        win.destroy()

    ttk.Button(buttons, text="СОХРАНИТЬ", command=save).pack(side="left")
    ttk.Button(buttons, text="Сбросить ручные правки", command=reset_manual).pack(side="left", padx=8)
    ttk.Button(buttons, text="Отмена", command=win.destroy).pack(side="right")

    # Standard paste/copy shortcuts in all edit fields and applicability text.
    for widget in (name_entry, text):
        widget.bind("<Control-v>", lambda e, w=widget: w.event_generate("<<Paste>>"))


def _paste_article(self):
    try:
        value = self.clipboard_get()
    except Exception:
        messagebox.showwarning("Буфер обмена", "В буфере обмена нет текста.")
        return
    self.marketplace_article_var.set(str(value).strip())


def build_editor_ui(self):
    _ORIGINAL_BUILD(self)
    box = _find_marketplace_box(self)
    if box is None:
        return
    row = ttk.Frame(box)
    row.pack(fill="x", pady=(8, 0))
    ttk.Button(row, text="РЕДАКТИРОВАТЬ ДАННЫЕ", command=self._marketplace_edit_product).pack(side="left")
    ttk.Button(row, text="ВСТАВИТЬ НОМЕР", command=self._marketplace_paste_article).pack(side="left", padx=8)
    ttk.Label(row, text="Ручные правки сохраняются отдельно от Excel").pack(side="left", padx=8)


catalog.lookup_product = lookup_product_with_override
app.App._build = build_editor_ui
app.App._marketplace_edit_product = _open_editor
app.App._marketplace_paste_article = _paste_article
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
catalog.APP_VERSION = APP_VERSION
catalog.APP_BUILD = APP_BUILD
