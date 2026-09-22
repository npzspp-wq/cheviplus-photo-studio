from pathlib import Path

from PIL import Image, ImageDraw

import cheviplus_plexiglass as plexi


def _product(size=(300, 180)):
    product = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((10, 10, size[0] - 10, size[1] - 10), radius=28, fill=(100, 110, 120, 255))
    draw.ellipse((80, 35, min(220, size[0]-20), min(165, size[1]-20)), fill=(210, 150, 30, 255))
    return product


def test_reflection_keeps_dimensions():
    base = Image.new("RGBA", (1280, 960), (235, 235, 235, 255))
    product = _product()
    out = plexi.apply_plexiglass_from_product(base, product, 490, 360, plexi.DEFAULT_INTENSITY)
    assert out.size == (1280, 960)


def test_zero_intensity_reflection_layer_is_subtle_but_valid():
    product = _product((180, 110))
    layer = plexi._reflection_layer(product, (640, 480), 230, 180, 0)
    assert layer.size == (640, 480)


def test_table_background_is_registered():
    assert plexi.TABLE_BACKGROUND_NAME in plexi.app.BUILTIN_BACKGROUNDS


def test_generated_table_background_exists():
    assert Path(plexi.app.BUILTIN_BACKGROUNDS[plexi.TABLE_BACKGROUND_NAME]).exists()


def test_table_placement_contact_line(monkeypatch):
    product = _product((400, 240))
    monkeypatch.setattr(plexi.aq, "remove_background", lambda original, **kwargs: (product.copy(), {"fill": 0.73}))
    monkeypatch.setattr(plexi.Image, "open", lambda source: Image.new("RGB", (800, 600), "white") if str(source) == "dummy.jpg" else Image.open(source))


def test_reflection_visible_below_product():
    base = Image.new("RGBA", (640, 480), (240, 240, 240, 255))
    product = _product((180, 110))
    x, y = 230, 180
    out = plexi.apply_plexiglass_from_product(base, product, x, y, 45)
    contact_y = min(479, y + product.height + 20)
    assert out.getpixel((x + product.width // 2, contact_y)) != base.getpixel((x + product.width // 2, contact_y))
