"""Stable launcher for the packaged Windows application."""

import sapphire_profile_patch as profile  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
import cheviplus_plexiglass as plexiglass  # noqa: F401
import cheviplus_table_placement_patch as table_patch  # noqa: F401
import cheviplus_compose_compat_patch as compose_compat  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment

# Visible version/build belongs to the newest compatibility patch.
renewal.APP_VERSION = compose_compat.APP_VERSION
renewal.APP_BUILD = compose_compat.APP_BUILD
renewal.app.APP_VERSION = compose_compat.APP_VERSION
renewal.app.APP_BUILD = compose_compat.APP_BUILD


if __name__ == "__main__":
    prepare_upgrade_environment(compose_compat.APP_VERSION)
    AdminRegistryApp().mainloop()
