"""Stable launcher for the packaged Windows application."""

# Apply branding/export presets and storage safety before starting the licensed UI.
import sapphire_profile_patch  # noqa: F401
import cheviplus_network_storage as network_storage  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
# Load adaptive scaling only after registry/AI modules have installed their processing hooks.
import cheviplus_adaptive_scale  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment

# The newest feature module owns the visible application version/build.
network_storage.app.APP_VERSION = network_storage.APP_VERSION
network_storage.app.APP_BUILD = network_storage.APP_BUILD
renewal.APP_VERSION = network_storage.APP_VERSION
renewal.APP_BUILD = network_storage.APP_BUILD


if __name__ == "__main__":
    prepare_upgrade_environment(network_storage.APP_VERSION)
    AdminRegistryApp().mainloop()
