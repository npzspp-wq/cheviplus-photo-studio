"""Stable launcher for the packaged Windows application."""

from cheviplus_stability_patch import StableApp
import cheviplus_birefnet_patch  # noqa: F401  # installs 4.4 BiRefNet test path


if __name__ == "__main__":
    StableApp().mainloop()
