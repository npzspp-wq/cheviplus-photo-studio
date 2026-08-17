from pathlib import Path

from PIL import Image

import cheviplus_plexiglass as plexi


def test_plexiglass_keeps_dimensions(tmp_path):
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (1280, 960), (230, 230, 230)).save(bg)
    image = Image.new("RGBA", (1280, 960), (230, 230, 230, 255))
    # Add a central foreground block so mask detection has a subject.
    for x in range(450, 830):
        for y in range(300, 620):
            image.putpixel((x, y), (80, 90, 100, 255))
    out = plexi.apply_plexiglass_effect(image, Path(bg), 25)
    assert out.size == (1280, 960)


def test_zero_intensity_is_noop(tmp_path):
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (640, 480), (240, 240, 240)).save(bg)
    image = Image.new("RGBA", (640, 480), (240, 240, 240, 255))
    out = plexi.apply_plexiglass_effect(image, Path(bg), 0)
    assert list(out.getdata()) == list(image.getdata())
