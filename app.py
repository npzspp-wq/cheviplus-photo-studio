import os
import sys
import json
import math
import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageFilter, ImageEnhance, ImageTk


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_BG_1 = resource_path("assets/background_cheviplus_1.jpg")
DEFAULT_BG_2 = resource_path("assets/background_cheviplus_2.jpg")
DEFAULT_LOGO = resource_path("assets/logo_cheviplus.png")
BACKGROUNDS_DIR = resource_path("assets/backgrounds")
MODEL_DIR = resource_path("models")
os.environ["U2NET_HOME"] = str(MODEL_DIR)

APP_VERSION = "3.0"
SETTINGS_FILE = APP_DIR / "cheviplus_settings.json"
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

DEFAULT_BACKGROUND_NAMES = {
    "Фон 1 — Cheviplus": DEFAULT_BG_1,
    "Фон 2 — DriveTime Auto Parts": DEFAULT_BG_2,
}


def discover_backgrounds():
    backgrounds = dict(DEFAULT_BACKGROUND_NAMES)
    if BACKGROUNDS_DIR.exists():
        for path in sorted(BACKGROUNDS_DIR.iterdir(), key=lambda p: p.name.lower()):
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                label = path.stem.replace("_", " ").replace("-", " ").strip()
                if label:
                    backgrounds[f"Фон — {label}"] = path
    return backgrounds


BUILTIN_BACKGROUNDS = discover_backgrounds()
_SESSION_LOCAL = threading.local()


def get_rembg_session():
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        from rembg import new_session
        session = new_session("u2netp")
        _SESSION_LOCAL.session = session
    return session


