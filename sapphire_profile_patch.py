"""Brand backgrounds and the approved 1C/reference photo profile.

Reference set measured 2026-08-14:
- 1280x960 (true 4:3)
- JPEG, 4:2:0
- 72 dpi metadata
- roughly 180-230 KB per photo
- product occupies about 50-55% of the frame, centered with generous margins
"""
from pathlib import Path
import io

from PIL import Image, ImageDraw, ImageFont
import app

SAPPHIRE_BG = app.APP_DIR / "sapphire_background.png"
REFERENCE_PROFILE = "1С — эталон 1280×960, 4:3, JPG до 230 КБ"
LEGACY_1C_PROFILES = {
    "1С — 1024×685, JPG до 100 КБ",
    "1С — 1024×768, 4:3, JPG",
}
REFERENCE_WIDTH = 1280
REFERENCE_HEIGHT = 960
REFERENCE_TARGET_KB = 230
REFERENCE_JPEG_QUALITY = 94
REFERENCE_FILL = 0.55
REFERENCE_SHADOW_STRENGTH = 28
_ORIGINAL_SAVE_RESULT = app.save_result
_ORIGINAL_LOAD_SETTINGS = app.App.load_settings
_ORIGINAL_RESET_SETTINGS = app.App.reset_settings


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


def _apply_reference_values(widget):
    widget.profile_var.set(REFERENCE_PROFILE)
    widget.width_var.set(str(REFERENCE_WIDTH))
    widget.height_var.set(str(REFERENCE_HEIGHT))
    widget.target_kb_var.set(str(REFERENCE_TARGET_KB))
    widget.jpeg_quality_var.set(str(REFERENCE_JPEG_QUALITY))
    widget.fill_var.set(REFERENCE_FILL)
    widget.format_var.set("JPG")
    widget.shadow_enabled.set(True)
    widget.shadow_strength_var.set(REFERENCE_SHADOW_STRENGTH)


def _load_settings_with_reference_migration(self):
    _ORIGINAL_LOAD_SETTINGS(self)
    # Existing installations used one of the older 1C profiles. Migrate those
    # automatically; do not overwrite explicitly chosen Site/Ozon/custom presets.
    current = self.profile_var.get()
    if current in LEGACY_1C_PROFILES or current not in app.EXPORT_PROFILES:
        _apply_reference_values(self)


def _reset_settings_to_reference(self):
    _ORIGINAL_RESET_SETTINGS(self)
    _apply_reference_values(self)


def _save_reference_result(image, source, output_dir, output_format, target_kb=0, jpeg_quality=90):
    """Write reference JPGs with 72-dpi metadata; delegate other formats."""
    fmt = str(output_format).upper()
    if fmt != "JPG":
        return _ORIGINAL_SAVE_RESULT(
            image, source, output_dir, output_format,
            target_kb=target_kb, jpeg_quality=jpeg_quality,
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{source.stem}_cheviplus.jpg"
    rgb = image.convert("RGB")
    quality = max(45, min(95, int(jpeg_quality)))
    target_bytes = int(target_kb * 1024) if target_kb else 0
    best = None
    for q in range(quality, 44, -2):
        buffer = io.BytesIO()
        rgb.save(
            buffer,
            format="JPEG",
            quality=q,
            optimize=True,
            progressive=True,
            subsampling="4:2:0",
            dpi=(72, 72),
        )
        data = buffer.getvalue()
        best = data
        if not target_bytes or len(data) <= target_bytes:
            break
    out.write_bytes(best)
    return out


def apply():
    for name in tuple(LEGACY_1C_PROFILES):
        app.EXPORT_PROFILES.pop(name, None)
    app.EXPORT_PROFILES = {
        REFERENCE_PROFILE: {
            "width": REFERENCE_WIDTH,
            "height": REFERENCE_HEIGHT,
            "format": "JPG",
            "target_kb": REFERENCE_TARGET_KB,
            "quality": REFERENCE_JPEG_QUALITY,
        },
        **app.EXPORT_PROFILES,
    }
    bg=ensure_sapphire_background()
    app.DEFAULT_BACKGROUND_NAMES["Фон 3 — Сапфир"]=bg
    app.BUILTIN_BACKGROUNDS=app.discover_backgrounds()
    app.BUILTIN_BACKGROUNDS["Фон 3 — Сапфир"]=bg
    app.save_result = _save_reference_result
    app.App.load_settings = _load_settings_with_reference_migration
    app.App.reset_settings = _reset_settings_to_reference


apply()
