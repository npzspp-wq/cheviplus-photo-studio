"""Stable launcher for the packaged Windows application."""

# Apply product/export configuration before the Tkinter UI is created.
import sapphire_profile_patch  # noqa: F401
from cheviplus_stability_patch import StableApp


if __name__ == "__main__":
    StableApp().mainloop()
