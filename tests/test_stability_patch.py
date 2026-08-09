import unittest

import numpy as np
from PIL import Image, ImageDraw

import cheviplus_stability_patch as patch


class StabilityPatchTests(unittest.TestCase):
    def _two_part_rgba(self):
        img = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((20, 30, 80, 85), fill=(30, 30, 30, 255))
        draw.rectangle((150, 35, 210, 90), fill=(30, 30, 30, 255))
        # Tiny floating artefact that should be removed.
        draw.rectangle((118, 8, 123, 13), fill=(30, 30, 30, 255))
        return img

    def test_separate_real_kit_parts_are_preserved(self):
        cleaned = patch.remove_isolated_artifacts(self._two_part_rgba())
        alpha = np.asarray(cleaned.getchannel("A"))
        self.assertGreater(alpha[50:70, 35:65].mean(), 200)
        self.assertGreater(alpha[50:75, 165:195].mean(), 200)
        self.assertEqual(int(alpha[9:13, 119:123].max()), 0)

    def test_strict_background_cleanup_keeps_multiple_cores(self):
        alpha = Image.new("L", (240, 120), 0)
        draw = ImageDraw.Draw(alpha)
        draw.rectangle((20, 30, 80, 85), fill=255)
        draw.rectangle((150, 35, 210, 90), fill=255)
        draw.rectangle((115, 7, 124, 15), fill=80)
        cleaned = patch.suppress_old_background(alpha, strict=True)
        arr = np.asarray(cleaned)
        self.assertGreater(arr[50:70, 35:65].mean(), 240)
        self.assertGreater(arr[50:75, 165:195].mean(), 240)
        self.assertEqual(int(arr[8:14, 116:123].max()), 0)

    def test_safe_numeric_parsing_clamps_bad_export_values(self):
        self.assertEqual(patch._safe_int("bad", 88, 45, 95), 88)
        self.assertEqual(patch._safe_int("999", 88, 45, 95), 95)
        self.assertAlmostEqual(patch._safe_float("bad", 0.86, 0.25, 0.98), 0.86)


if __name__ == "__main__":
    unittest.main()
