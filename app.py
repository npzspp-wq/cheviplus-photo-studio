
import os
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageFilter, ImageEnhance

def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_BG = resource_path("assets/background_cheviplus.jpg")
DEFAULT_LOGO = resource_path("assets/logo_cheviplus.png")
MODEL_DIR = resource_path("models")
os.environ["U2NET_HOME"] = str(MODEL_DIR)
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

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

def remove_background(img: Image.Image):
    from rembg import remove
    return remove(img.convert("RGBA"), session=get_rembg_session(), alpha_matting=False)

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

    # Gentle correction, without changing chrome/material appearance too much
    product_rgb = ImageEnhance.Contrast(product.convert("RGB")).enhance(1.03)
    product = Image.merge("RGBA", (*product_rgb.split(), product.getchannel("A")))

    bg = Image.open(background_path).convert("RGB")
    bg = fit_cover(bg, (canvas_size, canvas_size)).convert("RGBA")

    max_w = int(canvas_size * product_fill)
    max_h = int(canvas_size * product_fill)
    ratio = min(max_w / product.width, max_h / product.height)
    new_size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    product = product.resize(new_size, Image.Resampling.LANCZOS)

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
        self.title("Cheviplus Photo Studio")
        self.geometry("820x650")
        self.minsize(760, 600)
        self.configure(bg="#f4f6f8")
        self._build()

    def _build(self):
        title = tk.Label(
            self, text="CHEVIPLUS PHOTO STUDIO",
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
        self.bg_var = tk.StringVar(value=str(DEFAULT_BG))
        self.logo_var = tk.StringVar(value=str(DEFAULT_LOGO))
        self.size_var = tk.StringVar(value="2000")
        self.fill_var = tk.DoubleVar(value=0.86)
        self.format_var = tk.StringVar(value="JPG")
        self.logo_enabled = tk.BooleanVar(value=True)
        self.shadow_enabled = tk.BooleanVar(value=True)

        self._path_row(form, 0, "Папка с исходными фото:", self.input_var, True)
        self._path_row(form, 1, "Папка для готовых фото:", self.output_var, True)
        self._path_row(form, 2, "Фирменный фон:", self.bg_var, False)
        self._path_row(form, 3, "Логотип PNG:", self.logo_var, False)

        opts = ttk.LabelFrame(self, text="Настройки", padding=14)
        opts.pack(fill="x", padx=24, pady=14)

        ttk.Label(opts, text="Размер изображения:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.size_var, values=("1200", "1600", "2000", "2500", "3000"), width=10, state="readonly").grid(row=0, column=1, padx=8)

        ttk.Label(opts, text="Формат:").grid(row=0, column=2, sticky="w", padx=(25,0))
        ttk.Combobox(opts, textvariable=self.format_var, values=("JPG", "PNG", "WEBP"), width=10, state="readonly").grid(row=0, column=3, padx=8)

        ttk.Checkbutton(opts, text="Добавить логотип", variable=self.logo_enabled).grid(row=1, column=0, sticky="w", pady=(12,0))
        ttk.Checkbutton(opts, text="Добавить мягкую тень", variable=self.shadow_enabled).grid(row=1, column=1, columnspan=2, sticky="w", pady=(12,0))

        ttk.Label(opts, text="Масштаб товара:").grid(row=2, column=0, sticky="w", pady=(12,0))
        ttk.Scale(opts, from_=0.60, to=0.94, variable=self.fill_var, orient="horizontal", length=250).grid(row=2, column=1, columnspan=2, sticky="w", pady=(12,0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=24)
        self.start_btn = tk.Button(
            actions, text="ОБРАБОТАТЬ ВСЕ ФОТО",
            command=self.start, font=("Segoe UI", 12, "bold"),
            bg="#c71920", fg="white", activebackground="#9f1319",
            relief="flat", padx=24, pady=12, cursor="hand2"
        )
        self.start_btn.pack(side="left")
        ttk.Button(actions, text="Открыть папку результата", command=self.open_output).pack(side="left", padx=12)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=24, pady=(18, 8))
        self.status = tk.StringVar(value="Готово к работе")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=24)

        log_frame = ttk.LabelFrame(self, text="Журнал", padding=8)
        log_frame.pack(fill="both", expand=True, padx=24, pady=12)
        self.log = tk.Text(log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _path_row(self, parent, row, label, variable, folder):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable, width=70).grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        cmd = (lambda: self.choose_folder(variable)) if folder else (lambda: self.choose_file(variable))
        ttk.Button(parent, text="Выбрать", command=cmd).grid(row=row, column=2, pady=6)
        parent.columnconfigure(1, weight=1)

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
        if not inp.exists():
            messagebox.showerror("Ошибка", "Папка с исходными фотографиями не найдена.")
            return
        files = [p for p in inp.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED]
        if not files:
            messagebox.showwarning("Нет фотографий", "В выбранной папке нет поддерживаемых изображений.")
            return
        if not Path(self.bg_var.get()).exists():
            messagebox.showerror("Ошибка", "Файл фона не найден.")
            return

        self.start_btn.config(state="disabled")
        self.progress["maximum"] = len(files)
        self.progress["value"] = 0
        self.log.delete("1.0", "end")
        threading.Thread(target=self._worker, args=(files,), daemon=True).start()

    def _worker(self, files):
        ok = 0
        errors = 0
        try:
            for i, source in enumerate(files, 1):
                self.status.set(f"Обработка {i} из {len(files)}: {source.name}")
                try:
                    out = process_one(
                        source=source,
                        output_dir=Path(self.output_var.get()),
                        background_path=Path(self.bg_var.get()),
                        logo_path=Path(self.logo_var.get()),
                        canvas_size=int(self.size_var.get()),
                        product_fill=float(self.fill_var.get()),
                        add_logo=bool(self.logo_enabled.get()),
                        shadow=bool(self.shadow_enabled.get()),
                        output_format=self.format_var.get(),
                    )
                    ok += 1
                    self.write_log(f"OK  {source.name} → {out.name}")
                except Exception as exc:
                    errors += 1
                    self.write_log(f"ОШИБКА  {source.name}: {exc}")
                self.progress["value"] = i
            self.status.set(f"Готово. Успешно: {ok}; ошибок: {errors}")
            messagebox.showinfo("Обработка завершена", f"Готово.\nУспешно: {ok}\nОшибок: {errors}")
        except Exception:
            self.write_log(traceback.format_exc())
            messagebox.showerror("Ошибка", "Произошла непредвиденная ошибка. Смотрите журнал.")
        finally:
            self.start_btn.config(state="normal")

if __name__ == "__main__":
    App().mainloop()
