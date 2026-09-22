import tempfile
import unittest
from pathlib import Path

from PIL import Image

import cheviplus_ai_quality as aq


class AIQualityTests(unittest.TestCase):
    def test_modes_are_explicit(self):
        self.assertIn(aq.MODE_FAST, aq.MODES)
        self.assertIn(aq.MODE_QUALITY, aq.MODES)
        self.assertEqual(len(set(aq.MODES)), 2)

    def test_quality_session_model_name_is_birefnet_lite(self):
        source = aq.get_quality_session.__code__.co_consts
        self.assertIn("birefnet-general-lite", source)

    def test_quality_cache_key_tracks_file_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"first")
            key1 = aq._cache_key_from_source(path, aq.MODE_QUALITY)
            path.write_bytes(b"second-longer")
            key2 = aq._cache_key_from_source(path, aq.MODE_QUALITY)
            self.assertNotEqual(key1, key2)
            self.assertIsNone(aq._cache_key_from_source(path, aq.MODE_FAST))

    def test_mask_cache_returns_copy(self):
        key = ("unit-test", 1, 1, aq.MODE_QUALITY)
        mask = Image.new("L", (8, 8), 200)
        aq._cache_put(key, mask)
        cached = aq._cache_get(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.getpixel((0, 0)), 200)
        cached.putpixel((0, 0), 0)
        cached_again = aq._cache_get(key)
        self.assertEqual(cached_again.getpixel((0, 0)), 200)

    def test_admin_pin_hash_verifies_without_storing_plain_pin(self):
        pin = "4729"
        salt, digest = aq._hash_pin(pin, salt=b"0123456789abcdef")
        self.assertTrue(aq._verify_pin(pin, salt, digest))
        self.assertFalse(aq._verify_pin("4728", salt, digest))
        self.assertNotIn(pin, digest)


if __name__ == "__main__":
    unittest.main()
