import unittest

import numpy as np
from PIL import Image

import cheviplus_mask_quality as mq


class MaskQualityTests(unittest.TestCase):
    def test_recovers_dark_chrome_inside_product(self):
        h, w = 120, 240
        rgb = np.full((h, w, 3), 235, dtype=np.uint8)
        rgb[35:85, 35:205] = (35, 38, 42)
        for x in range(95, 145):
            shade = 70 + ((x - 95) % 20) * 4
            rgb[48:72, x] = (shade, shade + 10, shade + 15)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[35:85, 35:205] = 255
        alpha[48:72, 95:145] = 0

        recovered = np.asarray(
            mq.recover_reflective_chrome(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
            )
        )
        self.assertGreater(float(recovered[52:68, 100:140].mean()), 180.0)

    def test_keeps_true_backdrop_hole_transparent(self):
        h, w = 120, 240
        rgb = np.full((h, w, 3), 235, dtype=np.uint8)
        rgb[30:90, 30:210] = (45, 45, 48)
        rgb[48:72, 95:145] = (235, 235, 235)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[30:90, 30:210] = 255
        alpha[48:72, 95:145] = 0

        recovered = np.asarray(
            mq.recover_reflective_chrome(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
            )
        )
        self.assertLess(float(recovered[52:68, 100:140].mean()), 30.0)

    def test_removes_border_connected_old_backdrop(self):
        h, w = 120, 200
        rgb = np.full((h, w, 3), 238, dtype=np.uint8)
        rgb[35:95, 20:110] = (40, 42, 45)
        rgb[30:100, 115:200] = (232, 231, 228)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[35:95, 20:110] = 255
        alpha[30:100, 115:200] = 255

        cleaned = np.asarray(
            mq.remove_border_connected_backdrop(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
            )
        )
        self.assertGreater(float(cleaned[45:85, 35:95].mean()), 200.0)
        self.assertLess(float(cleaned[40:90, 135:190].mean()), 30.0)

    def test_does_not_overclean_long_bumper_like_part(self):
        h, w = 160, 360
        rgb = np.full((h, w, 3), 235, dtype=np.uint8)
        rgb[65:100, 25:335] = (48, 50, 52)
        rgb[72:90, 65:300] = (205, 205, 205)

        alpha = np.zeros((h, w), dtype=np.uint8)
        alpha[65:100, 25:335] = 255

        before = alpha.copy()
        cleaned = np.asarray(
            mq.remove_border_connected_backdrop(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
            )
        )
        self.assertGreater(float(cleaned[70:95, 40:320].mean()), 240.0)
        self.assertEqual(int(cleaned.sum()), int(before.sum()))


if __name__ == "__main__":
    unittest.main()
