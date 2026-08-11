import unittest

import numpy as np
from PIL import Image

import cheviplus_backdrop_quality as bq


class BackdropQualityTests(unittest.TestCase):
    def test_preserves_large_kit_when_one_pass_is_confident(self):
        h, w = 120, 220
        a1 = np.zeros((h, w), dtype=np.uint8)
        a2 = np.zeros((h, w), dtype=np.uint8)

        # Main light product, supported strongly by both passes.
        a1[30:100, 20:150] = 225
        a2[30:100, 20:150] = 205

        # Separate/overlapping kit piece that only one pass sees confidently.
        a1[45:105, 145:215] = 190
        a2[45:105, 145:215] = 42

        merged = bq._product_preserving_merge(a1, a2)
        self.assertGreater(float(merged[50:90, 40:130].mean()), 230.0)
        self.assertGreater(float(merged[55:95, 165:205].mean()), 150.0)

    def test_preserves_light_product_touching_image_edge(self):
        h, w = 120, 220
        rgb = np.full((h, w, 3), 240, dtype=np.uint8)
        rgb[35:115, 10:220] = (205, 201, 194)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[35:115, 10:220] = 205

        cleaned = bq._safe_background_cleanup(
            Image.fromarray(rgb, mode="RGB"), alpha
        )
        self.assertGreater(float(cleaned[55:100, 30:200].mean()), 190.0)
        self.assertGreater(float(cleaned[55:100, 205:219].mean()), 190.0)

    def test_removes_only_ai_weak_edge_background(self):
        h, w = 120, 220
        rgb = np.full((h, w, 3), 238, dtype=np.uint8)
        rgb[35:95, 35:150] = (110, 106, 100)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[35:95, 35:150] = 220
        alpha[10:110, 175:220] = 35

        cleaned = bq._safe_background_cleanup(
            Image.fromarray(rgb, mode="RGB"), alpha
        )
        self.assertGreater(float(cleaned[50:85, 50:130].mean()), 200.0)
        self.assertLess(float(cleaned[30:100, 185:215].mean()), 10.0)


if __name__ == "__main__":
    unittest.main()
