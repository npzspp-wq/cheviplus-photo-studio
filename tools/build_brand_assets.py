"""Generate Cheviplus Photo Studio app icon and header logo.

The assets are generated at build time so the GitHub repository stays text-only.
Design follows the approved dark-blue / chrome / neon-blue camera + AI identity.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def font(size, bold=False):
    names = ["arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_icon(size=512):
    scale = size / 512.0
    im = Image.new("RGBA", (size, size), (4, 13, 31, 255))
    d = ImageDraw.Draw(im)
    def xy(v): return int(v * scale)

    # neon outer glow
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((xy(18), xy(18), xy(494), xy(494)), radius=xy(92), outline=(0, 157, 255, 220), width=xy(14))
    glow = glow.filter(ImageFilter.GaussianBlur(xy(20)))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)

    # chrome frame and blue interior
    d.rounded_rectangle((xy(22), xy(22), xy(490), xy(490)), radius=xy(88), fill=(7, 27, 63, 255), outline=(230, 238, 247, 255), width=xy(12))
    d.rounded_rectangle((xy(43), xy(43), xy(469), xy(469)), radius=xy(70), outline=(0, 174, 255, 255), width=xy(6))

    # camera body
    d.rounded_rectangle((xy(87), xy(159), xy(422), xy(362)), radius=xy(32), fill=(37, 48, 66, 255), outline=(211, 220, 232, 255), width=xy(5))
    d.polygon([(xy(135),xy(159)),(xy(176),xy(112)),(xy(266),xy(112)),(xy(303),xy(159))], fill=(47,59,78,255), outline=(210,220,230,255))
    d.ellipse((xy(365),xy(177),xy(393),xy(205)), fill=(224,230,238,255))

    # lens glow
    lens_glow = Image.new("RGBA", im.size, (0,0,0,0))
    lg = ImageDraw.Draw(lens_glow)
    lg.ellipse((xy(139),xy(155),xy(356),xy(372)), fill=(0,139,255,90))
    lens_glow = lens_glow.filter(ImageFilter.GaussianBlur(xy(25)))
    im.alpha_composite(lens_glow)
    d = ImageDraw.Draw(im)
    for box, color, width in [
        ((145,161,350,366),(221,229,239,255),8),
        ((160,176,335,351),(28,100,176,255),12),
        ((180,196,315,331),(2,19,46,255),0),
        ((198,214,297,313),(0,112,219,255),0),
        ((218,234,277,293),(10,24,58,255),0),
    ]:
        b=tuple(xy(v) for v in box)
        if width: d.ellipse(b, outline=color, width=xy(width))
        else: d.ellipse(b, fill=color)
    d.ellipse((xy(224),xy(238),xy(253),xy(267)), fill=(117,231,255,230))

    # focus corner marks
    c=(235,245,255,255); w=xy(8)
    for pts in [((82,118),(82,78),(122,78)),((390,78),(430,78),(430,118)),((82,394),(82,434),(122,434)),((390,434),(430,434),(430,394))]:
        p=[(xy(a),xy(b)) for a,b in pts]
        d.line(p, fill=c, width=w, joint="curve")

    # AI label
    f=font(xy(72), True)
    d.text((xy(350),xy(352)), "AI", font=f, fill=(255,255,255,255), stroke_width=xy(2), stroke_fill=(0,108,255,255))
    return im


def make_logo(icon):
    w,h=1050,190
    im=Image.new("RGBA",(w,h),(22,31,43,255))
    d=ImageDraw.Draw(im)
    # subtle blue line
    d.rectangle((0,h-5,w,h),(0,145,255,255))
    small=icon.resize((156,156),Image.Resampling.LANCZOS)
    im.alpha_composite(small,(18,17))
    title=font(64,True); sub=font(32,True)
    d.text((202,34),"CHEVIPLUS",font=title,fill=(245,248,252,255),stroke_width=1,stroke_fill=(160,175,195,255))
    d.text((207,112),"PHOTO STUDIO",font=sub,fill=(210,225,242,255))
    return im


def main():
    icon=make_icon(512)
    icon.save(ASSETS/"app_icon.png", optimize=True)
    icon.save(ASSETS/"app_icon.ico", format="ICO", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    make_logo(icon).save(ASSETS/"app_logo.png", optimize=True)
    print("Generated:", ASSETS/"app_icon.ico", ASSETS/"app_icon.png", ASSETS/"app_logo.png")


if __name__ == "__main__":
    main()
