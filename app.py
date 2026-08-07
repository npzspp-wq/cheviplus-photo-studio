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

APP_VERSION = "4.0"
APP_BUILD = "2026.08.07.01"
SETTINGS_FILE = APP_DIR / "cheviplus_settings.json"
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

EXPORT_PROFILES = {
    "1С — 1024×685, JPG до 100 КБ": {
        "width": 1024,
        "height": 685,
        "format": "JPG",
        "target_kb": 95,
        "quality": 88,
    },
    "Сайт — 1600×1200, JPG": {
        "width": 1600,
        "height": 1200,
        "format": "JPG",
        "target_kb": 350,
        "quality": 90,
    },
    "Ozon / WB — 2000×2000, JPG": {
        "width": 2000,
        "height": 2000,
        "format": "JPG",
        "target_kb": 900,
        "quality": 94,
    },
    "PNG — 2000×2000": {
        "width": 2000,
        "height": 2000,
        "format": "PNG",
        "target_kb": 0,
        "quality": 95,
    },
    "Свои параметры": None,
}

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


def analyze_object_shape(alpha: Image.Image):
    """Определяет форму и рекомендуемые параметры отдельно для каждого фото."""
    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8)
    binary = arr >= 72
    labels, count = ndimage.label(binary)

    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        main_id = int(sizes.argmax())
        main = labels == main_id
    else:
        main = binary

    ys, xs = np.nonzero(main)
    if len(xs) < 50:
        return {
            "kind": "обычный",
            "fill": 0.72,
            "cleanup": 72,
            "edge_expand": 1,
            "opacity_floor": 120,
        }

    width = xs.max() - xs.min() + 1
    height = ys.max() - ys.min() + 1
    aspect = width / max(1, height)
    occupancy = len(xs) / max(1, width * height)

    if aspect >= 3.0:
        kind = "длинный горизонтальный"
        fill = 0.88
    elif aspect <= 0.38:
        kind = "длинный вертикальный"
        fill = 0.84
    elif occupancy < 0.28:
        kind = "тонкий или сложный"
        fill = 0.80
    elif max(width, height) < min(alpha.size) * 0.35:
        kind = "маленький предмет"
        fill = 0.82
    else:
        kind = "обычный"
        fill = 0.73

    return {
        "kind": kind,
        "fill": fill,
        "cleanup": 82,
        "edge_expand": 1 if kind != "тонкий или сложный" else 2,
        "opacity_floor": 138 if kind != "тонкий или сложный" else 112,
    }


def suppress_old_background(alpha: Image.Image, strict=True):
    """
    Удаляет большие полупрозрачные участки старого баннера,
    которые rembg иногда оставляет рядом с предметом.
    Для непрозрачных автозапчастей это безопаснее обычного размытого края.
    """
    if not strict:
        return alpha

    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8)

    # Ядро — только очень уверенные пиксели самого предмета.
    core = arr >= 175
    labels, count = ndimage.label(core)
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        main_id = int(sizes.argmax())
        core = labels == main_id

    # Немного закрываем дырочки внутри основной детали.
    core = ndimage.binary_closing(core, structure=np.ones((3, 3)), iterations=1)
    core = ndimage.binary_fill_holes(core)

    # Разрешаем естественный полупрозрачный край только рядом с уверенным ядром.
    support = arr >= 28
    distance = ndimage.distance_transform_edt(~core)
    near_core = distance <= 5.0
    keep = support & (core | near_core)

    # Отсекаем отдельные куски баннера/логотипа.
    labels, count = ndimage.label(keep)
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        main_id = int(sizes.argmax())
        keep = labels == main_id

    result = np.where(keep, arr, 0).astype(np.uint8)
    # Внутренность предмета делаем непрозрачной, край сохраняем узким.
    result[core] = 255
    result[result < 22] = 0
    return Image.fromarray(result, mode="L")


