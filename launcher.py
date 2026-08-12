"""Stable launcher for the packaged Windows application."""

# Apply branding/export presets first, then start the full 5.9 application.
import sapphire_profile_patch  # noqa: F401
from cheviplus_license import LicenseApp


if __name__ == "__main__":
    LicenseApp().mainloop()
