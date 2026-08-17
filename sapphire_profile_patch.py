"""Sapphire branding and confirmed 1C export profile.

Confirmed in the user's real 1C loader:
- 1280x960 pixels
- 4:3
- RGB JPEG
- JPEG quality 90
- no obsolete 100 KB cap

These values are now treated as a protected 1C preset so branch users cannot
accidentally return to the incompatible 1024x685/1024x768 profiles.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import app

SAPPHIRE_BG = app.APP_DIR / "sapphire_background.png"
ONE_C_PROFILE = "1С — 1280×960, 4:3, JPG (проверено)"
APP_VERSION = "5.14"
APP_BUILD = "2026.08.17.01"
ONE_C_WIDTH = 1280
ONE_C_HEIGHT = 960
ONE_C_QUALITY = 90


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


def _set_confirmed_1c(self):
    self.profile_var.set(ONE_C_PROFILE)
    self.width_var.set(str(ONE_C_WIDTH))
    self.height_var.set(str(ONE_C_HEIGHT))
    self.format_var.set("JPG")
    self.target_kb_var.set("0")
    self.jpeg_quality_var.set(str(ONE_C_QUALITY))


def _force_confirmed_1c_defaults(self):
    old_load_settings(self)
    profile = self.profile_var.get()
    if profile.startswith("1С —") or profile not in app.EXPORT_PROFILES:
        _set_confirmed_1c(self)


def _confirmed_reset(self):
    old_reset_settings(self)
    _set_confirmed_1c(self)


def apply():
    for name in list(app.EXPORT_PROFILES):
        if name.startswith("1С —"):
            app.EXPORT_PROFILES.pop(name, None)
    app.EXPORT_PROFILES = {
        ONE_C_PROFILE: {
            "width": ONE_C_WIDTH,
            "height": ONE_C_HEIGHT,
            "format": "JPG",
            "target_kb": 0,
            "quality": ONE_C_QUALITY,
        },
        **app.EXPORT_PROFILES,
    }

    original_build = app.App._build
    def build_with_1c_defaults(self):
        original_build(self)
        _set_confirmed_1c(self)
    app.App._build = build_with_1c_defaults

    global old_load_settings, old_reset_settings
    old_load_settings = app.App.load_settings
    old_reset_settings = app.App.reset_settings
    app.App.load_settings = _force_confirmed_1c_defaults
    app.App.reset_settings = _confirmed_reset

    bg=ensure_sapphire_background()
    app.DEFAULT_BACKGROUND_NAMES["Фон 3 — Сапфир"]=bg
    app.BUILTIN_BACKGROUNDS=app.discover_backgrounds()
    app.BUILTIN_BACKGROUNDS["Фон 3 — Сапфир"]=bg

    # Visible version for this tested branch.
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD


apply()
