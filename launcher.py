"""Stable launcher for the packaged Windows application."""

import sapphire_profile_patch as profile  # noqa: F401
from cheviplus_license_registry import AdminRegistryApp
import cheviplus_license_renewal as renewal  # noqa: F401
import cheviplus_plexiglass as plexiglass  # noqa: F401
import cheviplus_table_placement_patch as table_patch  # noqa: F401
import cheviplus_compose_compat_patch as compose_compat  # noqa: F401
import cheviplus_marketplace_catalog as marketplace  # noqa: F401
import cheviplus_marketplace_excel_1c_patch as marketplace_1c  # noqa: F401
import cheviplus_marketplace_cards as marketplace_cards  # noqa: F401
import cheviplus_marketplace_clipboard_patch as marketplace_clipboard  # noqa: F401
import cheviplus_marketplace_editor as marketplace_editor  # noqa: F401
import cheviplus_marketplace_templates as marketplace_templates  # noqa: F401
from cheviplus_update_support import prepare_upgrade_environment

renewal.APP_VERSION = marketplace_templates.APP_VERSION
renewal.APP_BUILD = marketplace_templates.APP_BUILD
renewal.app.APP_VERSION = marketplace_templates.APP_VERSION
renewal.app.APP_BUILD = marketplace_templates.APP_BUILD


if __name__ == "__main__":
    prepare_upgrade_environment(marketplace_templates.APP_VERSION)
    AdminRegistryApp().mainloop()
