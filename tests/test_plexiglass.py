from pathlib import Path

from PIL import Image, ImageDraw

import cheviplus_plexiglass as plexi


def _product(size=(300, 180)):
    product = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((10, 10, size[0] - 10, size[1] - 10), radius=28, fill=(100, 110, 120, 255))
    draw.ellipse((80, 35, 220, 165), fill=(210, 150, 30, 255))
    return product


def test_plexiglass_keeps_dimensions():
    base = Image.new("RGBA", (1280, 960), (235, 235, 235, 255))
    product = _product()
    out = plexi.apply_plexiglass_from_product(base, product, 490, 360, plexi.DEFAULT_INTENSITY)
    assert out.size == (1280, 960)


def test_zero_intensity_direct_effect_is_noop():
    base = Image.new("RGBA", (640, 480), (240, 240, 240, 255))
    product = _product((180, 110))
    out = plexi.apply_plexiglass_from_product(base, product, 230, 180, 0)
    assert list(out.getdata()) == list(base.getdata())


def test_visible_reflection_changes_pixels_below_product():
    base = Image.new("RGBA", (640, 480), (240, 240, 240, 255))
    product = _product((180, 110))
    x, y = 230, 180
    out = plexi.apply_plexiglass_from_product(base, product, x, y, 45)
    contact_y = y + product.height + 20
    assert out.getpixel((x + product.width // 2, contact_y)) != base.getpixel((x + product.width // 2, contact_y))


def test_enabled_zero_is_promoted_to_visible_default(monkeypatch):
    base = Image.new("RGBA", (640, 480), (240, 240, 240, 255))
    product = _product((180, 110))
    monkeypatch.setattr(plexi, "_ORIGINAL_COMPOSE", lambda *args, **kwargs: base.copy())
    monkeypatch.setattr(plexi, "_rebuild_product_cutout", lambda source, options: (product, 230, 180))
    out = plexi.compose_with_plexiglass(
        Path("sample.jpg"),
        plexiglass_enabled=True,
        plexiglass_intensity=0,
        canvas_width=640,
        canvas_height=480,
    )
    assert list(out.getdata()) != list(base.getdata())
