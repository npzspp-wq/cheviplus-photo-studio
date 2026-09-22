"""Upgrade support for Cheviplus Photo Studio.

Goals:
- every Setup can be installed over the previous version;
- license/workstation/admin/statistics/settings survive upgrades;
- legacy settings stored next to the EXE are migrated to APPDATA once;
- each new application version creates one local safety snapshot before use;
- reserve a stable update-channel state for a future server updater.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import shutil

import app

APP_DATA = Path(os.environ.get("APPDATA") or Path.home()) / "CheviplusPhotoStudio"
SETTINGS_PATH = APP_DATA / "settings.json"
UPDATE_STATE_PATH = APP_DATA / "update_state.json"
BACKUPS_DIR = APP_DATA / "backups"
CRITICAL_FILES = (
    "license.json",
    "license_registry.json",
    "issued_workstations.json",
    "admin.json",
    "workstation_stats.json",
    "settings.json",
)


def _safe_read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def migrate_settings_to_appdata():
    """Move settings out of the install directory without losing existing values."""
    APP_DATA.mkdir(parents=True, exist_ok=True)
    legacy = app.APP_DIR / "cheviplus_settings.json"
    if not SETTINGS_PATH.exists() and legacy.exists():
        try:
            shutil.copy2(legacy, SETTINGS_PATH)
        except Exception:
            pass
    # app.App save/load methods resolve this module global at runtime.
    app.SETTINGS_FILE = SETTINGS_PATH


def _backup_for_version(version: str):
    """Create one pre-use snapshot per installed version. Never delete old snapshots here."""
    APP_DATA.mkdir(parents=True, exist_ok=True)
    state = _safe_read_json(UPDATE_STATE_PATH, {})
    if state.get("last_backup_version") == version:
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = BACKUPS_DIR / f"before-{version}-{stamp}"
    copied = 0
    for name in CRITICAL_FILES:
        source = APP_DATA / name
        if not source.exists():
            continue
        try:
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / name)
            copied += 1
        except Exception:
            pass

    state.update({
        "schema_version": 1,
        "channel": state.get("channel", "stable"),
        "last_backup_version": version,
        "last_backup_at": datetime.now().isoformat(timespec="seconds"),
        "backup_files": copied,
        # Reserved for the future license/update server. Empty means manual Setup updates.
        "update_manifest_url": state.get("update_manifest_url", ""),
    })
    try:
        UPDATE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def prepare_upgrade_environment(version: str):
    migrate_settings_to_appdata()
    _backup_for_version(version)


def get_update_state():
    """Stable API for the future online updater/server integration."""
    data = _safe_read_json(UPDATE_STATE_PATH, {})
    data.setdefault("schema_version", 1)
    data.setdefault("channel", "stable")
    data.setdefault("update_manifest_url", "")
    return data
