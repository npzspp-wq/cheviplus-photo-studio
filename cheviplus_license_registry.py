"""Cheviplus Photo Studio 5.11: administrator license registry and workstation packages."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
import json
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import app
import cheviplus_ai_quality as aq
import cheviplus_license as lic

APP_VERSION = "5.11"
APP_BUILD = "2026.08.13.01"


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _safe_filename(value: str) -> str:
    value = _clean(value)
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value).strip("_") or "workstation"


def _registry_rows():
    data = lic._load_registry()
    rows = []
    for item in data.get("licenses", []):
        if not isinstance(item, dict):
            continue
        issued = str(item.get("issued_at", ""))
        try:
            issued_text = datetime.fromisoformat(issued).strftime("%d.%m.%Y %H:%M")
        except Exception:
            issued_text = issued or "—"
        rows.append({
            "license_number": item.get("license_number", "—"),
            "department": item.get("department", ""),
            "workstation_code": item.get("workstation_code", ""),
            "name": item.get("name", ""),
            "issued_at": issued_text,
            "issued_at_raw": item.get("issued_at", ""),
            "status": item.get("status", "issued"),
            "months": item.get("months", 6),
            "token": item.get("token", ""),
        })
    return rows


def _find_registry_item(license_number: str):
    data = lic._load_registry()
    for item in data.get("licenses", []):
        if isinstance(item, dict) and item.get("license_number") == license_number:
            return item
    return None


def _package_payload_from_registry(item: dict):
    number = str(item.get("license_number") or "").strip()
    token = str(item.get("token") or "").strip()
    issued_at = str(item.get("issued_at") or "").strip()
    department = _clean(item.get("department", ""))
    workstation_code = _clean(item.get("workstation_code", ""))
    name = _clean(item.get("name", "")) or _clean(f"{department} — {workstation_code}")
    if not number or not token or not issued_at:
        raise ValueError("Для этой старой записи недостаточно данных для повторной выгрузки лицензии.")
    payload = {
        "version": 3,
        "license_number": number,
        "department": department,
        "workstation_code": workstation_code,
        "workstation_name": name,
        "token": token,
        "months": int(item.get("months", 6) or 6),
        "issued_at": issued_at,
        "server_ready": True,
    }
    payload["signature"] = lic._sign_payload(payload)
    return payload


def save_existing_license_package(license_number: str, destination: str | Path):
    item = _find_registry_item(license_number)
    if not item:
        raise ValueError("Лицензия не найдена в реестре")
    payload = _package_payload_from_registry(item)
    Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def create_named_workstation_package(department: str, workstation_code: str, destination: str | Path):
    department = _clean(department)
    workstation_code = _clean(workstation_code)
    if not department:
        raise ValueError("Укажите подразделение")
    if not workstation_code:
        raise ValueError("Укажите номер или название рабочего места")

    registry = lic._load_registry()
    for item in registry.get("licenses", []):
        if not isinstance(item, dict):
            continue
        if _clean(item.get("department", "")).casefold() == department.casefold() and _clean(item.get("workstation_code", "")).casefold() == workstation_code.casefold():
            raise ValueError(
                f"Рабочее место уже существует: {item.get('license_number', '—')}. "
                "Выберите его в реестре и нажмите «Сохранить файл лицензии…»."
            )

    now = datetime.now()
    issued_at = now.isoformat(timespec="seconds")
    token = secrets.token_urlsafe(18)
    display_name = f"{department} — {workstation_code}"
    number = lic._allocate_license_number(display_name, token, issued_at)

    registry = lic._load_registry()
    for item in registry.get("licenses", []):
        if item.get("license_number") == number:
            item.update({
                "department": department,
                "workstation_code": workstation_code,
                "name": display_name,
                "months": 6,
                "status": "issued",
                "server_ready": True,
            })
            break
    lic._save_registry(registry)

    payload = _package_payload_from_registry(_find_registry_item(number))
    Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


class WorkstationDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Создать новую лицензию")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Подразделение:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.department = ttk.Entry(frame, width=42)
        self.department.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(frame, text="Номер / название рабочего места:").grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.workstation = ttk.Entry(frame, width=42)
        self.workstation.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(frame, text="Будет присвоен постоянный номер CPS-xxxxxx.\nСрок после первой активации — 6 календарных месяцев.", wraplength=390).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Button(frame, text="Отмена", command=self.destroy).grid(row=5, column=0, sticky="e", padx=(0, 6))
        ttk.Button(frame, text="Создать", command=self._submit).grid(row=5, column=1, sticky="w")
        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.department.focus_set()

    def _submit(self):
        department = _clean(self.department.get())
        workstation = _clean(self.workstation.get())
        if not department:
            messagebox.showerror("Рабочее место", "Укажите подразделение.", parent=self); return
        if not workstation:
            messagebox.showerror("Рабочее место", "Укажите номер или название рабочего места.", parent=self); return
        self.result = (department, workstation)
        self.destroy()


class RegistryWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Реестр лицензий Cheviplus Photo Studio")
        self.geometry("1030x480")
        self.minsize(880, 380)
        self.transient(parent)

        top = ttk.Frame(self, padding=(12, 12, 12, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Локальный реестр лицензий", font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Button(top, text="Создать новую лицензию", command=self._create_license).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Сохранить файл лицензии…", command=self._save_selected_license).pack(side="right", padx=6)
        ttk.Button(top, text="Экспорт CSV", command=self._export_csv).pack(side="right")
        ttk.Button(top, text="Обновить", command=self.refresh).pack(side="right", padx=6)

        body = ttk.Frame(self, padding=(12, 4, 12, 12)); body.pack(fill="both", expand=True)
        columns = ("license", "department", "workstation", "issued", "months", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=14, selectmode="browse")
        headings = {"license":"Лицензия","department":"Подразделение","workstation":"Рабочее место","issued":"Создана","months":"Срок","status":"Статус"}
        widths = {"license":125,"department":210,"workstation":180,"issued":145,"months":80,"status":110}
        for col in columns:
            self.tree.heading(col, text=headings[col]); self.tree.column(col, width=widths[col], minwidth=70, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._save_selected_license())
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in reversed(_registry_rows()):
            self.tree.insert("", "end", values=(row["license_number"], row["department"], row["workstation_code"], row["issued_at"], f"{row['months']} мес.", row["status"]))

    def _create_license(self):
        dialog = WorkstationDialog(self); self.wait_window(dialog)
        if not dialog.result: return
        department, workstation = dialog.result
        default_name = f"{_safe_filename(department)}_{_safe_filename(workstation)}.cpslicense"
        dest = filedialog.asksaveasfilename(parent=self, title="Куда сохранить файл лицензии", defaultextension=".cpslicense", initialfile=default_name, filetypes=[("Cheviplus license", "*.cpslicense")])
        if not dest: return
        try:
            payload = create_named_workstation_package(department, workstation, dest)
        except Exception as exc:
            messagebox.showerror("Лицензия", str(exc), parent=self); return
        self.refresh()
        messagebox.showinfo("Лицензия создана", f"Номер: {payload['license_number']}\nПодразделение: {department}\nРабочее место: {workstation}\n\nФайл сохранён:\n{dest}", parent=self)

    def _selected_license_number(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Реестр лицензий", "Сначала выберите лицензию в таблице.", parent=self); return None
        values = self.tree.item(selected[0], "values")
        return values[0] if values else None

    def _save_selected_license(self):
        number = self._selected_license_number()
        if not number: return
        item = _find_registry_item(number)
        if not item:
            messagebox.showerror("Лицензия", "Запись не найдена.", parent=self); return
        department = _safe_filename(item.get("department", ""))
        workstation = _safe_filename(item.get("workstation_code", ""))
        default_name = f"{number}_{department}_{workstation}.cpslicense"
        dest = filedialog.asksaveasfilename(parent=self, title="Сохранить файл лицензии", defaultextension=".cpslicense", initialfile=default_name, filetypes=[("Cheviplus license", "*.cpslicense")])
        if not dest: return
        try:
            save_existing_license_package(number, dest)
        except Exception as exc:
            messagebox.showerror("Лицензия", f"Не удалось выгрузить файл:\n{exc}", parent=self); return
        messagebox.showinfo("Готово", f"Файл лицензии {number} сохранён:\n{dest}", parent=self)

    def _export_csv(self):
        dest = filedialog.asksaveasfilename(parent=self, title="Экспорт реестра лицензий", defaultextension=".csv", initialfile="Cheviplus_license_registry.csv", filetypes=[("CSV", "*.csv")])
        if not dest: return
        rows = _registry_rows()
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Лицензия", "Подразделение", "Рабочее место", "Создана", "Срок, мес.", "Статус"])
            for r in rows: writer.writerow([r["license_number"], r["department"], r["workstation_code"], r["issued_at"], r["months"], r["status"]])
        messagebox.showinfo("Реестр лицензий", "CSV-файл сохранён.", parent=self)


class AdminRegistryApp(lic.LicenseApp):
    def _build(self):
        super()._build(); self._install_registry_controls()

    def _install_registry_controls(self):
        try: ttk.Button(self.admin_license_box, text="Реестр лицензий", command=self._open_registry).pack(side="right", padx=4)
        except Exception: pass

    def _open_registry(self):
        if self._admin_unlocked: RegistryWindow(self)

    def _prepare_workstation(self):
        if not self._admin_unlocked: return
        window = RegistryWindow(self)
        window.after(100, window._create_license)


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
aq.APP_VERSION = APP_VERSION
aq.APP_BUILD = APP_BUILD
lic.APP_VERSION = APP_VERSION
lic.APP_BUILD = APP_BUILD
