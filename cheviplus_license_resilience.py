"""Cheviplus Photo Studio 5.35 — resilient workstation licensing.

Goals:
- Windows/hardware changes must not unexpectedly stop an operator.
- Clock rollback is diagnostic only, never a hard stop.
- Keep a backup copy of the bound license and restore it if license.json is damaged.
- Keep administrator suspended/blocked states as hard stops.
- Extend the post-expiry grace period to 30 days.
- Preserve the existing activation/renewal format for compatibility.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import shutil

import app
import cheviplus_license as lic
import cheviplus_ui_cleanup_532 as ui

APP_VERSION = "5.35"
APP_BUILD = "2026.09.11.01"
GRACE_DAYS = 30
WARN_DAYS = 30

_ORIGINAL_LOAD = lic.load_license
_ORIGINAL_SAVE = lic.save_license


def _backup_path() -> Path:
    return lic._data_dir() / "license.backup.json"


def _valid_license_dict(data):
    return isinstance(data, dict) and bool(data.get("license_number") or data.get("machine_fingerprint"))


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_backup(data):
    if not _valid_license_dict(data):
        return
    try:
        p = _backup_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def load_license_resilient():
    data = _ORIGINAL_LOAD()
    if _valid_license_dict(data):
        _write_backup(data)
        return data
    backup = _read_json(_backup_path())
    if _valid_license_dict(backup):
        try:
            _ORIGINAL_SAVE(backup)
        except Exception:
            pass
        return backup
    return data


def save_license_resilient(data):
    _ORIGINAL_SAVE(data)
    _write_backup(data)


def license_state_resilient(now=None):
    now = now or datetime.now()
    data = load_license_resilient()
    status = data.get("status", lic.STATUS_UNLICENSED)

    # Administrator decisions remain authoritative.
    if status == lic.STATUS_BLOCKED:
        return data, "blocked", False
    if status == lic.STATUS_SUSPENDED:
        return data, "suspended", False

    if status != lic.STATUS_ACTIVE:
        return data, "unlicensed", False

    # Hardware / Windows identity changes are repaired automatically instead of
    # stopping a branch. The activation token and license number stay unchanged.
    current_fp = lic._machine_fingerprint()
    old_fp = data.get("machine_fingerprint")
    repaired_device = bool(old_fp and old_fp != current_fp)
    if not old_fp or repaired_device:
        data["machine_fingerprint"] = current_fp
        data["device_rebound_at"] = now.isoformat(timespec="seconds")
        data["device_rebound_reason"] = "automatic_recovery"

    # Clock rollback is recorded for diagnostics, but it no longer blocks work.
    last = lic._parse_dt(data.get("last_seen_at"))
    rollback = bool(last and now < last - timedelta(hours=lic.CLOCK_ROLLBACK_TOLERANCE_HOURS))
    if rollback:
        data["clock_warning_at"] = now.isoformat(timespec="seconds")
    else:
        data["last_seen_at"] = max(now, last or now).isoformat(timespec="seconds")

    until = lic._parse_dt(data.get("valid_until"))
    save_license_resilient(data)
    if until is None:
        return data, "unlicensed", False

    if now <= until:
        days = (until.date() - now.date()).days
        if repaired_device:
            return data, "active_recovered", True
        if rollback:
            return data, "active_clock_warning", True
        return data, ("expiring" if days <= WARN_DAYS else "active"), True

    if now <= until + timedelta(days=GRACE_DAYS):
        return data, "grace", True
    return data, "expired", False


def _friendly_license_required(self):
    self._refresh_license()
    if self._license_allowed:
        return False
    data = lic.load_license()
    state = getattr(self, "_license_state", "unlicensed")
    if not data.get("machine_fingerprint"):
        if lic.messagebox.askyesno(
            "Cheviplus Photo Studio",
            "Рабочее место не активировано.\n\nЗагрузить файл лицензии сейчас?",
            parent=self,
        ):
            self._activate_from_file()
        self._refresh_license()
        return not self._license_allowed

    messages = {
        "blocked": "Рабочее место заблокировано администратором.",
        "suspended": "Рабочее место приостановлено администратором.",
        "expired": "Срок лицензии и 30-дневный резервный период закончились. Требуется продление.",
        "unlicensed": "Данные лицензии неполные. Требуется восстановление или повторная активация.",
    }
    lic.messagebox.showwarning(
        "Cheviplus Photo Studio",
        messages.get(state, f"Лицензия требует внимания. Статус: {state}."),
        parent=self,
    )
    return True


def export_license_diagnostics(destination):
    data, state, allowed = license_state_resilient()
    report = {
        "app_version": APP_VERSION,
        "app_build": APP_BUILD,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "state": state,
        "allowed": allowed,
        "license_number": data.get("license_number"),
        "workstation_name": data.get("workstation_name"),
        "workstation_id": data.get("workstation_id"),
        "status": data.get("status"),
        "activated_at": data.get("activated_at"),
        "valid_until": data.get("valid_until"),
        "last_seen_at": data.get("last_seen_at"),
        "device_rebound_at": data.get("device_rebound_at"),
        "clock_warning_at": data.get("clock_warning_at"),
        "backup_exists": _backup_path().exists(),
    }
    Path(destination).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# Apply compatibility-preserving monkey patches before the UI instance is built.
lic.GRACE_DAYS = GRACE_DAYS
lic.WARN_DAYS = WARN_DAYS
lic.load_license = load_license_resilient
lic.save_license = save_license_resilient
lic.license_state = license_state_resilient
lic.LicenseApp._license_required = _friendly_license_required

# Make 5.35 visible throughout the existing layered UI without rewriting modules.
ui.APP_VERSION = APP_VERSION
ui.APP_BUILD = APP_BUILD
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
lic.APP_VERSION = APP_VERSION
lic.APP_BUILD = APP_BUILD
