"""Marketplace-card generator for Cheviplus Photo Studio.

Creates factual Ozon 3:4 cards directly from the selected catalog item.
No product photo is required. The generator uses only data found in the local
Excel/SQLite catalog and never invents product characteristics.
"""
from __future__ import annotations

import re
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont

import app
import cheviplus_marketplace_catalog as catalog

APP_VERSION = "5.18"
APP_BUILD = "2026.08.24.05"
CARD_SIZE = (1200, 1600)

_ORIGINAL_BUILD = app.App._build


def _font(size: int, bold=False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width, max_lines=4):
    words = re.split(r"\s+", (text or "").strip())
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines)) < len(" ".join(words)):
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def _base_card(accent=False):
    w, h = CARD_SIZE
    img = Image.new("RGB", CARD_SIZE, (247, 248, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 170), fill=(28, 31, 36))
    draw.rectangle((0, h - 120, w, h), fill=(238, 240, 243))
    draw.line((70, h - 120, w - 70, h - 120), fill=(205, 208, 214), width=2)
    if accent:
        draw.rounded_rectangle((735, 240, 1110, 615), radius=42, fill=(229, 35, 42))
        draw.ellipse((800, 305, 1045, 550), outline=(255, 255, 255), width=16)
        draw.line((860, 420, 985, 420), fill=(255, 255, 255), width=18)
        draw.line((923, 357, 923, 483), fill=(255, 255, 255), width=18)
    return img


def _brand_header(draw):
    draw.text((70, 48), "CHEVIPLUS", font=_font(62, True), fill=(247, 247, 249))
    draw.text((70, 117), "КАРТОЧКА ТОВАРА", font=_font(25), fill=(188, 193, 201))


def _product_name(product):
    return (product.get("name") or "ТОВАР").strip()


def _article(product):
    return (product.get("article") or product.get("code") or "").strip()


def _apps(product):
    return product.get("applicability") or []


def _primary_vehicle(product):
    apps = _apps(product)
    return apps[0] if apps else ""


def _draw_title(draw, text, y=250, max_lines=4, size=64):
    font = _font(size, True)
    for line in _wrap(draw, text.upper(), font, 1060, max_lines):
        draw.text((70, y), line, font=font, fill=(26, 29, 34))
        y += int(size * 1.16)
    return y


def build_card_main(product):
    img = _base_card(accent=True)
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    y = _draw_title(draw, _product_name(product), 245, 4, 61)

    article = _article(product)
    if article:
        draw.rounded_rectangle((70, y + 25, 545, y + 102), radius=20, fill=(229, 35, 42))
        draw.text((98, y + 43), f"АРТИКУЛ {article}", font=_font(31, True), fill="white")

    vehicle = _primary_vehicle(product)
    if vehicle:
        draw.text((70, 865), "ПОДХОДИТ ДЛЯ", font=_font(28, True), fill=(120, 124, 132))
        vy = 920
        for line in _wrap(draw, vehicle, _font(54, True), 1000, 3):
            draw.text((70, vy), line, font=_font(54, True), fill=(32, 35, 40))
            vy += 66

    draw.rounded_rectangle((70, 1240, 1130, 1395), radius=28, fill=(255, 255, 255), outline=(216, 219, 224), width=2)
    draw.text((105, 1275), "ДАННЫЕ ВЗЯТЫ ИЗ ЗАГРУЖЕННОЙ БАЗЫ", font=_font(30, True), fill=(55, 59, 66))
    draw.text((105, 1324), "Без выдуманных характеристик", font=_font(28), fill=(105, 110, 118))
    return img


