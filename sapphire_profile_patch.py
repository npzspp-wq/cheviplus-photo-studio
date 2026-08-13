"""Sapphire branding and approved 1C export profile for the 5.9 application."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import app

SAPPHIRE_BG = app.APP_DIR / "sapphire_background.png"


def _font(size: int, bold: bool = True):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_mark(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0):
    navy=(12,42,82); blue=(22,73,139); s=int(58*scale)
    outer=[(x,y+s//2),(x+s//4,y),(x+3*s//4,y),(x+s,y+s//4),(x+s,y+3*s//4),(x+3*s//4,y+s),(x+s//4,y+s),(x,y+3*s//4)]
    draw.polygon(outer,fill=navy)
    inner=[(x+s//4,y+s//3),(x+s//2,y+s//6),(x+3*s//4,y+s//3),(x+3*s//4,y+s//2),(x+s//2,y+2*s//3),(x+s//3,y+s//2)]
    draw.polygon(inner,fill=(247,248,249))
    draw.polygon([(x+s//2,y+s//6),(x+3*s//4,y+s//3),(x+3*s//4,y+s//2),(x+s//2,y+s//2)],fill=blue)
    draw.text((x+s+14*scale,y+8*scale),"САПФИР",font=_font(int(38*scale),True),fill=navy)


def ensure_sapphire_background(path: Path = SAPPHIRE_BG):
    try:
        if path.exists(): return path
        img=Image.new("RGB",(1600,1200),(247,248,249)); draw=ImageDraw.Draw(img)
        for row_i,y in enumerate([70,330,590,850,1110]):
            offset=-120 if row_i%2 else 50
            for x in range(offset,1600,410): _draw_mark(draw,x,y,0.82)
        img.save(path,"PNG",optimize=True)
    except Exception:
        pass
    return path


def apply():
    # Replace the obsolete 1024x685 preset with the approved true 4:3 1C standard.
    app.EXPORT_PROFILES.pop("1С — 1024×685, JPG до 100 КБ",None)
    profile_name="1С — 1024×768, 4:3, JPG"
    app.EXPORT_PROFILES={
        profile_name:{"width":1024,"height":768,"format":"JPG","target_kb":0,"quality":90},
        **app.EXPORT_PROFILES,
    }
    bg=ensure_sapphire_background()
    app.DEFAULT_BACKGROUND_NAMES["Фон 3 — Сапфир"]=bg
    app.BUILTIN_BACKGROUNDS=app.discover_backgrounds()
    app.BUILTIN_BACKGROUNDS["Фон 3 — Сапфир"]=bg


apply()
