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

# Keep the final legacy renderer (plexiglass/workspace compatibility), but inject the
# selected AI mode into its thread-local background-removal engine. Replacing the final
# renderer with ai_quality.compose_image dropped newer keyword arguments such as
# plexiglass_enabled and caused preview failures in Build .06.
import app as _app
import cheviplus_ai_quality as _aiq

_FINAL_COMPOSE = _app.compose_image

def _mode_aware_final_compose(*args, **kwargs):
    mode = kwargs.get("processing_mode", _aiq.MODE_FAST)
    mode = mode if mode in _aiq.MODES else _aiq.MODE_FAST
    previous_mode = getattr(_aiq._LOCAL, "mode", _aiq.MODE_FAST)
    previous_key = getattr(_aiq._LOCAL, "cache_key", None)
    source = args[0] if args else kwargs.get("source")
    _aiq._LOCAL.mode = mode
    _aiq._LOCAL.cache_key = _aiq._cache_key_from_source(source, mode)
    try:
        return _FINAL_COMPOSE(*args, **kwargs)
    finally:
        _aiq._LOCAL.mode = previous_mode
        _aiq._LOCAL.cache_key = previous_key

_app.compose_image = _mode_aware_final_compose
_app.remove_background = _aiq.remove_background

if __name__=='__main__':
    prepare_upgrade_environment(license_resilience.APP_VERSION)
    FinalApp().mainloop()
