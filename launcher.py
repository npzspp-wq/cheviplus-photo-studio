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

# Final runtime router. app.py looks up compose_image dynamically, so this is the
# single authoritative entry point for preview and batch processing.
import app as _app
import cheviplus_ai_quality as _aiq
from pathlib import Path as _Path
from PIL import Image as _Image, ImageEnhance as _ImageEnhance, ImageFilter as _ImageFilter

_FINAL_COMPOSE = _app.compose_image

def _compose_product_only_direct(source, **options):
    """Bypass legacy renderer closures so PRODUCT_ONLY cannot silently fall back."""
    original = _Image.open(source)
    mask = _aiq.build_product_only_mask(original)
    product = original.convert("RGBA")
    product.putalpha(mask)
    product = _app.trim_transparency(product)
    if options.get("straighten"):
        product = _app.trim_transparency(_app.auto_straighten(product))
    sharpness = max(0, min(100, int(options.get("sharpness", 45))))
    rgb = _ImageEnhance.Contrast(product.convert("RGB")).enhance(1.02)
    if sharpness:
        rgb = rgb.filter(_ImageFilter.UnsharpMask(radius=.65+sharpness/180, percent=45+int(sharpness*1.25), threshold=2))
    product = _Image.merge("RGBA", (*rgb.split(), product.getchannel("A")))
    cw, ch = int(options.get("canvas_width",1280)), int(options.get("canvas_height",960))
    bg = _app.fit_cover(_Image.open(options["background_path"]).convert("RGB"), (cw,ch)).convert("RGBA")
    fill=float(options.get("product_fill",.86))
    ratio=min((cw*fill)/max(1,product.width),(ch*fill)/max(1,product.height))
    product=product.resize((max(1,int(product.width*ratio)),max(1,int(product.height*ratio))),_Image.Resampling.LANCZOS)
    x=(cw-product.width)//2; y=max(20,min(int(ch*.54-product.height/2),ch-product.height-20))
    if options.get("shadow"):
        _app.add_shadow(bg,product,(x,y),int(options.get("shadow_strength",28)))
    bg.alpha_composite(product,(x,y))
    logo_path=_Path(options.get("logo_path") or _app.DEFAULT_LOGO)
    if options.get("add_logo") and logo_path.exists():
        logo=_Image.open(logo_path).convert("RGBA")
        scale=min(1.0,(cw*.15)/max(1,logo.width))
        logo=logo.resize((max(1,int(logo.width*scale)),max(1,int(logo.height*scale))),_Image.Resampling.LANCZOS)
        margin=int(min(cw,ch)*.025); bg.alpha_composite(logo,(cw-logo.width-margin,ch-logo.height-margin))
    return bg

def _mode_aware_final_compose(*args, **kwargs):
    mode = kwargs.get("processing_mode", _aiq.MODE_FAST)
    source = args[0] if args else kwargs.get("source")
    if mode == _aiq.MODE_PRODUCT_ONLY:
        direct = dict(kwargs)
        direct.pop("processing_mode", None)
        for key in ("plexiglass_enabled","plexiglass_intensity","table_manual_position","table_vertical_offset"):
            direct.pop(key, None)
        return _compose_product_only_direct(source, **direct)
    previous_mode = getattr(_aiq._LOCAL, "mode", _aiq.MODE_FAST)
    previous_key = getattr(_aiq._LOCAL, "cache_key", None)
    _aiq._LOCAL.mode = mode if mode in _aiq.MODES else _aiq.MODE_FAST
    _aiq._LOCAL.cache_key = _aiq._cache_key_from_source(source, _aiq._LOCAL.mode)
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
