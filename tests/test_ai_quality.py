import unittest

import cheviplus_ai_quality as aq


class AIQualityTests(unittest.TestCase):
    def test_modes_are_explicit(self):
        self.assertIn(aq.MODE_FAST, aq.MODES)
        self.assertIn(aq.MODE_QUALITY, aq.MODES)
        self.assertNotEqual(aq.MODE_FAST, aq.MODE_QUALITY)

    def test_quality_session_model_name_is_birefnet_lite(self):
        source = aq.get_quality_session.__code__.co_consts
        self.assertIn("birefnet-general-lite", source)


if __name__ == "__main__":
    unittest.main()
