import io
from pathlib import Path
from PIL import Image

import app
import sapphire_profile_patch as spp


def test_reference_profile_dimensions():
    profile = app.EXPORT_PROFILES[spp.REFERENCE_PROFILE]
    assert profile["width"] == 1280
    assert profile["height"] == 960
    assert profile["target_kb"] == 230
    assert profile["quality"] == 94


def test_reference_jpeg_uses_72_dpi(tmp_path):
    image = Image.new("RGBA", (1280, 960), (240, 240, 240, 255))
    source = Path("sample.jpg")
    out = spp._save_reference_result(image, source, tmp_path, "JPG", 230, 94)
    saved = Image.open(out)
    dpi = saved.info.get("dpi")
    assert saved.size == (1280, 960)
    assert dpi is not None
    assert abs(dpi[0] - 72) < 1 and abs(dpi[1] - 72) < 1