def fit_cover(img: Image.Image, size):
    w, h = size
    ratio = max(w / img.width, h / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def trim_transparency(img: Image.Image):
    img = img.convert("RGBA")
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def clean_alpha_mask(alpha: Image.Image, cleanup=45, edge_expand=1):
    import numpy as np
    from scipy import ndimage

    cleanup = max(0, min(100, int(cleanup)))
    edge_expand = max(0, min(4, int(edge_expand)))

    mask = np.asarray(alpha, dtype=np.uint8).copy()
    low_cut = int(12 + cleanup * 0.28)
    binary_cut = int(32 + cleanup * 0.35)
    mask[mask < low_cut] = 0

    binary = mask >= binary_cut
    labels, count = ndimage.label(binary)

    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        largest = int(sizes.max()) if sizes.size else 0
        # Чем выше очистка, тем активнее удаляются отдельные кусочки старого фона.
        fraction = 0.002 + cleanup * 0.00015
        min_component = max(80, int(largest * fraction))
        keep_ids = np.flatnonzero(sizes >= min_component)
        keep = np.isin(labels, keep_ids)
        mask[~keep] = 0

    binary = mask > 0
    binary = ndimage.binary_closing(binary, structure=np.ones((3, 3)), iterations=1)
    if edge_expand:
        binary = ndimage.binary_dilation(
            binary, structure=np.ones((3, 3)), iterations=edge_expand
        )

    cleaned = np.where(binary, mask, 0).astype(np.float32)
    contrast_start = 18 + cleanup * 0.08
    cleaned = np.clip((cleaned - contrast_start) * (255.0 / max(1.0, 235.0 - contrast_start)), 0, 255)

    # Очень лёгкое сглаживание контура — без заметного размытия.
    sigma = 0.25 if cleanup < 65 else 0.35
    cleaned = ndimage.gaussian_filter(cleaned, sigma=sigma)
    cleaned[cleaned < low_cut] = 0
    cleaned[cleaned > 226] = 255
    return Image.fromarray(cleaned.astype(np.uint8), mode="L")


def remove_background(img: Image.Image, cleanup=45, edge_expand=1):
    from rembg import remove

    result = remove(
        img.convert("RGBA"),
        session=get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")
    result.putalpha(clean_alpha_mask(result.getchannel("A"), cleanup, edge_expand))
    return result


def auto_straighten(product: Image.Image):
    """Слегка выравнивает длинные детали по главной оси, не меняя перспективу."""
    import numpy as np

    alpha = np.asarray(product.getchannel("A"))
    ys, xs = np.nonzero(alpha > 100)
    if len(xs) < 500:
        return product

    width = xs.max() - xs.min() + 1
    height = ys.max() - ys.min() + 1
    if width < height * 1.35:
        return product

    coords = np.column_stack((xs - xs.mean(), ys - ys.mean()))
    cov = np.cov(coords, rowvar=False)
    values, vectors = np.linalg.eigh(cov)
    vx, vy = vectors[:, values.argmax()]
    angle = math.degrees(math.atan2(vy, vx))
    while angle > 90:
        angle -= 180
    while angle < -90:
        angle += 180

    if abs(angle) < 0.5 or abs(angle) > 12:
        return product

    return product.rotate(
        -angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0, 0),
    )


def add_shadow(canvas, product, pos, strength=35):
    strength = max(0, min(80, int(strength)))
    if strength == 0:
        return
    blur = max(12, int(product.width * 0.018))
    offset_y = max(8, int(product.height * 0.035))
    alpha = product.getchannel("A")
    shadow = Image.new("RGBA", product.size, (0, 0, 0, 255))
    shadow.putalpha(alpha.point(lambda p: int(p * strength / 100)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (pos[0], pos[1] + offset_y))


def compose_image(
    source,
    background_path,
    logo_path,
    canvas_size,
    product_fill,
    add_logo,
    shadow,
    shadow_strength,
    cleanup,
    edge_expand,
    sharpness,
    straighten,
):
    original = Image.open(source)
    product = remove_background(original, cleanup=cleanup, edge_expand=edge_expand)
    product = trim_transparency(product)

    if straighten:
        product = trim_transparency(auto_straighten(product))

    sharpness = max(0, min(100, int(sharpness)))
    rgb = product.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.02)
    if sharpness:
        rgb = rgb.filter(
            ImageFilter.UnsharpMask(
                radius=0.65 + sharpness / 180,
                percent=45 + int(sharpness * 1.25),
                threshold=2,
            )
        )
    product = Image.merge("RGBA", (*rgb.split(), product.getchannel("A")))

    bg = fit_cover(Image.open(background_path).convert("RGB"), (canvas_size, canvas_size)).convert("RGBA")

    max_w = int(canvas_size * product_fill)
    max_h = int(canvas_size * product_fill)
    ratio = min(max_w / max(1, product.width), max_h / max(1, product.height))
    new_size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    product = product.resize(new_size, Image.Resampling.LANCZOS)

    if sharpness:
        resized_rgb = product.convert("RGB").filter(
            ImageFilter.UnsharpMask(radius=0.55, percent=35 + sharpness, threshold=2)
        )
        product = Image.merge("RGBA", (*resized_rgb.split(), product.getchannel("A")))

    x = (canvas_size - product.width) // 2
    y = int(canvas_size * 0.54 - product.height / 2)
    y = max(20, min(y, canvas_size - product.height - 20))

    if shadow:
        add_shadow(bg, product, (x, y), shadow_strength)
    bg.alpha_composite(product, (x, y))

    if add_logo and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        max_logo_w = int(canvas_size * 0.15)
        scale = min(1.0, max_logo_w / max(1, logo.width))
        logo = logo.resize(
            (max(1, int(logo.width * scale)), max(1, int(logo.height * scale))),
            Image.Resampling.LANCZOS,
        )
        margin = int(canvas_size * 0.025)
        bg.alpha_composite(
            logo,
            (canvas_size - logo.width - margin, canvas_size - logo.height - margin),
        )
    return bg


def save_result(image, source, output_dir, output_format):
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem + "_cheviplus"
    fmt = output_format.upper()
    if fmt == "JPG":
        out = output_dir / f"{stem}.jpg"
        image.convert("RGB").save(out, quality=95, optimize=True)
    elif fmt == "WEBP":
        out = output_dir / f"{stem}.webp"
        image.convert("RGB").save(out, quality=93, method=6)
    else:
        out = output_dir / f"{stem}.png"
        image.save(out, optimize=True)
    return out


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Cheviplus Photo Studio {APP_VERSION}")
        self.geometry("1280x820")
        self.minsize(1120, 720)
        self.configure(bg="#f3f5f7")

        (APP_DIR / "input").mkdir(parents=True, exist_ok=True)
        (APP_DIR / "output").mkdir(parents=True, exist_ok=True)

        self.selected_files = []
        self.cancel_requested = False
        self.preview_photo = None
        self.preview_source = None
        self.ui_queue = queue.Queue()

        self._build()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.process_ui_queue)

    def _build(self):
        header = tk.Frame(self, bg="#20252b", height=72)
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"CHEVIPLUS PHOTO STUDIO {APP_VERSION}",
            font=("Segoe UI", 20, "bold"),
            fg="white",
            bg="#20252b",
        ).pack(side="left", padx=24, pady=18)
        tk.Label(
            header,
            text="Профессиональная пакетная подготовка фотографий",
            font=("Segoe UI", 10),
            fg="#cfd5db",
            bg="#20252b",
        ).pack(side="left", pady=22)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=14, pady=14)

        left = ttk.Frame(main, padding=10)
        right = ttk.Frame(main, padding=10)
        main.add(left, weight=3)
        main.add(right, weight=2)

        self.input_var = tk.StringVar(value=str(APP_DIR / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "output"))
        self.bg_choice_var = tk.StringVar(value="Фон 1 — Cheviplus")
        self.bg_var = tk.StringVar(value=str(DEFAULT_BG_1))
        self.logo_var = tk.StringVar(value=str(DEFAULT_LOGO))
        self.size_var = tk.StringVar(value="2000")
        self.fill_var = tk.DoubleVar(value=0.86)
        self.format_var = tk.StringVar(value="JPG")
        self.logo_enabled = tk.BooleanVar(value=False)
        self.shadow_enabled = tk.BooleanVar(value=True)
        self.shadow_strength_var = tk.IntVar(value=35)
        self.recursive_enabled = tk.BooleanVar(value=True)
        self.cleanup_var = tk.IntVar(value=45)
        self.edge_expand_var = tk.IntVar(value=1)
        self.sharpness_var = tk.IntVar(value=45)
        self.straighten_var = tk.BooleanVar(value=True)
        self.workers_var = tk.IntVar(value=2)

        files_box = ttk.LabelFrame(left, text="1. Файлы и фон", padding=12)
        files_box.pack(fill="x")
        self._path_row(files_box, 0, "Исходные фото:", self.input_var, True)
        self._path_row(files_box, 1, "Готовые фото:", self.output_var, True)

        ttk.Label(files_box, text="Фон:").grid(row=2, column=0, sticky="w", pady=5)
        self.bg_combo = ttk.Combobox(
            files_box,
            textvariable=self.bg_choice_var,
            values=tuple(BUILTIN_BACKGROUNDS.keys()) + ("Свой фон…",),
            state="readonly",
            width=42,
        )
        self.bg_combo.grid(row=2, column=1, sticky="ew", padx=6, pady=5)
        self.bg_combo.bind("<<ComboboxSelected>>", self.on_background_selected)
        bg_btns = ttk.Frame(files_box)
        bg_btns.grid(row=2, column=2, sticky="w")
        ttk.Button(bg_btns, text="Свой", command=self.choose_custom_background).pack(side="left")
        ttk.Button(bg_btns, text="Обновить", command=self.refresh_backgrounds).pack(side="left", padx=4)
        files_box.columnconfigure(1, weight=1)

        basic = ttk.LabelFrame(left, text="2. Основные настройки", padding=12)
        basic.pack(fill="x", pady=(10, 0))
        ttk.Label(basic, text="Размер:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            basic, textvariable=self.size_var,
            values=("1200", "1600", "2000", "2500", "3000"),
            width=9, state="readonly"
        ).grid(row=0, column=1, padx=6)
        ttk.Label(basic, text="Формат:").grid(row=0, column=2, padx=(20, 0))
        ttk.Combobox(
            basic, textvariable=self.format_var,
            values=("JPG", "PNG", "WEBP"),
            width=8, state="readonly"
        ).grid(row=0, column=3, padx=6)
        ttk.Label(basic, text="Потоки:").grid(row=0, column=4, padx=(20, 0))
        ttk.Spinbox(basic, from_=1, to=4, textvariable=self.workers_var, width=5).grid(row=0, column=5)

        ttk.Checkbutton(basic, text="Мягкая тень", variable=self.shadow_enabled).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Автовыравнивание длинных деталей", variable=self.straighten_var).grid(row=1, column=1, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Вложенные папки", variable=self.recursive_enabled).grid(row=1, column=4, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Отдельный логотип поверх фона", variable=self.logo_enabled).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._scale_row(basic, 3, "Масштаб товара", self.fill_var, 0.60, 0.94, lambda v: f"{float(v)*100:.0f}%")
        self._scale_row(basic, 4, "Сила тени", self.shadow_strength_var, 0, 80, lambda v: f"{float(v):.0f}%")

        advanced = ttk.LabelFrame(left, text="3. Качество краёв", padding=12)
        advanced.pack(fill="x", pady=(10, 0))
        self._scale_row(advanced, 0, "Удаление остатков фона", self.cleanup_var, 0, 100, lambda v: f"{float(v):.0f}")
        self._scale_row(advanced, 1, "Расширение края", self.edge_expand_var, 0, 4, lambda v: f"{float(v):.0f} px")
        self._scale_row(advanced, 2, "Резкость товара", self.sharpness_var, 0, 100, lambda v: f"{float(v):.0f}")

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="Выбрать несколько фото", command=self.choose_multiple_files).pack(side="left")
        ttk.Button(actions, text="ПРЕДПРОСМОТР", command=self.start_preview).pack(side="left", padx=6)
        self.start_btn = tk.Button(
            actions,
            text="ОБРАБОТАТЬ ПАКЕТ",
            command=self.start,
            font=("Segoe UI", 11, "bold"),
            bg="#c71920", fg="white", activebackground="#9f1319",
            relief="flat", padx=18, pady=8, cursor="hand2",
        )
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Остановить", command=self.request_cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)

        settings_bar = ttk.Frame(left)
        settings_bar.pack(fill="x")
        ttk.Button(settings_bar, text="Открыть результат", command=self.open_output).pack(side="left")
        ttk.Button(settings_bar, text="Сохранить настройки", command=self.save_settings).pack(side="right")
        ttk.Button(settings_bar, text="Сбросить", command=self.reset_settings).pack(side="right", padx=6)

        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(14, 5))
        self.status = tk.StringVar(value="Готово к работе")
        ttk.Label(left, textvariable=self.status).pack(anchor="w")

        log_box = ttk.LabelFrame(left, text="Журнал", padding=6)
        log_box.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(log_box, height=8, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        preview_box = ttk.LabelFrame(right, text="Предпросмотр результата", padding=10)
        preview_box.pack(fill="both", expand=True)
        self.preview_label = tk.Label(
            preview_box,
            text="Выберите фотографию и нажмите «ПРЕДПРОСМОТР»",
            bg="#e7eaed", fg="#5d6670",
            font=("Segoe UI", 11),
        )
        self.preview_label.pack(fill="both", expand=True)
        self.preview_info = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.preview_info, wraplength=420).pack(fill="x", pady=(8, 0))

    def _scale_row(self, parent, row, text, variable, frm, to, formatter):
        ttk.Label(parent, text=text + ":").grid(row=row, column=0, sticky="w", pady=6)
        scale = ttk.Scale(parent, from_=frm, to=to, variable=variable, orient="horizontal", length=300)
        scale.grid(row=row, column=1, columnspan=4, sticky="ew", padx=8)
        value = ttk.Label(parent, width=8)
        value.grid(row=row, column=5, sticky="e")
        def update(*_):
            value.config(text=formatter(variable.get()))
        variable.trace_add("write", update)
        update()

    def _path_row(self, parent, row, label, variable, folder):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
        command = (lambda: self.choose_folder(variable)) if folder else (lambda: self.choose_file(variable))
        ttk.Button(parent, text="Выбрать", command=command).grid(row=row, column=2, pady=5)

    def choose_folder(self, variable):
        path = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if path:
            variable.set(path)

    def choose_file(self, variable):
        path = filedialog.askopenfilename(initialdir=str(Path(variable.get()).parent))
        if path:
            variable.set(path)

    def choose_custom_background(self):
        path = filedialog.askopenfilename(
            title="Выберите собственный фон",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp")],
        )
        if path:
            self.bg_choice_var.set("Свой фон…")
            self.bg_var.set(path)

    def refresh_backgrounds(self):
        global BUILTIN_BACKGROUNDS
        BUILTIN_BACKGROUNDS = discover_backgrounds()
        self.bg_combo["values"] = tuple(BUILTIN_BACKGROUNDS.keys()) + ("Свой фон…",)
        self.status.set(f"Фонов найдено: {len(BUILTIN_BACKGROUNDS)}")

    def on_background_selected(self, _event=None):
        choice = self.bg_choice_var.get()
        if choice in BUILTIN_BACKGROUNDS:
            self.bg_var.set(str(BUILTIN_BACKGROUNDS[choice]))
        elif choice == "Свой фон…":
            self.choose_custom_background()

    def choose_multiple_files(self):
        paths = filedialog.askopenfilenames(
            title="Выберите фотографии",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff")],
        )
        if paths:
            self.selected_files = [Path(p) for p in paths]
            self.preview_source = self.selected_files[0]
            self.status.set(f"Выбрано фотографий: {len(self.selected_files)}")

    def collect_files(self):
        files = list(self.selected_files)
        input_root = Path(self.input_var.get())
        if not files:
            if not input_root.exists():
                raise FileNotFoundError("Папка исходных фотографий не найдена.")
            iterator = input_root.rglob("*") if self.recursive_enabled.get() else input_root.iterdir()
            files = [p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED]

        output_root = Path(self.output_var.get()).resolve()
        result = []
        for p in files:
            try:
                if output_root in p.resolve().parents:
                    continue
            except Exception:
                pass
            if not p.stem.endswith("_cheviplus"):
                result.append(p)
        return sorted(dict.fromkeys(result), key=lambda p: str(p).lower())

    def current_options(self):
        return dict(
            background_path=Path(self.bg_var.get()),
            logo_path=Path(self.logo_var.get()),
            canvas_size=int(self.size_var.get()),
            product_fill=float(self.fill_var.get()),
            add_logo=bool(self.logo_enabled.get()),
            shadow=bool(self.shadow_enabled.get()),
            shadow_strength=int(self.shadow_strength_var.get()),
            cleanup=int(self.cleanup_var.get()),
            edge_expand=int(round(self.edge_expand_var.get())),
            sharpness=int(self.sharpness_var.get()),
            straighten=bool(self.straighten_var.get()),
        )

    def start_preview(self):
        try:
            files = self.collect_files()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        if not files:
            messagebox.showwarning("Нет фотографий", "Не найдено фотографий.")
            return
        self.preview_source = files[0]
        self.status.set("Создание предпросмотра…")
        threading.Thread(target=self.preview_worker, daemon=True).start()

    def preview_worker(self):
        try:
            image = compose_image(self.preview_source, **self.current_options())
            image.thumbnail((520, 620), Image.Resampling.LANCZOS)
            self.ui_queue.put(("preview", image.copy(), self.preview_source.name))
        except Exception as exc:
            self.ui_queue.put(("error", f"Предпросмотр: {exc}"))

    def show_preview(self, image, name):
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.config(image=self.preview_photo, text="")
        self.preview_info.set(f"Файл: {name} | Фон: {self.bg_choice_var.get()}")
        self.status.set("Предпросмотр готов")

    def start(self):
        try:
            files = self.collect_files()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
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
        self.write_log(f"Cheviplus Photo Studio {APP_VERSION}")
        self.write_log(f"Фотографий: {len(files)}; потоков: {self.workers_var.get()}")
        threading.Thread(target=self.batch_worker, args=(files,), daemon=True).start()

    def batch_worker(self, files):
        options = self.current_options()
        input_root = Path(self.input_var.get())
        output_root = Path(self.output_var.get())
        workers = max(1, min(4, int(self.workers_var.get())))
        completed = 0
        ok = 0
        errors = 0

        def one(source):
            if self.cancel_requested:
                return source, None, "Остановлено"
            target_dir = output_root
            try:
                if input_root.exists() and input_root in source.parents:
                    target_dir = output_root / source.parent.relative_to(input_root)
            except Exception:
                pass
            image = compose_image(source, **options)
            out = save_result(image, source, target_dir, self.format_var.get())
            return source, out, None

        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(one, source): source for source in files}
                for future in as_completed(futures):
                    if self.cancel_requested:
                        for pending in futures:
                            pending.cancel()
                    source = futures[future]
                    try:
                        _, out, error = future.result()
                        if error:
                            errors += 1
                            self.ui_queue.put(("log", f"ПРОПУЩЕНО {source.name}: {error}"))
                        else:
                            ok += 1
                            self.ui_queue.put(("log", f"OK {source.name} → {out}"))
                    except Exception as exc:
                        errors += 1
                        self.ui_queue.put(("log", f"ОШИБКА {source.name}: {exc}"))
                    completed += 1
                    self.ui_queue.put(("progress", completed, len(files), source.name))

            self.ui_queue.put(("done", ok, errors, self.cancel_requested))
        except Exception:
            self.ui_queue.put(("error", traceback.format_exc()))

    def process_ui_queue(self):
        try:
            while True:
                event = self.ui_queue.get_nowait()
                kind = event[0]
                if kind == "preview":
                    self.show_preview(event[1], event[2])
                elif kind == "log":
                    self.write_log(event[1])
                elif kind == "progress":
                    done, total, name = event[1:]
                    self.progress["value"] = done
                    self.status.set(f"Обработка {done} из {total}: {name}")
                elif kind == "done":
                    ok, errors, stopped = event[1:]
                    self.start_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.selected_files = []
                    self.status.set(f"Готово. Успешно: {ok}; ошибок: {errors}")
                    title = "Обработка остановлена" if stopped else "Пакет завершён"
                    messagebox.showinfo(title, f"Успешно: {ok}\nОшибок: {errors}")
                elif kind == "error":
                    self.start_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.status.set("Ошибка")
                    messagebox.showerror("Ошибка", event[1])
        except queue.Empty:
            pass
        self.after(100, self.process_ui_queue)

    def request_cancel(self):
        self.cancel_requested = True
        self.status.set("Остановка после текущих фотографий…")

    def open_output(self):
        path = Path(self.output_var.get())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def write_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def settings_payload(self):
        return {
            "input": self.input_var.get(),
            "output": self.output_var.get(),
            "background_choice": self.bg_choice_var.get(),
            "background_path": self.bg_var.get(),
            "size": self.size_var.get(),
            "fill": self.fill_var.get(),
            "format": self.format_var.get(),
            "logo_enabled": self.logo_enabled.get(),
            "shadow_enabled": self.shadow_enabled.get(),
            "shadow_strength": self.shadow_strength_var.get(),
            "recursive": self.recursive_enabled.get(),
            "cleanup": self.cleanup_var.get(),
            "edge_expand": self.edge_expand_var.get(),
            "sharpness": self.sharpness_var.get(),
            "straighten": self.straighten_var.get(),
            "workers": self.workers_var.get(),
        }

    def save_settings(self, silent=False):
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self.settings_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if not silent:
                self.status.set("Настройки сохранены")
        except Exception as exc:
            if not silent:
                messagebox.showerror("Ошибка", str(exc))

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
            self.logo_enabled.set(bool(data.get("logo_enabled", False)))
            self.shadow_enabled.set(bool(data.get("shadow_enabled", True)))
            self.shadow_strength_var.set(int(data.get("shadow_strength", 35)))
            self.recursive_enabled.set(bool(data.get("recursive", True)))
            self.cleanup_var.set(int(data.get("cleanup", 45)))
            self.edge_expand_var.set(int(data.get("edge_expand", 1)))
            self.sharpness_var.set(int(data.get("sharpness", 45)))
            self.straighten_var.set(bool(data.get("straighten", True)))
            self.workers_var.set(int(data.get("workers", 2)))

            choice = data.get("background_choice", "Фон 1 — Cheviplus")
            path = data.get("background_path", str(DEFAULT_BG_1))
            if choice in BUILTIN_BACKGROUNDS:
                self.bg_choice_var.set(choice)
                self.bg_var.set(str(BUILTIN_BACKGROUNDS[choice]))
            elif Path(path).exists():
                self.bg_choice_var.set("Свой фон…")
                self.bg_var.set(path)
        except Exception:
            self.status.set("Настройки по умолчанию")

    def reset_settings(self):
        self.size_var.set("2000")
        self.fill_var.set(0.86)
        self.format_var.set("JPG")
        self.logo_enabled.set(False)
        self.shadow_enabled.set(True)
        self.shadow_strength_var.set(35)
        self.recursive_enabled.set(True)
        self.cleanup_var.set(45)
        self.edge_expand_var.set(1)
        self.sharpness_var.set(45)
        self.straighten_var.set(True)
        self.workers_var.set(2)
        self.bg_choice_var.set("Фон 1 — Cheviplus")
        self.bg_var.set(str(DEFAULT_BG_1))
        self.status.set("Настройки сброшены")

    def on_close(self):
        self.save_settings(silent=True)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
