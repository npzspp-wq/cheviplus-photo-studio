"""Automatic product category detection and marketplace template selection."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

import app
import cheviplus_marketplace_catalog as catalog
import cheviplus_marketplace_cards as cards

APP_VERSION = "5.23"
APP_BUILD = "2026.08.24.11"
_ORIGINAL_BUILD = app.App._build
_ORIGINAL_LOOKUP_METHOD = app.App._marketplace_lookup
_ORIGINAL_CREATE = app.App._marketplace_create_ozon_cards

CATEGORY_RULES = [
    ("Ковры", ["ковер", "ковёр", "ковры", "коврик", "коврики", "eva"]),
    ("Защиты", ["защита картера", "защита двс", "защита двигателя", "защита кпп", "защита бака", "защита радиатора", "защита раздат"]),
    ("Фильтры", ["фильтр масля", "фильтр воздуш", "фильтр салон", "фильтр топлив"]),
    ("Тормоза", ["колодк", "диск тормоз", "суппорт", "brembo", "тормозн"]),
    ("Брызговики", ["брызговик"]),
    ("Дефлекторы", ["дефлектор"]),
    ("Подножки / пороги", ["подножк", "порог", "running board"]),
    ("Лифт подвески", ["лифт", "lift", "проставк подвес", "chevilift"]),
    ("Оптика", ["фара", "фонарь", "led фонар", "ламп", "противотуман"]),
    ("Электроника", ["камера", "carplay", "android", "монитор", "видеорегистратор", "регистратор"]),
    ("Эмблемы / декор", ["эмблем", "шильдик", "накладк", "молдинг"]),
    ("Багажные системы", ["багажник", "рейлинг", "поперечин", "thule", "бокс"]),
    ("Автохимия", ["масло", "антифриз", "жидкость", "очиститель", "смазка"]),
]

TEMPLATE_BY_CATEGORY = {
    "Ковры": "Шаблон A — крупный плоский товар",
    "Защиты": "Шаблон A — крупный плоский товар",
    "Фильтры": "Шаблон B — компактный расходник",
    "Тормоза": "Шаблон C — технический / premium",
    "Брызговики": "Шаблон D — комплект",
    "Дефлекторы": "Шаблон E — длинный товар",
    "Подножки / пороги": "Шаблон E — длинный товар",
    "Лифт подвески": "Шаблон D — комплект",
    "Оптика": "Шаблон C — технический / premium",
    "Электроника": "Шаблон F — электроника",
    "Эмблемы / декор": "Шаблон C — premium аксессуар",
    "Багажные системы": "Шаблон E — длинный / объёмный товар",
    "Автохимия": "Шаблон B — расходный материал",
    "Прочее": "Шаблон U — универсальный",
}


def detect_category(product: dict) -> str:
    text = " ".join([
        str(product.get("name") or ""),
        " ".join(product.get("applicability") or []),
    ]).lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    for category, needles in CATEGORY_RULES:
        if any(n.replace("ё", "е") in text for n in needles):
            return category
    return "Прочее"


def template_for(product: dict) -> str:
    category = product.get("marketplace_category") or detect_category(product)
    return TEMPLATE_BY_CATEGORY.get(category, TEMPLATE_BY_CATEGORY["Прочее"])


def apply_category(product: dict) -> dict:
    result = dict(product)
    result["marketplace_category"] = detect_category(result)
    result["marketplace_template"] = template_for(result)
    return result


def lookup_with_category(self):
    _ORIGINAL_LOOKUP_METHOD(self)
    product = getattr(self, "marketplace_selected_product", None)
    if product:
        product = apply_category(product)
        self.marketplace_selected_product = product
        if hasattr(self, "marketplace_category_var"):
            self.marketplace_category_var.set(product["marketplace_category"])
        if hasattr(self, "marketplace_template_var"):
            self.marketplace_template_var.set(product["marketplace_template"])


def build_template_ui(self):
    _ORIGINAL_BUILD(self)
    self.marketplace_category_var = tk.StringVar(value="—")
    self.marketplace_template_var = tk.StringVar(value="—")
    box = None
    for child in self.winfo_children():
        stack = [child]
        while stack:
            w = stack.pop()
            try:
                if isinstance(w, ttk.LabelFrame) and "Маркетплейсы" in w.cget("text"):
                    box = w; stack.clear(); break
            except Exception:
                pass
            try: stack.extend(w.winfo_children())
            except Exception: pass
        if box is not None: break
    if box is None: return
    row = ttk.Frame(box)
    row.pack(fill="x", pady=(8, 0))
    ttk.Label(row, text="Категория:").pack(side="left")
    ttk.Label(row, textvariable=self.marketplace_category_var).pack(side="left", padx=(6, 18))
    ttk.Label(row, text="Шаблон:").pack(side="left")
    ttk.Label(row, textvariable=self.marketplace_template_var).pack(side="left", padx=6)


def create_with_category(self):
    product = getattr(self, "marketplace_selected_product", None)
    if product:
        product = apply_category(product)
        self.marketplace_selected_product = product
    return _ORIGINAL_CREATE(self)


# Make classifier available to card generator and editor.
cards.detect_marketplace_category = detect_category
cards.marketplace_template_for = template_for
app.App._build = build_template_ui
app.App._marketplace_lookup = lookup_with_category
app.App._marketplace_create_ozon_cards = create_with_category
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
catalog.APP_VERSION = APP_VERSION
catalog.APP_BUILD = APP_BUILD
cards.APP_VERSION = APP_VERSION
cards.APP_BUILD = APP_BUILD
