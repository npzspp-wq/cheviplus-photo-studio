import unittest
import numpy as np
from PIL import Image

import cheviplus_ai_quality as aq


class ProductOnlyCutoutTests(unittest.TestCase):
    def test_removes_large_pale_support_but_keeps_dark_product(self):
        h, w = 300, 400
        rgb = np.full((h, w, 3), 250, dtype=np.uint8)
        # Large neutral cardboard/support board.
        rgb[55:255, 55:345] = (188, 186, 180)
        # Dark automotive part lying on top of it.
        rgb[115:205, 125:290] = (28, 31, 34)
        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[55:255, 55:345] = 255

        cleaned = aq._remove_flat_support_surface(Image.fromarray(rgb, "RGB"), alpha)

        self.assertLess(int(cleaned[80, 80]), 40)
        self.assertGreater(int(cleaned[150, 200]), 200)


if __name__ == "__main__":
    unittest.main()
