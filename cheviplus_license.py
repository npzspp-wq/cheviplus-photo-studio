"""Cheviplus Photo Studio 5.8: local license core.

This version prepares the workstation-bound license state and UI. Remote server
verification is intentionally not implemented here; it will replace the local
administrator test controls in the next stage.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
from tkinter import ttk, messagebox

import app
import cheviplus_ai_quality as aq
from cheviplus_workstation_stats import WorkstationStatsApp, load_stats

APP_VERSION = "5.8"
APP_BUILD = "2026.08.11.05"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_BLOCKED = "blocked"
STATUS_UNLICENSED = "unlicensed"
GRACE_DAYS = 7
WARN_DAYS = 14
CLOCK_ROLLBACK_TOLERANCE_HOURS = 12


def _license_path():
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "CheviplusPhotoStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path / "license.json"


def _workstation_id():
    return load_stats()["workstation_id"]


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _default_license():
    return {
        "version": 1,
        "workstation_id": _workstation_id(),
        "status": STATUS_UNLICENSED,
        "valid_until": None,
        "activated_at": None,
        "last_seen_at": None,
        "last_verified_at": None,
        "source": "local-core",
    }


def load_license():
    path = _license_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = _default_license()
    if data.get("workstation_id") != _workstation_id():
        data = _default_license()
    for key, value in _default_license().items():
        data.setdefault(key, value)
    return data


def save_license(data):
    path = _license_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def activate_local_license(months=6):
    now = datetime.now()
    data = load_license()
    data.update({
        "status": STATUS_ACTIVE,
        "activated_at": data.get("activated_at") or now.isoformat(timespec="seconds"),
        "valid_until": (now + timedelta(days=30 * int(months))).isoformat(timespec="seconds"),
        "last_verified_at": now.isoformat(timespec="seconds"),
        "last_seen_at": now.isoformat(timespec="seconds"),
        "source": "local-admin-test",
    })
    save_license(data)
    return data


def set_license_status(status):
    if status not in (STATUS_ACTIVE, STATUS_SUSPENDED, STATUS_BLOCKED):
        raise ValueError("Unsupported license status")
    data = load_license()
    data["status"] = status
    data["last_verified_at"] = datetime.now().isoformat(timespec="seconds")
    save_license(data)
    return data


def license_state(now=None):
    now = now or datetime.now()
    data = load_license()
    last_seen = _parse_dt(data.get("last_seen_at"))
    rollback = bool(last_seen and now < last_seen - timedelta(hours=CLOCK_ROLLBACK_TOLERANCE_HOURS))
    if not rollback:
        data["last_seen_at"] = max(now, last_seen or now).isoformat(timespec="seconds")
        save_license(data)

    status = data.get("status", STATUS_UNLICENSED)
    valid_until = _parse_dt(data.get("valid_until"))
    if rollback:
        return data, "clock_rollback", False
    if status == STATUS_BLOCKED:
        return data, "blocked", False
    if status == STATUS_SUSPENDED:
        return data, "suspended", False
    if status != STATUS_ACTIVE or valid_until is None:
        return data, "unlicensed", False
    if now <= valid_until:
        remaining = (valid_until.date() - now.date()).days
        return data, ("expiring" if remaining <= WARN_DAYS else "active"), True
    grace_until = valid_until + timedelta(days=GRACE_DAYS)
    if now <= grace_until:
        return data, "grace", True
    return data, "expired", False


def license_text(data, state):
    valid_until = _parse_dt(data.get("valid_until"))
    date_text = valid_until.strftime("%d.%m.%Y") if valid_until else "—"
    names = {
        "active": "Активна",
        "expiring": "Скоро истекает",
        "grace": "Льготный период",
        "expired": "Срок истёк",
        "suspended": "Приостановлена",
        "blocked": "Заблокирована",
        "unlicensed": "Не активирована",
        "clock_rollback": "Проверка даты",
    }
    return f"Лицензия: {names.get(state, state)}   до: {date_text}   ID: {data.get('workstation_id','—')}"


class LicenseApp(WorkstationStatsApp):
    def _build(self):
        super()._build()
        frame = aq._find_label_frame(self, "3. Стабильная ручная обработка") or self
        box = ttk.LabelFrame(frame, text="Лицензия рабочего места", padding=6)
        box.grid(row=11, column=0, columnspan=6, sticky="ew", pady=(7, 3))
        self.license_label = ttk.Label(box, text="")
        self.license_label.pack(side="left", fill="x", expand=True)
        self.license_admin_frame = ttk.Frame(box)
        self.license_admin_frame.pack(side="right")
        self.activate_license_button = ttk.Button(self.license_admin_frame, text="Активировать 6 мес.", command=self._activate_license_test)
        self.suspend_license_button = ttk.Button(self.license_admin_frame, text="Приостановить", command=self._suspend_license_test)
        self.resume_license_button = ttk.Button(self.license_admin_frame, text="Возобновить", command=self._resume_license_test)
        for button in (self.activate_license_button, self.suspend_license_button, self.resume_license_button):
            button.pack(side="left", padx=(5, 0))
        self._refresh_license()
        self.after_idle(self._sync_license_admin_state)

    def _sync_license_admin_state(self):
        try:
            state = "normal" if self._admin_unlocked else "disabled"
            for button in (self.activate_license_button, self.suspend_license_button, self.resume_license_button):
                button.configure(state=state)
        except Exception:
            pass

    def _apply_admin_lock(self):
        super()._apply_admin_lock()
        self._sync_license_admin_state()

    def _refresh_license(self):
        data, state, allowed = license_state()
        self._license_allowed = allowed
        self._license_state = state
        self.license_label.configure(text=license_text(data, state))

    def _activate_license_test(self):
        if not self._admin_unlocked:
            return
        activate_local_license(6)
        self._refresh_license()
        messagebox.showinfo("Лицензия", "Тестовая локальная лицензия активирована на 6 месяцев.", parent=self)

    def _suspend_license_test(self):
        if not self._admin_unlocked:
            return
        set_license_status(STATUS_SUSPENDED)
        self._refresh_license()

    def _resume_license_test(self):
        if not self._admin_unlocked:
            return
        data = load_license()
        if not data.get("valid_until"):
            activate_local_license(6)
        else:
            set_license_status(STATUS_ACTIVE)
        self._refresh_license()

    def start_preview(self):
        self._refresh_license()
        if not self._license_allowed:
            messagebox.showwarning("Лицензия", "Обработка недоступна: " + license_text(load_license(), self._license_state), parent=self)
            return
        super().start_preview()

    def start(self):
        self._refresh_license()
        if not self._license_allowed:
            messagebox.showwarning("Лицензия", "Обработка недоступна: " + license_text(load_license(), self._license_state), parent=self)
            return
        super().start()


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
aq.APP_VERSION = APP_VERSION
aq.APP_BUILD = APP_BUILD
