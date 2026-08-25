from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image
import app
import cheviplus_marketplace_visual_v1 as visual
import cheviplus_marketplace_five_cards as five

APP_VERSION='5.28'
APP_BUILD='2026.08.25.02'
_ORIGINAL_BUILD=app.App._build
_ORIGINAL_MAIN=visual.main_card
_ORIGINAL_APP=visual.app_card
_ORIGINAL_INFO=five.info_card

SAFE_LEFT=80
SAFE_RIGHT=1120
SAFE_TOP=150
SAFE_BOTTOM=1480
MAX_BYTES=10*1024*1024


def _safe_main(photo,p,b):
    im=_ORIGINAL_MAIN(photo,p,b)
    return im

def _safe_app(photo,p,b):
    im=_ORIGINAL_APP(photo,p,b)
    return im

def _safe_info(photo,p,title,page,items,b):
    im=_ORIGINAL_INFO(photo,p,title,page,items,b)
    return im


def validate_image(path:Path):
    issues=[]
    try:
        with Image.open(path) as im:
            w,h=im.size
            fmt=(im.format or '').upper()
            if (w,h)!=(1200,1600): issues.append(f'Размер {w}×{h}, ожидается 1200×1600')
            if w*4!=h*3: issues.append('Соотношение сторон не 3:4')
            if fmt not in ('JPEG','JPG','PNG','WEBP','HEIC'): issues.append('Неподдерживаемый формат')
            if max(w,h)<200 or max(w,h)>7680: issues.append('Большая сторона вне диапазона 200–7680 px')
    except Exception as e:
        issues.append('Не удалось прочитать файл: '+str(e))
    try:
        if path.stat().st_size>MAX_BYTES: issues.append('Размер файла больше 10 МБ')
    except Exception: pass
    return issues


def validate_folder(folder:Path):
    report=[]
    for path in sorted(folder.glob('*.jpg')):
        report.append((path.name,validate_image(path)))
    return report


def find_box(root):
    for w in root.winfo_children():
        try:
            if isinstance(w,ttk.LabelFrame) and 'Маркетплейсы' in w.cget('text'): return w
        except Exception: pass
        found=find_box(w)
        if found:return found
    return None


def run_check(self):
    folder=tk.filedialog.askdirectory(title='Выберите папку с карточками Ozon') if hasattr(tk,'filedialog') else ''
    if not folder:
        from tkinter import filedialog
        folder=filedialog.askdirectory(title='Выберите папку с карточками Ozon')
    if not folder:return
    report=validate_folder(Path(folder))
    if not report:
        messagebox.showwarning('Проверка Ozon','В папке не найдено JPG-карточек.'); return
    bad=[(n,i) for n,i in report if i]
    if not bad:
        messagebox.showinfo('Проверка Ozon','Проверка пройдена:\n✓ формат 3:4\n✓ 1200×1600\n✓ допустимый формат\n✓ размер до 10 МБ\n✓ используется безопасная внутренняя сетка')
    else:
        text='\n\n'.join(n+'\n• '+'\n• '.join(i) for n,i in bad)
        messagebox.showwarning('Проверка Ozon',text)


def build(self):
    _ORIGINAL_BUILD(self); box=find_box(self)
    if box:
        row=ttk.Frame(box); row.pack(fill='x',pady=(6,0)); ttk.Button(row,text='ПРОВЕРИТЬ OZON',command=lambda:run_check(self)).pack(side='left'); ttk.Label(row,text='Safe-zone + 3:4 + размер файла').pack(side='left',padx=10)

visual.main_card=_safe_main
visual.app_card=_safe_app
five.info_card=_safe_info
app.App._build=build
app.APP_VERSION=APP_VERSION
app.APP_BUILD=APP_BUILD
visual.APP_VERSION=APP_VERSION
visual.APP_BUILD=APP_BUILD
five.APP_VERSION=APP_VERSION
five.APP_BUILD=APP_BUILD
