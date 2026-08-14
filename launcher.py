"""Stable launcher for the packaged Windows application."""

# Apply branding/export presets first, then prepare persistent user data and start 5.12.
import sapphire_profile_patch  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment


if __name__ == "__main__":
    prepare_upgrade_environment(renewal.APP_VERSION)
    AdminRegistryApp().mainloop()
