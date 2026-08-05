
import os
import sys
import threading
import traceback
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageFilter, ImageEnhance

def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_BG_1 = resource_path("assets/background_cheviplus_1.jpg")
DEFAULT_BG_2 = resource_path("assets/background_cheviplus_2.jpg")
DEFAULT_LOGO = resource_path("assets/logo_cheviplus.png")

BUILTIN_BACKGROUNDS = {
    "Фон 1 — сплошной фирменный": DEFAULT_BG_1,
    "Фон 2 — DriveTime Auto Parts": DEFAULT_BG_2,
}
MODEL_DIR = resource_path("models")
os.environ["U2NET_HOME"] = str(MODEL_DIR)
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
APP_VERSION = "2.0"
SETTINGS_FILE = APP_DIR / "cheviplus_settings.json"

_REMBG_SESSION = None

def get_rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        _REMBG_SESSION = new_session("u2netp")
    return _REMBG_SESSION

def fit_cover(img: Image.Image, size):
    w, h = size
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))

def trim_transparency(img: Image.Image):
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img

def _clean_alpha_mask(alpha: Image.Image) -> Image.Image:
    """
    Удаляет отдельные остатки фона/логотипов и делает контур более чётким.
    Основной предмет сохраняется, мелкие оторванные компоненты удаляются.
    """
    import numpy as np
    from scipy import ndimage

    mask = np.asarray(alpha, dtype=np.uint8)

    # Удаляем почти прозрачный мусор.
    mask[mask < 28] = 0

    # Бинарная карта для поиска отдельных объектов.
    binary = mask >= 48
    labels, count = ndimage.label(binary)

    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        largest = int(sizes.max())

        # Сохраняем основной объект и достаточно крупные отдельные части.
        # Мелкие логотипы/кусочки фона удаляются.
        min_component = max(120, int(largest * 0.012))
        keep_ids = np.flatnonzero(sizes >= min_component)
        keep = np.isin(labels, keep_ids)
        mask[~keep] = 0

    # Закрываем единичные дырки и слегка расширяем маску,
    # чтобы нейросеть не "съедала" край товара.
    binary = mask > 0
    binary = ndimage.binary_closing(binary, structure=np.ones((3, 3)), iterations=1)
    binary = ndimage.binary_dilation(binary, structure=np.ones((3, 3)), iterations=1)

    # Чёткая, но не рваная граница:
    # слабые пиксели убираем, сильные делаем непрозрачными.
    cleaned = np.where(binary, mask, 0).astype(np.float32)
    cleaned = np.clip((cleaned - 22.0) * (255.0 / 205.0), 0, 255)

    # Очень лёгкое сглаживание только на 0.35 px, без заметного размытия.
    cleaned = ndimage.gaussian_filter(cleaned, sigma=0.35)
    cleaned[cleaned < 22] = 0
    cleaned[cleaned > 225] = 255

    return Image.fromarray(cleaned.astype(np.uint8), mode="L")


