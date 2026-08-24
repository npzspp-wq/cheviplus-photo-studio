"""First marketplace-card generator for Cheviplus Photo Studio.

Uses the product selected from the local Excel/SQLite catalog and one processed
photo chosen by the employee. Generates a factual, no-hallucination set of Ozon
3:4 JPG cards. AI is deliberately not required in this first version.
"""
from __future__ import annotations

import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import app
import cheviplus_marketplace_catalog as catalog

APP_VERSION = "5.17"
APP_BUILD = "2026.08.24.04"
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
    lines = []
    current = ""
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


def _fit_photo(photo: Image.Image, box, padding=0):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 - padding * 2, y1 - y0 - padding * 2
    image = photo.convert("RGB")
    ratio = min(bw / image.width, bh / image.height)
    resized = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    x = x0 + (x1 - x0 - resized.width) // 2
    y = y0 + (y1 - y0 - resized.height) // 2
    return resized, (x, y)


def _base_card():
    w, h = CARD_SIZE
    img = Image.new("RGB", CARD_SIZE, (246, 247, 249))
    draw = ImageDraw.Draw(img)
    # Premium neutral studio surface.
    draw.rectangle((0, 0, w, 150), fill=(28, 31, 36))
    draw.rectangle((0, h - 130, w, h), fill=(238, 240, 243))
    draw.line((70, h - 130, w - 70, h - 130), fill=(205, 208, 214), width=2)
    return img


def _brand_header(draw):
    draw.text((70, 45), "CHEVIPLUS", font=_font(60, True), fill=(245, 245, 247))
    draw.text((70, 108), "MARKETPLACE", font=_font(25, False), fill=(185, 190, 198))


def _product_name(product):
    return (product.get("name") or "ТОВАР").strip()


def _article_text(product):
    article = product.get("article") or product.get("code") or ""
    return f"АРТИКУЛ {article}" if article else ""


def _short_apps(product, limit=4):
    apps = product.get("applicability") or []
    return apps[:limit]


def build_card_main(photo, product):
    img = _base_card()
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    title_font = _font(62, True)
    y = 210
    for line in _wrap(draw, _product_name(product).upper(), title_font, 1060, 3):
        draw.text((70, y), line, font=title_font, fill=(25, 28, 33))
        y += 72
    art = _article_text(product)
    if art:
        draw.rounded_rectangle((70, y + 12, 520, y + 72), radius=18, fill=(225, 38, 44))
        draw.text((92, y + 25), art, font=_font(28, True), fill="white")
    fitted, pos = _fit_photo(photo, (100, 520, 1100, 1400), 20)
    img.paste(fitted, pos)
    draw.text((70, 1490), "Карточка сформирована по данным товарной базы", font=_font(24), fill=(105, 110, 118))
    return img


def build_card_applicability(photo, product):
    img = _base_card()
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    draw.text((70, 210), "ПРИМЕНЯЕМОСТЬ", font=_font(68, True), fill=(25, 28, 33))
    fitted, pos = _fit_photo(photo, (650, 300, 1120, 1040), 10)
    fitted = ImageEnhance.Contrast(fitted).enhance(1.02)
    img.paste(fitted, pos)

    apps = _short_apps(product, 7)
    y = 355
    if apps:
        for app_line in apps:
            draw.rounded_rectangle((70, y - 8, 610, y + 90), radius=20, fill=(255, 255, 255), outline=(214, 217, 222), width=2)
            lines = _wrap(draw, app_line, _font(34, True), 485, 2)
            ty = y + 8
            for line in lines:
                draw.text((100, ty), line, font=_font(34, True), fill=(42, 46, 52))
                ty += 42
            y += 120
    else:
        draw.text((80, 390), "Применяемость не указана в базе", font=_font(36, True), fill=(80, 84, 92))

    draw.text((70, 1370), _product_name(product), font=_font(34, True), fill=(35, 38, 43))
    art = _article_text(product)
    if art:
        draw.text((70, 1425), art, font=_font(28), fill=(105, 110, 118))
    return img


def build_card_info(photo, product):
    img = _base_card()
    draw = ImageDraw.Draw(img)
    _brand_header(draw)
    draw.text((70, 210), "ДАННЫЕ ТОВАРА", font=_font(68, True), fill=(25, 28, 33))
    fitted, pos = _fit_photo(photo, (100, 350, 1100, 1020), 10)
    blurred = fitted.filter(ImageFilter.GaussianBlur(radius=0.15))
    img.paste(blurred, pos)

    y = 1080
    facts = []
    if product.get("article"):
        facts.append(("Каталожный номер", product["article"]))
    if product.get("code"):
        facts.append(("Код номенклатуры", product["code"]))
    apps = product.get("applicability") or []
    if apps:
        facts.append(("Применяемость в базе", f"{len(apps)} вариант(а/ов)"))
    facts.append(("Источник характеристик", "загруженная база Excel"))

    for label, value in facts[:4]:
        draw.text((80, y), label.upper(), font=_font(23, True), fill=(128, 132, 140))
        draw.text((80, y + 34), str(value), font=_font(34, True), fill=(35, 38, 43))
        y += 105
    return img


def generate_cards(photo_path: Path, product: dict, out_dir: Path):
    photo = Image.open(photo_path).convert("RGB")
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = [
        ("01_OZON_MAIN.jpg", build_card_main(photo, product)),
        ("02_OZON_APPLICABILITY.jpg", build_card_applicability(photo, product)),
        ("03_OZON_PRODUCT_DATA.jpg", build_card_info(photo, product)),
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
    ttk.Label(row, text="3 карточки 1200×1600 • только факты из базы").pack(side="left", padx=10)


def create_ozon_cards(self):
    product = getattr(self, "marketplace_selected_product", None)
    if not product:
        messagebox.showwarning("Ozon", "Сначала найдите товар по артикулу или коду.")
        return
    photo = filedialog.askopenfilename(
        title="Выберите готовое фото товара для карточек Ozon",
        filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp")],
    )
    if not photo:
        return
    default_name = catalog.normalize_key(product.get("article") or product.get("code") or "OZON") or "OZON"
    out_parent = filedialog.askdirectory(title="Куда сохранить карточки Ozon?")
    if not out_parent:
        return
    out_dir = Path(out_parent) / f"OZON_{default_name}"
    try:
        files = generate_cards(Path(photo), product, out_dir)
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
