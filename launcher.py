"""Stable launcher for the packaged Windows application."""

# Apply branding/export presets first, then prepare persistent user data and start 5.10.
import sapphire_profile_patch  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp, APP_VERSION
from cheviplus_update_support import prepare_upgrade_environment


if __name__ == "__main__":
    prepare_upgrade_environment(APP_VERSION)
    AdminRegistryApp().mainloop()
