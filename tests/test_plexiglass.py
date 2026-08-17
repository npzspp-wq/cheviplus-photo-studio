from pathlib import Path

from PIL import Image

import cheviplus_plexiglass as plexi


def _sample(tmp_path, size=(1280, 960)):
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", size, (230, 230, 230)).save(bg)
    image = Image.new("RGBA", size, (230, 230, 230, 255))
    w, h = size
    for x in range(int(w * 0.35), int(w * 0.65)):
        for y in range(int(h * 0.30), int(h * 0.65)):
            image.putpixel((x, y), (80, 90, 100, 255))
    return bg, image


def test_plexiglass_keeps_dimensions(tmp_path):
    bg, image = _sample(tmp_path)
    out = plexi.apply_plexiglass_effect(image, Path(bg), plexi.DEFAULT_INTENSITY)
    assert out.size == (1280, 960)


def test_zero_intensity_direct_effect_is_noop(tmp_path):
    bg, image = _sample(tmp_path, (640, 480))
    out = plexi.apply_plexiglass_effect(image, Path(bg), 0)
    assert list(out.getdata()) == list(image.getdata())


def test_enabled_zero_is_promoted_to_visible_default(monkeypatch, tmp_path):
    bg, image = _sample(tmp_path, (640, 480))
    monkeypatch.setattr(plexi, "_ORIGINAL_COMPOSE", lambda *args, **kwargs: image.copy())
    out = plexi.compose_with_plexiglass(
        Path("sample.jpg"),
        background_path=Path(bg),
        plexiglass_enabled=True,
        plexiglass_intensity=0,
    )
    assert list(out.getdata()) != list(image.getdata())
