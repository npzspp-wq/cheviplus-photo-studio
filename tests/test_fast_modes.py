import unittest

import cheviplus_fast_modes as fm


class FastModeTests(unittest.TestCase):
    def test_known_modes_are_kept(self):
        for mode in fm.MODES:
            self.assertEqual(fm._normalize_mode(mode), mode)

    def test_unknown_mode_falls_back_to_normal(self):
        self.assertEqual(fm._normalize_mode("anything"), fm.MODE_NORMAL)


if __name__ == "__main__":
    unittest.main()