def harden_alpha(alpha: Image.Image, opacity_floor=128):
    """Не даёт новому фону просвечивать через непрозрачные части товара."""
    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8).astype(np.float32)
    floor = max(70, min(190, int(opacity_floor)))

    # Внутренние области объекта делаем полностью непрозрачными.
    solid = arr >= floor
    solid = ndimage.binary_closing(solid, structure=np.ones((3, 3)), iterations=1)
    solid = ndimage.binary_fill_holes(solid)

    # Сохраняем только узкую полупрозрачную кромку для естественного контура.
    edge_band = ndimage.binary_dilation(solid, iterations=2) & ~ndimage.binary_erosion(solid, iterations=1)
    result = np.zeros_like(arr)
    result[solid] = 255
    result[edge_band] = np.maximum(result[edge_band], arr[edge_band])

    # Всё слабее 25 убираем, чтобы не оставались призраки логотипов.
    result[result < 25] = 0
    return Image.fromarray(result.astype(np.uint8), mode="L")


def remove_isolated_artifacts(rgba: Image.Image, strength=82):
    """Оставляет основной предмет и близкие реальные детали, убирая отдельные логотипы."""
    import numpy as np
    from scipy import ndimage

    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    binary = alpha >= 52
    labels, count = ndimage.label(binary)
    if count <= 1:
        return rgba

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    main_id = int(sizes.argmax())
    main_mask = labels == main_id

    # Разрешаем компоненты, которые находятся близко к основному предмету.
    distance = ndimage.distance_transform_edt(~main_mask)
    keep = main_mask.copy()
    main_size = max(1, int(sizes[main_id]))
    for idx in range(1, count + 1):
        if idx == main_id or sizes[idx] == 0:
            continue
        component = labels == idx
        close = float(distance[component].min()) <= max(12, min(alpha.shape) * 0.025)
        large_enough = sizes[idx] >= main_size * 0.018
        if close and large_enough:
            keep |= component

    cleaned_alpha = np.where(keep, alpha, 0).astype(np.uint8)
    result = rgba.copy()
    result.putalpha(Image.fromarray(cleaned_alpha, mode="L"))
    return result


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


def remove_background(
    img: Image.Image,
    cleanup=45,
    edge_expand=1,
    auto_settings=True,
    prevent_background_showthrough=True,
    strict_logo_cleanup=True,
    solid_object=False,
    solid_hole_limit=8,
):
    from rembg import remove

    result = remove(
        img.convert("RGBA"),
        session=get_rembg_session(),
        alpha_matting=False,
        post_process_mask=False,
    ).convert("RGBA")

    raw_alpha = result.getchannel("A")
    recommendations = analyze_object_shape(raw_alpha)

    if solid_object:
        raw_alpha = reinforce_solid_object_alpha(raw_alpha, hole_limit_percent=solid_hole_limit)

    if auto_settings:
        cleanup = recommendations["cleanup"]
        edge_expand = recommendations["edge_expand"]

    cleaned_alpha = clean_alpha_mask(raw_alpha, cleanup, edge_expand)
    cleaned_alpha = suppress_old_background(
        cleaned_alpha,
        strict=strict_logo_cleanup,
    )
    result.putalpha(cleaned_alpha)
    result = remove_isolated_artifacts(result, strength=cleanup)

    if prevent_background_showthrough:
        opacity_floor = recommendations["opacity_floor"] if auto_settings else 128
        result.putalpha(harden_alpha(result.getchannel("A"), opacity_floor))

    return result, recommendations


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


