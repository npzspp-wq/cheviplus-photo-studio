import numpy as np
from PIL import Image

import cheviplus_adaptive_scale as scale


def mask_box(width, height, fill=1.0):
    arr = np.zeros((1000, 1000), dtype=np.uint8)
    x0 = (1000-width)//2; y0 = (1000-height)//2
    if fill >= 0.99:
        arr[y0:y0+height, x0:x0+width] = 255
    else:
        # open rectangular ring approximates moulding/open trim geometry
        t = max(3, int(min(width, height)*0.08))
        arr[y0:y0+t, x0:x0+width] = 255
        arr[y0+height-t:y0+height, x0:x0+width] = 255
        arr[y0:y0+height, x0:x0+t] = 255
        arr[y0:y0+height, x0+width-t:x0+width] = 255
    return Image.fromarray(arr, mode="L")


def test_ring_like_reference_uses_generous_margin():
    assert scale.adaptive_reference_fill(mask_box(500, 500, fill=0.2)) == 0.55


def test_very_long_part_uses_width():
    assert scale.adaptive_reference_fill(mask_box(800, 180)) == 0.90


def test_compact_solid_part_stays_moderate():
    assert scale.adaptive_reference_fill(mask_box(450, 420)) == 0.60
