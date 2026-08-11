import tempfile
import unittest
from pathlib import Path

from PIL import Image

import cheviplus_ai_quality as aq


class AIQualityTests(unittest.TestCase):
    def test_modes_are_explicit(self):
        self.assertIn(aq.MODE_AUTO, aq.MODES)
        self.assertIn(aq.MODE_FAST, aq.MODES)
        self.assertIn(aq.MODE_QUALITY, aq.MODES)
        self.assertEqual(len(set(aq.MODES)), 3)

    def test_quality_session_model_name_is_birefnet_lite(self):
        source = aq.get_quality_session.__code__.co_consts
        self.assertIn("birefnet-general-lite", source)

    def test_quality_cache_key_tracks_file_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"first")
            key1 = aq._cache_key_from_source(path, aq.MODE_QUALITY, aq.QUALITY_MAX_SIDE)
            path.write_bytes(b"second-longer")
            key2 = aq._cache_key_from_source(path, aq.MODE_QUALITY, aq.QUALITY_MAX_SIDE)
            self.assertNotEqual(key1, key2)
            self.assertIsNone(aq._cache_key_from_source(path, aq.MODE_FAST, aq.AUTO_SIMPLE_SIDE))

    def test_auto_cache_key_includes_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"same-file")
            low = aq._cache_key_from_source(path, aq.MODE_AUTO, aq.AUTO_SIMPLE_SIDE)
            high = aq._cache_key_from_source(path, aq.MODE_AUTO, aq.AUTO_COMPLEX_SIDE)
            self.assertNotEqual(low, high)

    def test_auto_never_uses_manual_max_resolution(self):
        samples = [
            Image.new("RGB", (1600, 900), "white"),
            Image.new("RGB", (1600, 900), "gray"),
            Image.new("RGB", (1600, 900), "black"),
        ]
        for image in samples:
            engine, side = aq._auto_plan(image)
            self.assertIn(engine, ("fast", "birefnet"))
            if side is not None:
                self.assertLess(side, aq.QUALITY_MAX_SIDE)

    def test_mask_cache_returns_copy(self):
        key = ("unit-test", 1, 1, aq.MODE_QUALITY, aq.QUALITY_MAX_SIDE)
        mask = Image.new("L", (8, 8), 200)
        aq._cache_put(key, mask)
        cached = aq._cache_get(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.getpixel((0, 0)), 200)
        cached.putpixel((0, 0), 0)
        cached_again = aq._cache_get(key)
        self.assertEqual(cached_again.getpixel((0, 0)), 200)


if __name__ == "__main__":
    unittest.main()