def build_card_applicability(product):
    img = _base_card()
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    draw.text((70, 235), "ПРИМЕНЯЕМОСТЬ", font=_font(70, True), fill=(26, 29, 34))
    draw.text((70, 330), _product_name(product), font=_font(32, True), fill=(95, 99, 107))

    apps = _apps(product)
    y = 420
    if apps:
        for idx, line in enumerate(apps[:7], start=1):
            draw.rounded_rectangle((70, y, 1130, y + 120), radius=24, fill=(255, 255, 255), outline=(214, 217, 222), width=2)
            draw.ellipse((98, y + 35, 148, y + 85), fill=(229, 35, 42))
            draw.text((113, y + 40), str(idx), font=_font(24, True), fill="white")
            ty = y + 25
            for wrapped in _wrap(draw, line, _font(36, True), 900, 2):
                draw.text((180, ty), wrapped, font=_font(36, True), fill=(40, 44, 50))
                ty += 44
            y += 142
        if len(apps) > 7:
            draw.text((70, y + 10), f"И ещё {len(apps) - 7} вариант(а/ов) в базе", font=_font(30, True), fill=(105, 110, 118))
    else:
        draw.text((70, 460), "В базе применяемость не указана", font=_font(40, True), fill=(80, 84, 92))

    article = _article(product)
    if article:
        draw.text((70, 1460), f"АРТИКУЛ {article}", font=_font(30, True), fill=(90, 94, 102))
    return img


def build_card_product_data(product):
    img = _base_card()
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    draw.text((70, 235), "О ТОВАРЕ", font=_font(70, True), fill=(26, 29, 34))

    y = 370
    name = _product_name(product)
    blocks = [("НАИМЕНОВАНИЕ", name)]
    if product.get("article"):
        blocks.append(("КАТАЛОЖНЫЙ НОМЕР", product["article"]))
    if product.get("code"):
        blocks.append(("КОД НОМЕНКЛАТУРЫ", product["code"]))
    if _apps(product):
        blocks.append(("ЗАПИСЕЙ ПРИМЕНЯЕМОСТИ", str(len(_apps(product)))))

    for label, value in blocks[:4]:
        draw.text((70, y), label, font=_font(26, True), fill=(126, 130, 138))
        y += 45
        lines = _wrap(draw, str(value), _font(43, True), 1030, 3)
        for line in lines:
            draw.text((70, y), line, font=_font(43, True), fill=(35, 38, 43))
            y += 52
        y += 55

    draw.rounded_rectangle((70, 1290, 1130, 1425), radius=26, fill=(28, 31, 36))
    draw.text((105, 1325), "ХАРАКТЕРИСТИКИ НЕ ВЫДУМЫВАЮТСЯ", font=_font(31, True), fill=(248, 248, 250))
    draw.text((105, 1371), "Показываем только то, что есть в базе", font=_font(27), fill=(190, 194, 202))
    return img


def generate_cards(product: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = [
        ("01_OZON_MAIN.jpg", build_card_main(product)),
        ("02_OZON_APPLICABILITY.jpg", build_card_applicability(product)),
        ("03_OZON_PRODUCT_DATA.jpg", build_card_product_data(product)),
    ]
    result = []
    for name, image in cards:
        path = out_dir / name
        image.save(path, "JPEG", quality=92, optimize=True, progressive=True)
        result.append(path)
    return result


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


def build_cards_ui(self):
    _ORIGINAL_BUILD(self)
    box = _find_marketplace_box(self)
    if box is None:
        return
    row = ttk.Frame(box)
    row.pack(fill="x", pady=(10, 0))
    ttk.Button(row, text="СОЗДАТЬ КАРТОЧКИ OZON", command=self._marketplace_create_ozon_cards).pack(side="left")
    ttk.Label(row, text="3 карточки 1200×1600 • фото не требуется • только данные из базы").pack(side="left", padx=10)


def create_ozon_cards(self):
    product = getattr(self, "marketplace_selected_product", None)
    if not product:
        messagebox.showwarning("Ozon", "Сначала найдите товар по артикулу или коду.")
        return

    out_parent = filedialog.askdirectory(title="Куда сохранить карточки Ozon?")
    if not out_parent:
        return

    default_name = catalog.normalize_key(_article(product) or "OZON") or "OZON"
    out_dir = Path(out_parent) / f"OZON_{default_name}"
    try:
        files = generate_cards(product, out_dir)
    except Exception as exc:
        messagebox.showerror("Ozon", f"Не удалось создать карточки:\n{exc}")
        return

    self.status.set(f"Создано карточек Ozon: {len(files)}")
    messagebox.showinfo("Ozon", f"Готово. Создано {len(files)} карточки.\nПапка:\n{out_dir}")


app.App._build = build_cards_ui
app.App._marketplace_create_ozon_cards = create_ozon_cards
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
catalog.APP_VERSION = APP_VERSION
catalog.APP_BUILD = APP_BUILD
