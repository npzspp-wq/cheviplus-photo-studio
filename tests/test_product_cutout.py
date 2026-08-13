import unittest

import numpy as np
from PIL import Image

import cheviplus_product_cutout as pc


class ProductCutoutTests(unittest.TestCase):
    def test_meaningful_components_keep_multiple_parts(self):
        alpha = np.zeros((120, 220), dtype=np.uint8)
        alpha[20:70, 20:90] = 220
        alpha[30:80, 120:185] = 210
        alpha[5:8, 5:8] = 200
        keep = pc._meaningful_component_mask(alpha)
        self.assertTrue(bool(keep[40, 40]))
        self.assertTrue(bool(keep[50, 150]))
        self.assertFalse(bool(keep[6, 6]))

    def test_edge_backdrop_does_not_erase_confident_light_product(self):
        rgb = np.full((100, 160, 3), 238, dtype=np.uint8)
        rgb[30:75, 30:130] = (210, 205, 195)
        alpha = np.zeros((100, 160), dtype=np.uint8)
        alpha[30:75, 30:130] = 230
        cleaned = pc._remove_edge_connected_backdrop(
            Image.fromarray(rgb, mode="RGB"), alpha
        )
        self.assertGreater(int(cleaned[50, 80]), 200)
        self.assertEqual(int(cleaned[5, 5]), 0)


if __name__ == "__main__":
    unittest.main()
