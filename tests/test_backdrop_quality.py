import unittest

import numpy as np
from PIL import Image

import cheviplus_backdrop_quality as bq


class BackdropQualityTests(unittest.TestCase):
    def test_removes_edge_connected_backdrop_seen_by_only_one_pass(self):
        h, w = 120, 220
        rgb = np.full((h, w, 3), 238, dtype=np.uint8)
        rgb[35:95, 35:150] = (112, 108, 102)

        a1 = np.zeros((h, w), dtype=np.uint8)
        a2 = np.zeros((h, w), dtype=np.uint8)
        a1[35:95, 35:150] = 235
        a2[35:95, 35:150] = 220

        # Simulate a false rectangular old-backdrop foreground touching right edge:
        # one model pass is confident, the second rejects it.
        a1[20:110, 155:220] = 205
        a2[20:110, 155:220] = 40

        cleaned = bq._agreement_backdrop_cleanup(
            Image.fromarray(rgb, mode="RGB"), a1, a2
        )
        self.assertGreater(float(cleaned[50:85, 50:130].mean()), 200.0)
        self.assertLess(float(cleaned[30:100, 170:210].mean()), 40.0)

    def test_preserves_light_product_when_both_passes_agree(self):
        h, w = 120, 220
        rgb = np.full((h, w, 3), 240, dtype=np.uint8)
        rgb[35:95, 35:180] = (205, 201, 194)

        a1 = np.zeros((h, w), dtype=np.uint8)
        a2 = np.zeros((h, w), dtype=np.uint8)
        a1[35:95, 35:180] = 220
        a2[35:95, 35:180] = 205

        cleaned = bq._agreement_backdrop_cleanup(
            Image.fromarray(rgb, mode="RGB"), a1, a2
        )
        self.assertGreater(float(cleaned[50:80, 55:160].mean()), 195.0)


if __name__ == "__main__":
    unittest.main()
