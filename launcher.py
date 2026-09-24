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
import cheviplus_marketplace_visual_v1 as marketplace_visual  # noqa: F401
import cheviplus_marketplace_five_cards as marketplace_five_cards  # noqa: F401
import cheviplus_ozon_compliance as ozon_compliance  # noqa: F401
import cheviplus_marketplace_text_layout as marketplace_text_layout  # noqa: F401
import cheviplus_photo_picker_fix as photo_picker_fix  # noqa: F401
import cheviplus_workspace_modes as workspace_modes  # noqa: F401
import cheviplus_ui_cleanup_532 as ui_cleanup  # noqa: F401
import cheviplus_license_resilience as license_resilience  # noqa: F401
# IMPORTANT: license_registry imports ai_quality but its class was historically based on
# the older LicenseApp, so selecting an AI mode changed the combobox without changing
# the processing path. Build the final application from AIQualityApp + registry controls.
from cheviplus_ai_quality import AIQualityApp
from cheviplus_update_support import prepare_upgrade_environment

renewal.APP_VERSION=license_resilience.APP_VERSION
renewal.APP_BUILD=license_resilience.APP_BUILD
renewal.app.APP_VERSION=license_resilience.APP_VERSION
renewal.app.APP_BUILD=license_resilience.APP_BUILD

class FinalApp(AdminRegistryApp, AIQualityApp):
    """Final packaged UI: registry controls layered on the AI implementation.

    AdminRegistryApp already inherits from AIQualityApp through LicenseApp /
    WorkstationStatsApp. Listing AIQualityApp a second time after it caused Python MRO
    to resolve current_options through older patched bases in packaged builds.
    """
    pass

# Force the final renderer back to the mode-aware AI wrapper after all legacy UI/effect
# patch imports above. Several old modules replace app.compose_image during import.
import app as _app
import cheviplus_ai_quality as _aiq
_app.compose_image = _aiq.compose_image
_app.remove_background = _aiq.remove_background

if __name__=='__main__':
    prepare_upgrade_environment(license_resilience.APP_VERSION)
    FinalApp().mainloop()