def remove_product_logo_region(image: Image.Image, strength=55):
    """Осторожно убирает небольшую наклейку в центральной зоне товара."""
    import numpy as np
    from scipy import ndimage
    img=image.convert("RGBA")
    arr=np.asarray(img).copy()
    alpha=arr[...,3]
    ys,xs=np.nonzero(alpha>160)
    if len(xs)<200: return img
    x0,x1=xs.min(),xs.max(); y0,y1=ys.min(),ys.max()
    w=x1-x0+1; h=y1-y0+1
    rx0=int(x0+w*0.24); rx1=int(x0+w*0.76)
    ry0=int(y0+h*0.20); ry1=int(y0+h*0.78)
    crop=arr[ry0:ry1,rx0:rx1,:3].astype(np.float32)
    crop_alpha=alpha[ry0:ry1,rx0:rx1]>180
    mx=crop.max(axis=2); mn=crop.min(axis=2); sat=mx-mn; lum=crop.mean(axis=2)
    suspicious=crop_alpha & ((lum>150) | (sat>78))
    suspicious=ndimage.binary_opening(suspicious,structure=np.ones((3,3)))
    suspicious=ndimage.binary_closing(suspicious,structure=np.ones((5,5)))
    labels,count=ndimage.label(suspicious)
    if count==0: return img
    sizes=np.bincount(labels.ravel()); sizes[0]=0
    region_area=suspicious.size; candidates=[]
    for idx in range(1,count+1):
        size=sizes[idx]
        if size<max(20,region_area*0.0007) or size>region_area*0.16: continue
        yy,xx=np.nonzero(labels==idx)
        if len(xx)==0: continue
        bw=xx.max()-xx.min()+1; bh=yy.max()-yy.min()+1; aspect=bw/max(1,bh)
        if 0.7<=aspect<=6.5: candidates.append((size,idx,xx.min(),xx.max(),yy.min(),yy.max()))
    if not candidates: return img
    _,idx,cx0,cx1,cy0,cy1=max(candidates)
    pad=max(3,int(min(w,h)*(0.005+max(0,min(100,strength))*0.00006)))
    cx0=max(0,cx0-pad); cx1=min(crop.shape[1]-1,cx1+pad)
    cy0=max(0,cy0-pad); cy1=min(crop.shape[0]-1,cy1+pad)
    gy0=max(0,cy0-pad*3); gy1=min(crop.shape[0],cy1+pad*3+1)
    gx0=max(0,cx0-pad*3); gx1=min(crop.shape[1],cx1+pad*3+1)
    surround=crop[gy0:gy1,gx0:gx1]
    mask_local=np.ones(surround.shape[:2],dtype=bool)
    mask_local[cy0-gy0:cy1-gy0+1,cx0-gx0:cx1-gx0+1]=False
    pixels=surround[mask_local]
    if len(pixels)<20: return img
    base=np.median(pixels,axis=0)
    fill=np.empty_like(crop[cy0:cy1+1,cx0:cx1+1]); fill[:]=base
    for c in range(3):
        local_blur=ndimage.gaussian_filter(crop[...,c],sigma=max(3,pad))
        fill[...,c]=local_blur[cy0:cy1+1,cx0:cx1+1]*0.45+base[c]*0.55
    crop[cy0:cy1+1,cx0:cx1+1]=np.clip(fill,0,255)
    arr[ry0:ry1,rx0:rx1,:3]=crop.astype(np.uint8)
    return Image.fromarray(arr,mode="RGBA")



def reinforce_solid_object_alpha(alpha: Image.Image, hole_limit_percent=8):
    """Восстанавливает слабую маску хрома ДО обычной очистки."""
    import numpy as np
    from scipy import ndimage

    arr = np.asarray(alpha, dtype=np.uint8)
    core = arr >= 110
    labels, count = ndimage.label(core)
    if count == 0:
        return alpha
    sizes = np.bincount(labels.ravel()); sizes[0] = 0
    main_id = int(sizes.argmax())
    core = labels == main_id

    weak = arr >= 8
    grown = ndimage.binary_dilation(core, structure=np.ones((5, 5)), iterations=6)
    candidate = weak & grown
    merged = ndimage.binary_closing(core | candidate, structure=np.ones((5, 5)), iterations=2)

    filled = ndimage.binary_fill_holes(merged)
    holes = filled & ~merged
    hlabels, hcount = ndimage.label(holes)
    fill_small = np.zeros_like(holes, dtype=bool)
    main_size = max(1, int(merged.sum()))
    max_hole = main_size * max(1, min(30, int(hole_limit_percent))) / 100.0
    if hcount:
        hs = np.bincount(hlabels.ravel()); hs[0] = 0
        for i in range(1, hcount + 1):
            if 0 < hs[i] <= max_hole:
                fill_small |= (hlabels == i)
    merged |= fill_small

    eroded = ndimage.binary_erosion(merged, structure=np.ones((3, 3)), iterations=1)
    result = arr.copy()
    result[eroded] = 255
    result[fill_small] = 255
    edge = merged & ~eroded
    result[edge] = np.maximum(result[edge], 170)
    result[~merged & (arr < 18)] = 0
    return Image.fromarray(result.astype(np.uint8), mode="L")



