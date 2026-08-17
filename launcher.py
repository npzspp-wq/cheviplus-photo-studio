"""Stable launcher for the packaged Windows application."""

import sapphire_profile_patch as profile  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment

# Licensing modules inherit the visible build number of the active profile branch.
renewal.APP_VERSION = profile.APP_VERSION
renewal.APP_BUILD = profile.APP_BUILD
renewal.app.APP_VERSION = profile.APP_VERSION
renewal.app.APP_BUILD = profile.APP_BUILD


if __name__ == "__main__":
    prepare_upgrade_environment(profile.APP_VERSION)
    AdminRegistryApp().mainloop()
