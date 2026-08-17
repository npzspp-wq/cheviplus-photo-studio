"""Sapphire branding and confirmed 1C export profile.

The 1C profile is based on a real JPEG accepted by the user's 1C photo loader:
1280x960 pixels, 4:3, RGB JPEG.  Do not impose the obsolete 100 KB target because
the accepted reference is about 194 KB.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import app

SAPPHIRE_BG = app.APP_DIR / "sapphire_background.png"
ONE_C_PROFILE = "1С — 1280×960, 4:3, JPG (проверено)"


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


def _force_confirmed_1c_defaults(self):
    """Keep old saved 1C presets from restoring incompatible dimensions."""
    old_load_settings(self)
    profile = self.profile_var.get()
    obsolete = profile.startswith("1С — 1024×685") or profile.startswith("1С — 1024×768")
    if obsolete:
        self.profile_var.set(ONE_C_PROFILE)
        self.width_var.set("1280")
        self.height_var.set("960")
        self.format_var.set("JPG")
        self.target_kb_var.set("0")
        self.jpeg_quality_var.set("90")


def _confirmed_reset(self):
    old_reset_settings(self)
    self.profile_var.set(ONE_C_PROFILE)
    self.width_var.set("1280")
    self.height_var.set("960")
    self.format_var.set("JPG")
    self.target_kb_var.set("0")
    self.jpeg_quality_var.set("90")


def apply():
    # Remove every obsolete 1C profile and make the accepted 1280x960 profile first.
    for name in list(app.EXPORT_PROFILES):
        if name.startswith("1С —"):
            app.EXPORT_PROFILES.pop(name, None)
    app.EXPORT_PROFILES = {
        ONE_C_PROFILE: {
            "width": 1280,
            "height": 960,
            "format": "JPG",
            "target_kb": 0,
            "quality": 90,
        },
        **app.EXPORT_PROFILES,
    }

    # New installations start directly with the confirmed 1C settings.
    original_build = app.App._build
    def build_with_1c_defaults(self):
        original_build(self)
        self.profile_var.set(ONE_C_PROFILE)
        self.width_var.set("1280")
        self.height_var.set("960")
        self.format_var.set("JPG")
        self.target_kb_var.set("0")
        self.jpeg_quality_var.set("90")
    app.App._build = build_with_1c_defaults

    # Existing settings created by old builds are migrated automatically.
    global old_load_settings, old_reset_settings
    old_load_settings = app.App.load_settings
    old_reset_settings = app.App.reset_settings
    app.App.load_settings = _force_confirmed_1c_defaults
    app.App.reset_settings = _confirmed_reset

    bg=ensure_sapphire_background()
    app.DEFAULT_BACKGROUND_NAMES["Фон 3 — Сапфир"]=bg
    app.BUILTIN_BACKGROUNDS=app.discover_backgrounds()
    app.BUILTIN_BACKGROUNDS["Фон 3 — Сапфир"]=bg


apply()