def cheviplus_banner_mask(original: Image.Image, alpha: Image.Image):
    import numpy as np
    from scipy import ndimage

    rgb = np.asarray(original.convert("RGB"), dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8)
    h, w, _ = rgb.shape

    # Оцениваем цвет фирменного баннера по внешней рамке снимка.
    b = max(8, int(min(h, w) * 0.05))
    border = np.concatenate([
        rgb[:b].reshape(-1, 3),
        rgb[-b:].reshape(-1, 3),
        rgb[:, :b].reshape(-1, 3),
        rgb[:, -b:].reshape(-1, 3),
    ])
    bg = np.median(border, axis=0)

    # Совмещаем rembg с отличием от баннера.
    diff = np.linalg.norm(rgb - bg[None, None, :], axis=2)
    seed = (a >= 35) | (diff >= 28)

    seed = ndimage.binary_opening(seed, np.ones((3, 3)))
    seed = ndimage.binary_closing(seed, np.ones((7, 7)), iterations=2)

    labels, count = ndimage.label(seed)
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        seed = labels == int(sizes.argmax())

    # Хром/глянец: небольшие внутренние "дыры" закрываем.
    filled = ndimage.binary_fill_holes(seed)
    holes = filled & ~seed
    hole_labels, hole_count = ndimage.label(holes)
    if hole_count:
        sizes = np.bincount(hole_labels.ravel())
        sizes[0] = 0
        max_hole = max(1, int(seed.sum() * 0.12))
        for i in range(1, hole_count + 1):
            if sizes[i] <= max_hole:
                seed |= (hole_labels == i)

    eroded = ndimage.binary_erosion(seed, np.ones((3, 3)), iterations=1)
    edge = seed & ~eroded

    out = np.zeros_like(a)
    out[eroded] = 255
    out[edge] = np.maximum(a[edge], 185)
    return Image.fromarray(out.astype(np.uint8), mode="L")


def compose_image(
    source,
    background_path,
    logo_path,
    canvas_width,
    canvas_height,
    product_fill,
    add_logo,
    shadow,
    shadow_strength,
    cleanup,
    edge_expand,
    sharpness,
    straighten,
    auto_settings,
    prevent_background_showthrough,
    strict_logo_cleanup,
    remove_product_logo,
    logo_remove_strength,
    solid_object,
    solid_hole_limit,
    processing_mode,
):
    original = Image.open(source)
    product, auto_info = remove_background(
        original,
        cleanup=cleanup,
        edge_expand=edge_expand,
        auto_settings=auto_settings,
        prevent_background_showthrough=prevent_background_showthrough,
        strict_logo_cleanup=strict_logo_cleanup,
        solid_object=solid_object,
        solid_hole_limit=solid_hole_limit,
    )
    if processing_mode.startswith("Cheviplus Studio"):
        product.putalpha(
            cheviplus_banner_mask(original, product.getchannel("A"))
        )
    product = trim_transparency(product)

    if auto_settings:
        product_fill = auto_info["fill"]

    if straighten:
        product = trim_transparency(auto_straighten(product))

    if remove_product_logo:
        product = remove_product_logo_region(product, logo_remove_strength)

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

    bg = fit_cover(
        Image.open(background_path).convert("RGB"),
        (canvas_width, canvas_height),
    ).convert("RGBA")

    max_w = int(canvas_width * product_fill)
    max_h = int(canvas_height * product_fill)
    ratio = min(max_w / max(1, product.width), max_h / max(1, product.height))
    new_size = (max(1, int(product.width * ratio)), max(1, int(product.height * ratio)))
    product = product.resize(new_size, Image.Resampling.LANCZOS)

    if sharpness:
        resized_rgb = product.convert("RGB").filter(
            ImageFilter.UnsharpMask(radius=0.55, percent=35 + sharpness, threshold=2)
        )
        product = Image.merge("RGBA", (*resized_rgb.split(), product.getchannel("A")))

    x = (canvas_width - product.width) // 2
    y = int(canvas_height * 0.54 - product.height / 2)
    y = max(20, min(y, canvas_height - product.height - 20))

    if shadow:
        add_shadow(bg, product, (x, y), shadow_strength)
    bg.alpha_composite(product, (x, y))

    if add_logo and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        max_logo_w = int(canvas_width * 0.15)
        scale = min(1.0, max_logo_w / max(1, logo.width))
        logo = logo.resize(
            (max(1, int(logo.width * scale)), max(1, int(logo.height * scale))),
            Image.Resampling.LANCZOS,
        )
        margin = int(min(canvas_width, canvas_height) * 0.025)
        bg.alpha_composite(
            logo,
            (canvas_width - logo.width - margin, canvas_height - logo.height - margin),
        )
    return bg


