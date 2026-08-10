"""Stable launcher for the packaged Windows application."""

from cheviplus_stability_patch import StableApp
import cheviplus_isnet_patch  # noqa: F401  # installs 4.3 ISNet runtime patch


if __name__ == "__main__":
    StableApp().mainloop()
