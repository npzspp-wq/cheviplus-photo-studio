"""Stable launcher for the packaged Windows application."""

from cheviplus_stability_patch import StableApp
import cheviplus_mask_quality  # noqa: F401  # installs 4.2 mask-quality patch


if __name__ == "__main__":
    StableApp().mainloop()