def remove_background(img: Image.Image):
    from rembg import remove

    result = remove(
        img.convert("RGBA"),
        session=get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")

    cleaned_alpha = _clean_alpha_mask(result.getchannel("A"))
    result.putalpha(cleaned_alpha)
    return result

def add_shadow(canvas: Image.Image, product: Image.Image, pos, blur=35, opacity=95, offset_y=28):
    alpha = product.getchannel("A")
    shadow = Image.new("RGBA", product.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda p: int(p * opacity / 255)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (pos[0], pos[1] + offset_y))

def process_one(
    source: Path,
    output_dir: Path,
    background_path: Path,
    logo_path: Path,
    canvas_size: int,
    product_fill: float,
    add_logo: bool,
    shadow: bool,
    output_format: str,
):
    original = Image.open(source)
    product = remove_background(original)
    product = trim_transparency(product)

    # Сохраняем хром и пластик, но возвращаем детализацию после вырезания.
    product_rgb = ImageEnhance.Contrast(product.convert("RGB")).enhance(1.025)
    product_rgb = product_rgb.filter(
        ImageFilter.UnsharpMask(radius=0.9, percent=105, threshold=3)
    )
    product = Image.merge("RGBA", (*product_rgb.split(), product.getchannel("A")))

    bg = Image.open(background_path).convert("RGB")
    bg = fit_cover(bg, (canvas_size, canvas_size)).convert("RGBA")

    max_w = int(canvas_size * product_fill)
    max_h = int(canvas_size * product_fill)
    ratio = min(max_w / product.width, max_h / product.height)
    new_size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    product = product.resize(new_size, Image.Resampling.LANCZOS)

    # Компенсируем небольшое размытие, которое появляется при масштабировании.
    resized_rgb = product.convert("RGB").filter(
        ImageFilter.UnsharpMask(radius=0.65, percent=75, threshold=2)
    )
    product = Image.merge("RGBA", (*resized_rgb.split(), product.getchannel("A")))

    x = (canvas_size - product.width) // 2
    y = int(canvas_size * 0.54 - product.height / 2)
    y = max(20, min(y, canvas_size - product.height - 20))

    if shadow:
        add_shadow(bg, product, (x, y))
    bg.alpha_composite(product, (x, y))

    if add_logo and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        max_logo_w = int(canvas_size * 0.16)
        scale = min(1.0, max_logo_w / logo.width)
        logo = logo.resize(
            (int(logo.width * scale), int(logo.height * scale)),
            Image.Resampling.LANCZOS,
        )
        margin = int(canvas_size * 0.025)
        bg.alpha_composite(logo, (canvas_size - logo.width - margin, canvas_size - logo.height - margin))

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem + "_cheviplus"
    fmt = output_format.upper()
    if fmt == "JPG":
        out = output_dir / f"{stem}.jpg"
        bg.convert("RGB").save(out, quality=94, optimize=True)
    elif fmt == "WEBP":
        out = output_dir / f"{stem}.webp"
        bg.convert("RGB").save(out, quality=92, method=6)
    else:
        out = output_dir / f"{stem}.png"
        bg.save(out, optimize=True)
    return out

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Cheviplus Photo Studio {APP_VERSION}")
        self.geometry("940x720")
        self.minsize(860, 660)
        self.configure(bg="#f4f6f8")
        (APP_DIR / "input").mkdir(parents=True, exist_ok=True)
        (APP_DIR / "output").mkdir(parents=True, exist_ok=True)
        self.selected_files = []
        self.cancel_requested = False
        self._build()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build(self):
        title = tk.Label(
            self, text=f"CHEVIPLUS PHOTO STUDIO  {APP_VERSION}",
            font=("Segoe UI", 20, "bold"), fg="#c71920", bg="#f4f6f8"
        )
        title.pack(pady=(18, 3))
        tk.Label(
            self, text="Пакетное удаление фона и подготовка фотографий для сайта",
            font=("Segoe UI", 10), fg="#40464d", bg="#f4f6f8"
        ).pack(pady=(0, 16))

        form = ttk.Frame(self, padding=14)
        form.pack(fill="x", padx=24)

        self.input_var = tk.StringVar(value=str(APP_DIR / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "output"))
        self.bg_choice_var = tk.StringVar(value="Фон 1 — сплошной фирменный")
        self.bg_var = tk.StringVar(value=str(DEFAULT_BG_1))
        self.logo_var = tk.StringVar(value=str(DEFAULT_LOGO))
        self.size_var = tk.StringVar(value="2000")
        self.fill_var = tk.DoubleVar(value=0.86)
        self.format_var = tk.StringVar(value="JPG")
        self.logo_enabled = tk.BooleanVar(value=False)
        self.shadow_enabled = tk.BooleanVar(value=True)
        self.recursive_enabled = tk.BooleanVar(value=True)

        self._path_row(form, 0, "Папка с исходными фото:", self.input_var, True)
        self._path_row(form, 1, "Папка для готовых фото:", self.output_var, True)
        ttk.Label(form, text="Выбор фона:").grid(row=2, column=0, sticky="w", pady=6)
        self.bg_combo = ttk.Combobox(
            form,
            textvariable=self.bg_choice_var,
            values=tuple(BUILTIN_BACKGROUNDS.keys()) + ("Свой фон…",),
            state="readonly",
            width=66,
        )
        self.bg_combo.grid(row=2, column=1, padx=8, pady=6, sticky="ew")
        self.bg_combo.bind("<<ComboboxSelected>>", self.on_background_selected)
        ttk.Button(
            form, text="Выбрать свой", command=self.choose_custom_background
        ).grid(row=2, column=2, pady=6)

        ttk.Label(form, text="Файл выбранного фона:").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.bg_var, width=70, state="readonly").grid(
            row=3, column=1, padx=8, pady=6, sticky="ew"
        )

        self._path_row(form, 4, "Логотип PNG:", self.logo_var, False)

        opts = ttk.LabelFrame(self, text="Настройки", padding=14)
        opts.pack(fill="x", padx=24, pady=14)

        ttk.Label(opts, text="Размер изображения:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.size_var, values=("1200", "1600", "2000", "2500", "3000"), width=10, state="readonly").grid(row=0, column=1, padx=8)

        ttk.Label(opts, text="Формат:").grid(row=0, column=2, sticky="w", padx=(25,0))
        ttk.Combobox(opts, textvariable=self.format_var, values=("JPG", "PNG", "WEBP"), width=10, state="readonly").grid(row=0, column=3, padx=8)

        ttk.Checkbutton(opts, text="Добавить отдельный логотип поверх фона", variable=self.logo_enabled).grid(row=1, column=0, sticky="w", pady=(12,0))
        ttk.Checkbutton(opts, text="Добавить мягкую тень", variable=self.shadow_enabled).grid(row=1, column=1, columnspan=2, sticky="w", pady=(12,0))
        ttk.Checkbutton(opts, text="Обрабатывать вложенные папки", variable=self.recursive_enabled).grid(row=1, column=3, sticky="w", pady=(12,0))

        ttk.Label(opts, text="Масштаб товара:").grid(row=2, column=0, sticky="w", pady=(12,0))
        ttk.Scale(opts, from_=0.60, to=0.94, variable=self.fill_var, orient="horizontal", length=250).grid(row=2, column=1, columnspan=2, sticky="w", pady=(12,0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=24)

        ttk.Button(
            actions,
            text="Выбрать несколько фото",
            command=self.choose_multiple_files
        ).pack(side="left")

        self.start_btn = tk.Button(
            actions, text="ОБРАБОТАТЬ ПАКЕТ",
            command=self.start, font=("Segoe UI", 12, "bold"),
            bg="#c71920", fg="white", activebackground="#9f1319",
            relief="flat", padx=24, pady=12, cursor="hand2"
        )
        self.start_btn.pack(side="left", padx=10)

        self.cancel_btn = ttk.Button(
            actions, text="Остановить", command=self.request_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="left")

        ttk.Button(
            actions, text="Открыть папку результата", command=self.open_output
        ).pack(side="left", padx=12)

        ttk.Button(
            actions, text="Сохранить настройки", command=self.save_settings
        ).pack(side="right")

        ttk.Button(
            actions, text="Сбросить настройки", command=self.reset_settings
        ).pack(side="right", padx=8)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=24, pady=(18, 8))
        self.status = tk.StringVar(value="Готово к работе")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=24)

        log_frame = ttk.LabelFrame(self, text="Журнал", padding=8)
        log_frame.pack(fill="both", expand=True, padx=24, pady=12)
        self.log = tk.Text(log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _settings_payload(self):
        return {
            "input": self.input_var.get(),
            "output": self.output_var.get(),
            "background_choice": self.bg_choice_var.get(),
            "background_path": self.bg_var.get(),
            "logo_path": self.logo_var.get(),
            "size": self.size_var.get(),
            "fill": float(self.fill_var.get()),
            "format": self.format_var.get(),
            "logo_enabled": bool(self.logo_enabled.get()),
            "shadow_enabled": bool(self.shadow_enabled.get()),
            "recursive_enabled": bool(self.recursive_enabled.get()),
        }

    def save_settings(self, silent=False):
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._settings_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if not silent:
                self.status.set("Настройки сохранены")
        except Exception as exc:
            if not silent:
                messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{exc}")

    def load_settings(self):
        if not SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.input_var.set(data.get("input", self.input_var.get()))
            self.output_var.set(data.get("output", self.output_var.get()))
            self.size_var.set(str(data.get("size", self.size_var.get())))
            self.fill_var.set(float(data.get("fill", self.fill_var.get())))
            self.format_var.set(data.get("format", self.format_var.get()))
            self.logo_enabled.set(bool(data.get("logo_enabled", self.logo_enabled.get())))
            self.shadow_enabled.set(bool(data.get("shadow_enabled", self.shadow_enabled.get())))
            self.recursive_enabled.set(bool(data.get("recursive_enabled", self.recursive_enabled.get())))
            self.logo_var.set(data.get("logo_path", self.logo_var.get()))

            choice = data.get("background_choice", self.bg_choice_var.get())
            bg_path = data.get("background_path", self.bg_var.get())
            if choice in BUILTIN_BACKGROUNDS:
                self.bg_choice_var.set(choice)
                self.bg_var.set(str(BUILTIN_BACKGROUNDS[choice]))
            elif Path(bg_path).exists():
                self.bg_choice_var.set("Свой фон…")
                self.bg_var.set(bg_path)
            self.status.set("Последние настройки восстановлены")
        except Exception:
            self.status.set("Настройки по умолчанию")

    def reset_settings(self):
        self.input_var.set(str(APP_DIR / "input"))
        self.output_var.set(str(APP_DIR / "output"))
        self.bg_choice_var.set("Фон 1 — сплошной фирменный")
        self.bg_var.set(str(DEFAULT_BG_1))
        self.logo_var.set(str(DEFAULT_LOGO))
        self.size_var.set("2000")
        self.fill_var.set(0.86)
        self.format_var.set("JPG")
        self.logo_enabled.set(False)
        self.shadow_enabled.set(True)
        self.recursive_enabled.set(True)
        self.status.set("Настройки сброшены")
        self.save_settings(silent=True)

    def on_close(self):
        self.save_settings(silent=True)
        self.destroy()

    def _path_row(self, parent, row, label, variable, folder):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable, width=70).grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        cmd = (lambda: self.choose_folder(variable)) if folder else (lambda: self.choose_file(variable))
        ttk.Button(parent, text="Выбрать", command=cmd).grid(row=row, column=2, pady=6)
        parent.columnconfigure(1, weight=1)

    def on_background_selected(self, event=None):
        choice = self.bg_choice_var.get()
        if choice in BUILTIN_BACKGROUNDS:
            self.bg_var.set(str(BUILTIN_BACKGROUNDS[choice]))
            self.status.set(f"Выбран: {choice}")
        elif choice == "Свой фон…":
            self.choose_custom_background()

    def choose_custom_background(self):
        path = filedialog.askopenfilename(
            title="Выберите собственный фон",
            initialdir=str(Path(self.bg_var.get()).parent),
            filetypes=[
                ("Изображения", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
            ],
        )
        if path:
            self.bg_choice_var.set("Свой фон…")
            self.bg_var.set(path)
            self.status.set("Выбран собственный фон")
        elif self.bg_choice_var.get() == "Свой фон…":
            self.bg_choice_var.set("Фон 1 — сплошной фирменный")
            self.bg_var.set(str(DEFAULT_BG_1))

    def choose_folder(self, var):
        p = filedialog.askdirectory(initialdir=var.get() if Path(var.get()).exists() else str(APP_DIR))
        if p:
            var.set(p)

    def choose_file(self, var):
        p = filedialog.askopenfilename(
            initialdir=str(Path(var.get()).parent),
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp")]
        )
        if p:
            var.set(p)

    def choose_multiple_files(self):
        paths = filedialog.askopenfilenames(
            title="Выберите фотографии для пакетной обработки",
            filetypes=[
                ("Все поддерживаемые изображения", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("WEBP", "*.webp"),
            ],
        )
        if paths:
            self.selected_files = [Path(p) for p in paths]
            self.status.set(f"Выбрано отдельных фотографий: {len(self.selected_files)}")
            self.write_log(f"Выбрано файлов: {len(self.selected_files)}")

    def request_cancel(self):
        self.cancel_requested = True
        self.status.set("Остановка после текущей фотографии…")

    def open_output(self):
        p = Path(self.output_var.get())
        p.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(p)
        elif sys.platform == "darwin":
            os.system(f'open "{p}"')
        else:
            os.system(f'xdg-open "{p}"')

    def write_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.update_idletasks()

    def start(self):
        inp = Path(self.input_var.get())

        files = list(self.selected_files)
        if not files:
            if not inp.exists():
                messagebox.showerror("Ошибка", "Папка с исходными фотографиями не найдена.")
                return

            iterator = inp.rglob("*") if self.recursive_enabled.get() else inp.iterdir()
            files = [
                p for p in iterator
                if p.is_file() and p.suffix.lower() in SUPPORTED
            ]

        output_dir = Path(self.output_var.get()).resolve()
        clean_files = []
        for p in files:
            try:
                if output_dir in p.resolve().parents:
                    continue
            except Exception:
                pass
            if p.stem.endswith("_cheviplus"):
                continue
            clean_files.append(p)

        files = sorted(dict.fromkeys(clean_files), key=lambda p: str(p).lower())

        if not files:
            messagebox.showwarning("Нет фотографий", "Не найдено изображений для обработки.")
            return
        if not Path(self.bg_var.get()).exists():
            messagebox.showerror("Ошибка", "Файл фона не найден.")
            return

        self.save_settings(silent=True)
        self.cancel_requested = False
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["maximum"] = len(files)
        self.progress["value"] = 0
        self.log.delete("1.0", "end")
        self.write_log(f"Версия программы: {APP_VERSION}")
        self.write_log(f"Фон: {self.bg_choice_var.get()}")
        self.write_log(f"Пакетная обработка: {len(files)} фото")
        threading.Thread(target=self._worker, args=(files,), daemon=True).start()

    def _worker(self, files):
        ok = 0
        errors = 0
        stopped = False
        input_root = Path(self.input_var.get())
        output_root = Path(self.output_var.get())

        try:
            for i, source in enumerate(files, 1):
                if self.cancel_requested:
                    stopped = True
                    self.write_log("ОБРАБОТКА ОСТАНОВЛЕНА ПОЛЬЗОВАТЕЛЕМ")
                    break

                self.status.set(f"Обработка {i} из {len(files)}: {source.name}")

                target_dir = output_root
                try:
                    if input_root.exists() and input_root in source.parents:
                        relative_parent = source.parent.relative_to(input_root)
                        target_dir = output_root / relative_parent
                except Exception:
                    target_dir = output_root

                try:
                    out = process_one(
                        source=source,
                        output_dir=target_dir,
                        background_path=Path(self.bg_var.get()),
                        logo_path=Path(self.logo_var.get()),
                        canvas_size=int(self.size_var.get()),
                        product_fill=float(self.fill_var.get()),
                        add_logo=bool(self.logo_enabled.get()),
                        shadow=bool(self.shadow_enabled.get()),
                        output_format=self.format_var.get(),
                    )
                    ok += 1
                    self.write_log(f"OK  {source.name} → {out}")
                except Exception as exc:
                    errors += 1
                    self.write_log(f"ОШИБКА  {source.name}: {exc}")

                self.progress["value"] = i

            if stopped:
                self.status.set(f"Остановлено. Готово: {ok}; ошибок: {errors}")
                messagebox.showinfo(
                    "Обработка остановлена",
                    f"Обработано: {ok}\nОшибок: {errors}"
                )
            else:
                self.status.set(f"Готово. Успешно: {ok}; ошибок: {errors}")
                messagebox.showinfo(
                    "Пакетная обработка завершена",
                    f"Всего: {len(files)}\nУспешно: {ok}\nОшибок: {errors}"
                )
        except Exception:
            self.write_log(traceback.format_exc())
            messagebox.showerror("Ошибка", "Произошла непредвиденная ошибка. Смотрите журнал.")
        finally:
            self.selected_files = []
            self.cancel_requested = False
            self.start_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

if __name__ == "__main__":
    App().mainloop()
