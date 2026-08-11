"""Generate bright Cheviplus Photo Studio Windows branding assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def font(size, bold=False):
    for name in ("arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_icon(size=512):
    s = size / 512.0
    def x(v): return int(v * s)
    # Transparent outside corners make the Windows icon cleaner and larger visually.
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((x(14), x(14), x(498), x(498)), radius=x(92), fill=(0, 166, 255, 135))
    glow = glow.filter(ImageFilter.GaussianBlur(x(14)))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)

    # Much brighter blue tile and thick silver/white frame for taskbar visibility.
    d.rounded_rectangle((x(18), x(18), x(494), x(494)), radius=x(88), fill=(18, 105, 190, 255), outline=(250, 253, 255, 255), width=x(16))
    d.rounded_rectangle((x(42), x(42), x(470), x(470)), radius=x(70), fill=(8, 66, 135, 255), outline=(55, 210, 255, 255), width=x(9))

    # Camera is enlarged and lightened so it remains readable at 16/24/32 px.
    d.rounded_rectangle((x(72), x(154), x(432), x(370)), radius=x(34), fill=(205, 218, 232, 255), outline=(255, 255, 255, 255), width=x(8))
    d.polygon([(x(120),x(154)),(x(168),x(103)),(x(275),x(103)),(x(316),x(154))], fill=(226,235,245,255), outline=(255,255,255,255))
    d.ellipse((x(365),x(176),x(401),x(212)), fill=(35, 143, 224, 255), outline=(255,255,255,255), width=x(3))

    lens_glow = Image.new("RGBA", im.size, (0,0,0,0))
    lg = ImageDraw.Draw(lens_glow)
    lg.ellipse((x(126),x(148),x(366),x(388)), fill=(0,190,255,150))
    lens_glow = lens_glow.filter(ImageFilter.GaussianBlur(x(22)))
    im.alpha_composite(lens_glow)
    d = ImageDraw.Draw(im)
    d.ellipse((x(136),x(158),x(356),x(378)), fill=(235,244,252,255), outline=(255,255,255,255), width=x(7))
    d.ellipse((x(154),x(176),x(338),x(360)), fill=(35,137,218,255), outline=(5,70,145,255), width=x(12))
    d.ellipse((x(179),x(201),x(313),x(335)), fill=(5,42,94,255))
    d.ellipse((x(202),x(224),x(290),x(312)), fill=(0,130,225,255))
    d.ellipse((x(221),x(243),x(271),x(293)), fill=(222,250,255,255))

    # Strong white focus marks.
    c=(255,255,255,255); w=x(11)
    for pts in [((72,121),(72,70),(123,70)),((389,70),(440,70),(440,121)),((72,391),(72,442),(123,442)),((389,442),(440,442),(440,391))]:
        d.line([(x(a),x(b)) for a,b in pts], fill=c, width=w, joint="curve")

    # Large AI badge instead of small dark lettering.
    badge=(x(335),x(340),x(445),x(433))
    d.rounded_rectangle(badge, radius=x(22), fill=(0,119,220,255), outline=(255,255,255,255), width=x(5))
    f=font(x(58), True)
    d.text((x(352),x(351)), "AI", font=f, fill=(255,255,255,255))
    return im


def make_logo(icon):
    w,h=1050,190
    im=Image.new("RGBA",(w,h),(22,31,43,255)); d=ImageDraw.Draw(im)
    d.rectangle((0,h-5,w,h),(0,175,255,255))
    im.alpha_composite(icon.resize((156,156),Image.Resampling.LANCZOS),(18,17))
    d.text((202,34),"CHEVIPLUS",font=font(64,True),fill=(255,255,255,255),stroke_width=1,stroke_fill=(170,190,215,255))
    d.text((207,112),"PHOTO STUDIO",font=font(32,True),fill=(110,215,255,255))
    return im


def main():
    icon=make_icon(512)
    icon.save(ASSETS/"app_icon.png", optimize=True)
    icon.save(ASSETS/"app_icon.ico", format="ICO", sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])
    make_logo(icon).save(ASSETS/"app_logo.png", optimize=True)
    print("Generated bright Windows icon and header logo")


if __name__ == "__main__":
    main()
