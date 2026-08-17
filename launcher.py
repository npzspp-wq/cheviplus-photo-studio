"""Stable launcher for the packaged Windows application."""

import sapphire_profile_patch as profile  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
# Import after the AI/license modules so the effect wraps the final processing pipeline.
import cheviplus_plexiglass as plexiglass  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment

# Visible version/build belongs to the newest feature module.
renewal.APP_VERSION = plexiglass.APP_VERSION
renewal.APP_BUILD = plexiglass.APP_BUILD
renewal.app.APP_VERSION = plexiglass.APP_VERSION
renewal.app.APP_BUILD = plexiglass.APP_BUILD


if __name__ == "__main__":
    prepare_upgrade_environment(plexiglass.APP_VERSION)
    AdminRegistryApp().mainloop()
