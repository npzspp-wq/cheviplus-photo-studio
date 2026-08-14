"""Cheviplus Photo Studio 5.13: offline renewal now, server-ready later."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
from tkinter import ttk, filedialog, messagebox, simpledialog

import app
import cheviplus_license as lic
import cheviplus_license_registry as registry

APP_VERSION = "5.13"
APP_BUILD = "2026.08.14.01"


def _renewal_payload(item: dict, months: int = 6) -> dict:
    payload = {
        "version": 4,
        "type": "renewal",
        "license_number": str(item.get("license_number") or "").strip(),
        "department": registry._clean(item.get("department", "")),
        "workstation_code": registry._clean(item.get("workstation_code", "")),
        "workstation_name": registry._clean(item.get("name", "")),
        "token": str(item.get("token") or "").strip(),
        "months": int(months),
        "issued_at": datetime.now().isoformat(timespec="seconds"),
        "server_ready": True,
        "renewal": True,
    }
    if not payload["license_number"] or not payload["token"]:
        raise ValueError("В записи нет данных для продления этой лицензии.")
    payload["signature"] = lic._sign_payload(payload)
    return payload


def save_renewal_package(license_number: str, destination: str | Path, months: int = 6):
    item = registry._find_registry_item(license_number)
    if not item:
        raise ValueError("Лицензия не найдена в локальном реестре.")
    payload = _renewal_payload(item, months)
    Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    data = lic._load_registry()
    for row in data.get("licenses", []):
        if isinstance(row, dict) and row.get("license_number") == license_number:
            row["last_renewal_issued_at"] = payload["issued_at"]
            row["last_renewal_months"] = int(months)
            row["status"] = "renewal_issued"
            break
    lic._save_registry(data)
    return payload


def apply_renewal_package(path: str | Path, show_errors: bool = False):
    try:
        package_path = Path(path)
        data = json.loads(package_path.read_text(encoding="utf-8"))
        if not lic._verify_package(data):
            raise ValueError("Некорректная подпись файла продления.")
        if not (data.get("renewal") or data.get("type") == "renewal"):
            return False
        current = lic.load_license()
        if not current.get("machine_fingerprint"):
            raise ValueError("Рабочее место ещё не активировано.")
        if str(current.get("license_number")) != str(data.get("license_number")):
            raise ValueError("Файл продления предназначен для другой лицензии.")
        if str(current.get("activation_token")) != str(data.get("token")):
            raise ValueError("Файл продления не соответствует этому рабочему месту.")
        now = datetime.now()
        old_until = lic._parse_dt(current.get("valid_until"))
        base = old_until if old_until and old_until > now else now
        months = max(1, min(60, int(data.get("months", 6) or 6)))
        new_until = lic._add_months(base, months)
        current["valid_until"] = new_until.isoformat(timespec="seconds")
        current["status"] = lic.STATUS_ACTIVE
        current["last_renewed_at"] = now.isoformat(timespec="seconds")
        current["last_renewal_package_at"] = data.get("issued_at")
        lic.save_license(current)
        try:
            package_path.unlink()
        except Exception:
            pass
        return True
    except Exception:
        if show_errors:
            raise
        return False


def _scan_for_renewal():
    current = lic.load_license()
    if not current.get("machine_fingerprint"):
        return False
    for path in list(lic._candidate_packages()):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("renewal") or raw.get("type") == "renewal":
                if apply_renewal_package(path):
                    return True
        except Exception:
            continue
    return False


_original_license_state = lic.license_state

def _license_state_with_renewal(now=None):
    _scan_for_renewal()
    return _original_license_state(now)

lic.license_state = _license_state_with_renewal


def _import_renewal_for_app(self):
    path = filedialog.askopenfilename(
        parent=self,
        title="Выберите файл продления лицензии",
        filetypes=[("Cheviplus license", "*.cpslicense"), ("Все файлы", "*.*")],
    )
    if not path:
        return
    try:
        if not apply_renewal_package(path, show_errors=True):
            raise ValueError("Это не файл продления лицензии.")
        self._refresh_license()
        data = lic.load_license()
        until = lic._parse_dt(data.get("valid_until"))
        text = until.strftime("%d.%m.%Y") if until else "—"
        messagebox.showinfo("Лицензия продлена", f"Лицензия {data.get('license_number','')} продлена.\nНовый срок: до {text}.", parent=self)
    except Exception as exc:
        messagebox.showerror("Продление лицензии", str(exc), parent=self)


def _install_employee_renewal_button(self):
    try:
        frame = getattr(self, "public_license_box", None) or getattr(self, "admin_license_box", None)
        if frame is not None:
            self.renew_license_btn = ttk.Button(frame, text="Загрузить продление…", command=lambda: _import_renewal_for_app(self))
            self.renew_license_btn.pack(side="right", padx=4)
            data = lic.load_license()
            if not data.get("machine_fingerprint"):
                self.renew_license_btn.pack_forget()
    except Exception:
        pass


def _show_renewal_when_activated(self):
    try:
        btn = getattr(self, "renew_license_btn", None)
        data = lic.load_license()
        if btn is None:
            return
        if data.get("machine_fingerprint"):
            if not btn.winfo_manager(): btn.pack(side="right", padx=4)
        else:
            btn.pack_forget()
    except Exception:
        pass


_original_refresh = registry.AdminRegistryApp._refresh_license
def _refresh_with_renewal_button(self):
    _original_refresh(self)
    _show_renewal_when_activated(self)
registry.AdminRegistryApp._refresh_license = _refresh_with_renewal_button

_original_registry_init = registry.RegistryWindow.__init__
def _registry_init(self, parent):
    _original_registry_init(self, parent)
    bar = ttk.Frame(self, padding=(12, 0, 12, 10))
    bar.pack(fill="x")
    ttk.Button(bar, text="Продлить выбранную лицензию…", command=lambda: _renew_selected(self)).pack(side="right")
    ttk.Label(bar, text="Продление сохраняет тот же номер CPS и рабочее место.").pack(side="left")
registry.RegistryWindow.__init__ = _registry_init


def _renew_selected(window):
    number = window._selected_license_number()
    if not number:
        return
    months = simpledialog.askinteger("Продление лицензии", "На сколько месяцев продлить?", parent=window, initialvalue=6, minvalue=1, maxvalue=60)
    if not months:
        return
    item = registry._find_registry_item(number)
    if not item:
        messagebox.showerror("Продление", "Лицензия не найдена.", parent=window)
        return
    department = registry._safe_filename(item.get("department", ""))
    workstation = registry._safe_filename(item.get("workstation_code", ""))
    default_name = f"{number}_{department}_{workstation}_RENEWAL_{months}m.cpslicense"
    dest = filedialog.asksaveasfilename(parent=window, title="Сохранить файл продления", defaultextension=".cpslicense", initialfile=default_name, filetypes=[("Cheviplus license", "*.cpslicense")])
    if not dest:
        return
    try:
        save_renewal_package(number, dest, months)
        window.refresh()
        messagebox.showinfo("Продление готово", f"Лицензия: {number}\nПродление: +{months} мес.\n\nОтправьте этот .cpslicense в филиал. Номер лицензии и настройки не изменятся.", parent=window)
    except Exception as exc:
        messagebox.showerror("Продление", str(exc), parent=window)


_original_build = registry.AdminRegistryApp._build
def _build_with_renewal(self):
    _original_build(self)
    _install_employee_renewal_button(self)
registry.AdminRegistryApp._build = _build_with_renewal

app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
lic.APP_VERSION = APP_VERSION
lic.APP_BUILD = APP_BUILD
registry.APP_VERSION = APP_VERSION
registry.APP_BUILD = APP_BUILD
