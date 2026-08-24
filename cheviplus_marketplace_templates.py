"""Marketplace category detection based on the real 1C applicability assortment."""
from __future__ import annotations
import re, tkinter as tk
from tkinter import ttk
import app
import cheviplus_marketplace_catalog as catalog
import cheviplus_marketplace_cards as cards
APP_VERSION="5.25"; APP_BUILD="2026.08.24.13"; _ORIGINAL_BUILD=app.App._build; _ORIGINAL_LOOKUP_METHOD=app.App._marketplace_lookup; _ORIGINAL_CREATE=app.App._marketplace_create_ozon_cards
# Ordered from specific to broad. Rules were rebuilt after profiling 37k unique SKUs
# from the user's 1C applicability export (189k rows).
CATEGORY_RULES=[
("Ковры",["ковер","ковр","коврик","eva"]),
("Защиты",["защита картера","защита двс","защита двигателя","защита кпп","защита акпп","защита бака","защита радиатора","защита раздат","защита"]),
("Фильтры",["фильтр"]),
("Тормоза",["колод","диск торм","суппорт","тормозн","brembo","ppv"]),
("Брызговики",["брызгов"]),
("Дефлекторы",["дефлект"]),
("Подножки / пороги",["поднож","порог","running board"]),
("Фаркопы / багажные системы",["фаркоп","багажник","рейлинг","поперечин","thule","велокреп","крепление лыж","бокс багаж"]),
("Оптика",["фара","фонар","противотуман","ламп","ксенон","led"]),
("Электрика / электроника",["датчик","камера","модуль","провод","кнопк","переключ","стартер","генератор","carplay","android","монитор","регистратор"]),
("Подвеска / рулевое",["амортиз","рычаг","стойк","втулк","пружин","ступиц","шаровая","тяга рул","наконечник","лифт","lift","проставк подвес","chevilift"]),
("Двигатель / ТО",["свеч","ремень","ролик","проклад","термостат","помпа","насос","масло мотор","цепь грм","натяжител"]),
("Кузов / экстерьер",["решет","бампер","крыло","капот","молдинг","накладк","эмблем","шильдик","спойлер","ручка двер"]),
("Автохимия / жидкости",["антифриз","жидкость","очиститель","смазка","mercasol"]),
]
TEMPLATE_BY_CATEGORY={
"Ковры":"Ковры — форма, салон/багажник, применяемость",
"Защиты":"Защита — агрегаты, материал/толщина если есть, применяемость",
"Фильтры":"Фильтр — тип фильтра, артикул, применяемость",
"Тормоза":"Тормоза — ось/тип системы если есть, артикул, применяемость",
"Брызговики":"Брызговики — перед/зад и комплектность если есть",
"Дефлекторы":"Дефлекторы — длинный товар, комплектность, применяемость",
"Подножки / пороги":"Пороги — длинный товар, тип, применяемость",
"Фаркопы / багажные системы":"Багаж/фаркоп — тип системы и применяемость",
"Оптика":"Оптика — сторона/тип если есть, артикул, применяемость",
"Электрика / электроника":"Электрика — назначение, артикул, применяемость",
"Подвеска / рулевое":"Подвеска — узел/сторона если есть, применяемость",
"Двигатель / ТО":"Двигатель/ТО — назначение, артикул, применяемость",
"Кузов / экстерьер":"Кузов — деталь/сторона если есть, применяемость",
"Автохимия / жидкости":"Жидкости — тип/объем если есть, применяемость",
"Прочее":"Универсальный — название, артикул, применяемость",
}
def _text(p): return re.sub(r"\s+"," "," ".join([str(p.get("name") or "")," ".join(p.get("applicability") or [])]).lower().replace("ё","е"))
def detect_category(product):
    text=_text(product)
    for category,needles in CATEGORY_RULES:
        if any(n.replace("ё","е") in text for n in needles): return category
    return "Прочее"
def template_for(product):
    c=product.get("marketplace_category") or detect_category(product); return TEMPLATE_BY_CATEGORY.get(c,TEMPLATE_BY_CATEGORY["Прочее"])
def recommended_cards(product):
    # Never invent facts: all products get main + applicability only when applicability exists.
    result=["Главная"]
    if product.get("applicability"): result.append("Применяемость")
    return result
def apply_category(product):
    r=dict(product); r["marketplace_category"]=detect_category(r); r["marketplace_template"]=template_for(r); r["marketplace_cards"]=recommended_cards(r); return r
def lookup_with_category(self):
    _ORIGINAL_LOOKUP_METHOD(self); p=getattr(self,"marketplace_selected_product",None)
    if p:
        p=apply_category(p); self.marketplace_selected_product=p
        if hasattr(self,"marketplace_category_var"): self.marketplace_category_var.set(p["marketplace_category"])
        if hasattr(self,"marketplace_template_var"): self.marketplace_template_var.set(p["marketplace_template"])
        if hasattr(self,"marketplace_cards_var"): self.marketplace_cards_var.set(" + ".join(p["marketplace_cards"]))
def _find_box(root):
    for w in root.winfo_children():
        try:
            if isinstance(w,ttk.LabelFrame) and "Маркетплейсы" in w.cget("text"): return w
        except Exception: pass
        f=_find_box(w)
        if f is not None:return f
    return None
def build_template_ui(self):
    _ORIGINAL_BUILD(self); self.marketplace_category_var=tk.StringVar(value="—"); self.marketplace_template_var=tk.StringVar(value="—"); self.marketplace_cards_var=tk.StringVar(value="—"); box=_find_box(self)
    if box is None:return
    row=ttk.Frame(box); row.pack(fill="x",pady=(8,0)); ttk.Label(row,text="Категория:").pack(side="left"); ttk.Label(row,textvariable=self.marketplace_category_var).pack(side="left",padx=(6,18)); ttk.Label(row,text="Шаблон:").pack(side="left"); ttk.Label(row,textvariable=self.marketplace_template_var).pack(side="left",padx=6)
    row2=ttk.Frame(box); row2.pack(fill="x",pady=(3,0)); ttk.Label(row2,text="Карточки:").pack(side="left"); ttk.Label(row2,textvariable=self.marketplace_cards_var).pack(side="left",padx=6)
def create_with_category(self):
    p=getattr(self,"marketplace_selected_product",None)
    if p:self.marketplace_selected_product=apply_category(p)
    return _ORIGINAL_CREATE(self)
cards.detect_marketplace_category=detect_category; cards.marketplace_template_for=template_for; cards.marketplace_recommended_cards=recommended_cards; app.App._build=build_template_ui; app.App._marketplace_lookup=lookup_with_category; app.App._marketplace_create_ozon_cards=create_with_category; app.APP_VERSION=APP_VERSION; app.APP_BUILD=APP_BUILD; catalog.APP_VERSION=APP_VERSION; catalog.APP_BUILD=APP_BUILD; cards.APP_VERSION=APP_VERSION; cards.APP_BUILD=APP_BUILD