def save_result(
    image,
    source,
    output_dir,
    output_format,
    target_kb=0,
    jpeg_quality=90,
):
    import io

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem + "_cheviplus"
    fmt = output_format.upper()

    if fmt == "JPG":
        out = output_dir / f"{stem}.jpg"
        rgb = image.convert("RGB")
        quality = max(45, min(95, int(jpeg_quality)))
        target_bytes = int(target_kb * 1024) if target_kb else 0

        if target_bytes:
            best = None
            for q in range(quality, 44, -3):
                buffer = io.BytesIO()
                rgb.save(
                    buffer,
                    format="JPEG",
                    quality=q,
                    optimize=True,
                    progressive=True,
                    subsampling="4:2:0",
                    dpi=(96, 96),
                )
                data = buffer.getvalue()
                best = data
                if len(data) <= target_bytes:
                    break
            out.write_bytes(best)
        else:
            rgb.save(
                out,
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
                dpi=(96, 96),
            )
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
        self.title(f"Cheviplus Photo Studio {APP_VERSION} — Build {APP_BUILD}")
        self.geometry("1280x820")
        self.minsize(980, 640)
        try:
            self.state("zoomed")
        except Exception:
            pass
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
        try:
            folder = Path(self.input_var.get())
            count = sum(
                1 for p in folder.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED
            ) if folder.exists() else 0
            self.selection_info.set(f"Источник: папка ({count} файлов)")
        except Exception:
            pass
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
            text=f"Build {APP_BUILD}  •  Профессиональная пакетная подготовка фотографий",
            font=("Segoe UI", 10),
            fg="#cfd5db",
            bg="#20252b",
        ).pack(side="left", pady=22)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=14, pady=14)

        left_host = ttk.Frame(main)
        right = ttk.Frame(main, padding=10)
        main.add(left_host, weight=3)
        main.add(right, weight=2)

        left_canvas = tk.Canvas(left_host, highlightthickness=0, bg="#f3f5f7")
        left_scroll = ttk.Scrollbar(left_host, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)

        left_scroll.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)

        left = ttk.Frame(left_canvas, padding=10)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_scroll_region(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _sync_left_width(event):
            left_canvas.itemconfigure(left_window, width=event.width)

        def _mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        left.bind("<Configure>", _sync_scroll_region)
        left_canvas.bind("<Configure>", _sync_left_width)
        left_canvas.bind_all("<MouseWheel>", _mousewheel)

        self.input_var = tk.StringVar(value=str(APP_DIR / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "output"))
        self.bg_choice_var = tk.StringVar(value="Фон 1 — Cheviplus")
        self.bg_var = tk.StringVar(value=str(DEFAULT_BG_1))
        self.logo_var = tk.StringVar(value=str(DEFAULT_LOGO))
        self.profile_var = tk.StringVar(value="1С — 1024×685, JPG до 100 КБ")
        self.width_var = tk.StringVar(value="1024")
        self.height_var = tk.StringVar(value="685")
        self.target_kb_var = tk.StringVar(value="95")
        self.jpeg_quality_var = tk.StringVar(value="88")
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
        self.auto_settings_var = tk.BooleanVar(value=False)
        self.prevent_showthrough_var = tk.BooleanVar(value=True)
        self.strict_logo_cleanup_var = tk.BooleanVar(value=False)
        self.remove_product_logo_var = tk.BooleanVar(value=False)
        self.logo_remove_strength_var = tk.IntVar(value=55)
        self.solid_object_var = tk.BooleanVar(value=True)
        self.solid_hole_limit_var = tk.IntVar(value=8)
        self.processing_mode_var = tk.StringVar(value="Cheviplus Studio — старый фирменный баннер")
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
        ttk.Label(basic, text="Режим обработки:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            basic,
            textvariable=self.processing_mode_var,
            values=(
                "Cheviplus Studio — старый фирменный баннер",
                "Хром / глянец",
                "Обычный",
            ),
            state="readonly",
            width=38,
        ).grid(row=0, column=1, columnspan=3, sticky="w", padx=6, pady=(0, 8))

        ttk.Label(basic, text="Профиль экспорта:").grid(row=1, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(
            basic,
            textvariable=self.profile_var,
            values=tuple(EXPORT_PROFILES.keys()),
            state="readonly",
            width=34,
        )
        self.profile_combo.grid(row=1, column=1, columnspan=3, sticky="w", padx=6)
        self.profile_combo.bind("<<ComboboxSelected>>", self.apply_export_profile)

        ttk.Label(basic, text="Потоки:").grid(row=1, column=4, padx=(20, 0))
        ttk.Spinbox(basic, from_=1, to=4, textvariable=self.workers_var, width=5).grid(row=1, column=5)

        ttk.Label(basic, text="Ширина:").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(basic, textvariable=self.width_var, width=9).grid(row=1, column=1, sticky="w", pady=(10, 0))
        ttk.Label(basic, text="Высота:").grid(row=1, column=2, sticky="e", pady=(10, 0))
        ttk.Entry(basic, textvariable=self.height_var, width=9).grid(row=1, column=3, sticky="w", pady=(10, 0))
        ttk.Label(basic, text="Формат:").grid(row=1, column=4, sticky="e", pady=(10, 0))
        ttk.Combobox(
            basic, textvariable=self.format_var,
            values=("JPG", "PNG", "WEBP"),
            width=8, state="readonly"
        ).grid(row=1, column=5, pady=(10, 0))

        ttk.Label(basic, text="Цель, КБ:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.target_kb_var, width=9).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Label(basic, text="Качество JPG:").grid(row=2, column=2, sticky="e", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.jpeg_quality_var, width=9).grid(row=2, column=3, sticky="w", pady=(8, 0))

        ttk.Checkbutton(basic, text="Мягкая тень", variable=self.shadow_enabled).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Автовыравнивание длинных деталей", variable=self.straighten_var).grid(row=3, column=1, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Вложенные папки", variable=self.recursive_enabled).grid(row=3, column=4, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(basic, text="Отдельный логотип поверх фона", variable=self.logo_enabled).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._scale_row(basic, 5, "Масштаб товара", self.fill_var, 0.60, 0.94, lambda v: f"{float(v)*100:.0f}%")
        self._scale_row(basic, 6, "Сила тени", self.shadow_strength_var, 0, 80, lambda v: f"{float(v):.0f}%")

        advanced = ttk.LabelFrame(left, text="3. Автоматическая обработка каждого фото", padding=12)
        advanced.pack(fill="x", pady=(10, 0))

        ttk.Checkbutton(
            advanced,
            text="Автонастройка отдельно для каждого фото",
            variable=self.auto_settings_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        ttk.Checkbutton(
            advanced,
            text="Не допускать просвечивания нового фона через товар",
            variable=self.prevent_showthrough_var,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 4))

        ttk.Checkbutton(
            advanced,
            text="ХРОМ/ГЛЯНЕЦ — восстанавливать непрозрачность до очистки",
            variable=self.solid_object_var,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 4))

        self._scale_row(
            advanced, 3, "Заполнение внутренних дыр",
            self.solid_hole_limit_var, 1, 25, lambda v: f"{float(v):.0f}%"
        )

        ttk.Checkbutton(
            advanced,
            text="Строгая очистка старых логотипов и баннера (необязательно)",
            variable=self.strict_logo_cleanup_var,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 4))

        ttk.Checkbutton(
            advanced,
            text="Удаление логотипа НА ДЕТАЛИ (экспериментально — обычно выключено)",
            variable=self.remove_product_logo_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 4))

        self._scale_row(
            advanced, 6, "Сила удаления логотипа на детали",
            self.logo_remove_strength_var, 0, 100, lambda v: f"{float(v):.0f}"
        )

        ttk.Label(
            advanced,
            text="При включённой автонастройке программа сама выбирает масштаб, очистку и толщину края.",
        ).grid(row=7, column=0, columnspan=5, sticky="w", pady=(0, 8))

        self._scale_row(advanced, 8, "Ручная очистка фона", self.cleanup_var, 0, 100, lambda v: f"{float(v):.0f}")
        self._scale_row(advanced, 9, "Ручное расширение края", self.edge_expand_var, 0, 4, lambda v: f"{float(v):.0f} px")
        self._scale_row(advanced, 10, "Резкость товара", self.sharpness_var, 0, 100, lambda v: f"{float(v):.0f}")

        source_bar = ttk.LabelFrame(left, text="4. Добавить фотографии", padding=10)
        source_bar.pack(fill="x", pady=(10, 0))

        ttk.Button(
            source_bar, text="Выбрать фото",
            command=self.choose_multiple_files
        ).pack(side="left")

        ttk.Button(
            source_bar, text="Выбрать папку",
            command=lambda: self.choose_folder(self.input_var)
        ).pack(side="left", padx=6)

        self.selection_info = tk.StringVar(value="Источник: папка исходных фотографий")
        ttk.Label(source_bar, textvariable=self.selection_info).pack(side="left", padx=12)

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=12)

        ttk.Button(
            actions, text="ПРЕДПРОСМОТР",
            command=self.start_preview
        ).pack(side="left")

        self.start_btn = tk.Button(
            actions,
            text="ОБРАБОТАТЬ",
            command=self.start,
            font=("Segoe UI", 11, "bold"),
            bg="#c71920", fg="white", activebackground="#9f1319",
            relief="flat", padx=22, pady=8, cursor="hand2",
        )
        self.start_btn.pack(side="left", padx=8)

        self.cancel_btn = ttk.Button(
            actions, text="Остановить",
            command=self.request_cancel,
            state="disabled"
        )
        self.cancel_btn.pack(side="left")

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
        ttk.Label(right, text=f"Версия {APP_VERSION}  •  Build {APP_BUILD}", font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(8, 0))

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

    def apply_export_profile(self, _event=None):
        profile = EXPORT_PROFILES.get(self.profile_var.get())
        if not profile:
            return
        self.width_var.set(str(profile["width"]))
        self.height_var.set(str(profile["height"]))
        self.format_var.set(profile["format"])
        self.target_kb_var.set(str(profile["target_kb"]))
        self.jpeg_quality_var.set(str(profile["quality"]))
        self.status.set(f"Выбран профиль: {self.profile_var.get()}")

    def choose_folder(self, variable):
        path = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if path:
            variable.set(path)
            if variable is self.input_var:
                self.selected_files = []
                try:
                    count = sum(
                        1 for p in Path(path).rglob("*")
                        if p.is_file() and p.suffix.lower() in SUPPORTED
                    )
                except Exception:
                    count = 0
                self.selection_info.set(f"Выбрана папка: {count} файлов")
                self.status.set(f"Выбрана папка: {count} файлов")

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
            count = len(self.selected_files)
            self.selection_info.set(f"Выбрано файлов: {count}")
            self.status.set(f"Выбрано файлов: {count}")

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
            canvas_width=max(200, int(self.width_var.get())),
            canvas_height=max(200, int(self.height_var.get())),
            product_fill=float(self.fill_var.get()),
            add_logo=bool(self.logo_enabled.get()),
            shadow=bool(self.shadow_enabled.get()),
            shadow_strength=int(self.shadow_strength_var.get()),
            cleanup=int(self.cleanup_var.get()),
            edge_expand=int(round(self.edge_expand_var.get())),
            sharpness=int(self.sharpness_var.get()),
            straighten=bool(self.straighten_var.get()),
            auto_settings=bool(self.auto_settings_var.get()),
            prevent_background_showthrough=bool(self.prevent_showthrough_var.get()),
            strict_logo_cleanup=bool(self.strict_logo_cleanup_var.get()),
            remove_product_logo=bool(self.remove_product_logo_var.get()),
            logo_remove_strength=int(self.logo_remove_strength_var.get()),
            solid_object=bool(self.solid_object_var.get()),
            solid_hole_limit=int(self.solid_hole_limit_var.get()),
            processing_mode=self.processing_mode_var.get(),
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
        self.write_log(
            "Автонастройка: "
            + ("включена" if self.auto_settings_var.get() else "выключена")
            + "; защита от просвечивания: "
            + ("включена" if self.prevent_showthrough_var.get() else "выключена")
            + "; строгая очистка старого логотипа: "
            + ("включена" if self.strict_logo_cleanup_var.get() else "выключена")
        )
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
            out = save_result(
                image,
                source,
                target_dir,
                self.format_var.get(),
                target_kb=max(0, int(self.target_kb_var.get() or 0)),
                jpeg_quality=max(45, min(95, int(self.jpeg_quality_var.get() or 88))),
            )
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
                    title = "Обработка остановлена" if stopped else "Обработка завершена"
                    messagebox.showinfo(title, f"Обработано: {ok}\nОшибок: {errors}")
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
            "profile": self.profile_var.get(),
            "width": self.width_var.get(),
            "height": self.height_var.get(),
            "target_kb": self.target_kb_var.get(),
            "jpeg_quality": self.jpeg_quality_var.get(),
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
            "auto_settings": self.auto_settings_var.get(),
            "prevent_showthrough": self.prevent_showthrough_var.get(),
            "strict_logo_cleanup": self.strict_logo_cleanup_var.get(),
            "remove_product_logo": self.remove_product_logo_var.get(),
            "logo_remove_strength": self.logo_remove_strength_var.get(),
            "solid_object": self.solid_object_var.get(),
            "solid_hole_limit": self.solid_hole_limit_var.get(),
            "processing_mode": self.processing_mode_var.get(),
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
            self.profile_var.set(data.get("profile", self.profile_var.get()))
            self.width_var.set(str(data.get("width", self.width_var.get())))
            self.height_var.set(str(data.get("height", self.height_var.get())))
            self.target_kb_var.set(str(data.get("target_kb", self.target_kb_var.get())))
            self.jpeg_quality_var.set(str(data.get("jpeg_quality", self.jpeg_quality_var.get())))
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
            self.auto_settings_var.set(bool(data.get("auto_settings", True)))
            self.prevent_showthrough_var.set(bool(data.get("prevent_showthrough", True)))
            self.strict_logo_cleanup_var.set(bool(data.get("strict_logo_cleanup", False)))
            self.remove_product_logo_var.set(bool(data.get("remove_product_logo", False)))
            self.logo_remove_strength_var.set(int(data.get("logo_remove_strength", 55)))
            self.solid_object_var.set(bool(data.get("solid_object", True)))
            self.solid_hole_limit_var.set(int(data.get("solid_hole_limit", 8)))
            self.processing_mode_var.set(data.get("processing_mode", "Cheviplus Studio — старый фирменный баннер"))
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
        self.profile_var.set("1С — 1024×685, JPG до 100 КБ")
        self.width_var.set("1024")
        self.height_var.set("685")
        self.target_kb_var.set("95")
        self.jpeg_quality_var.set("88")
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
        self.auto_settings_var.set(False)
        self.prevent_showthrough_var.set(True)
        self.strict_logo_cleanup_var.set(False)
        self.remove_product_logo_var.set(False)
        self.logo_remove_strength_var.set(55)
        self.solid_object_var.set(True)
        self.solid_hole_limit_var.set(8)
        self.workers_var.set(2)
        self.bg_choice_var.set("Фон 1 — Cheviplus")
        self.bg_var.set(str(DEFAULT_BG_1))
        self.status.set("Настройки сброшены")

    def on_close(self):
        self.save_settings(silent=True)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
