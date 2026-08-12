"""Cheviplus Photo Studio 5.10: administrator workstation creator and local license registry.

This module deliberately builds on the proven 5.9 license/processing stack. It does not
change photo processing. The local registry format is designed to be importable by the
future license server without changing CPS license numbers already issued.
"""
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

APP_VERSION = "5.10"
APP_BUILD = "2026.08.12.01"


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
            "status": item.get("status", "issued"),
            "months": item.get("months", 6),
        })
    return rows


def create_named_workstation_package(department: str, workstation_code: str, destination: str | Path):
    """Create one signed activation package and permanently register its CPS number locally."""
    department = _clean(department)
    workstation_code = _clean(workstation_code)
    if not department:
        raise ValueError("Укажите подразделение")
    if not workstation_code:
        raise ValueError("Укажите номер или название рабочего места")

    now = datetime.now()
    issued_at = now.isoformat(timespec="seconds")
    token = secrets.token_urlsafe(18)
    display_name = f"{department} — {workstation_code}"
    number = lic._allocate_license_number(display_name, token, issued_at)

    # Enrich the administrator registry entry. The CPS number remains permanent.
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

    payload = {
        "version": 3,
        "license_number": number,
        "department": department,
        "workstation_code": workstation_code,
        "workstation_name": display_name,
        "token": token,
        "months": 6,
        "issued_at": issued_at,
        "server_ready": True,
    }
    payload["signature"] = lic._sign_payload(payload)
    Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


class WorkstationDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Создать рабочее место")
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

        ttk.Label(
            frame,
            text="После сохранения будет присвоен постоянный номер лицензии CPS-xxxxxx.\nСрок лицензии после первой активации — 6 календарных месяцев.",
            wraplength=390,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Button(frame, text="Отмена", command=self.destroy).grid(row=5, column=0, sticky="e", padx=(0, 6))
        ttk.Button(frame, text="Создать", command=self._submit).grid(row=5, column=1, sticky="w")
        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.department.focus_set()
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 3)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _submit(self):
        department = _clean(self.department.get())
        workstation = _clean(self.workstation.get())
        if not department:
            messagebox.showerror("Рабочее место", "Укажите подразделение.", parent=self)
            return
        if not workstation:
            messagebox.showerror("Рабочее место", "Укажите номер или название рабочего места.", parent=self)
            return
        self.result = (department, workstation)
        self.destroy()


class RegistryWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Реестр лицензий Cheviplus Photo Studio")
        self.geometry("970x440")
        self.minsize(820, 360)
        self.transient(parent)

        top = ttk.Frame(self, padding=(12, 12, 12, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Локальный реестр лицензий", font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Button(top, text="Экспорт CSV", command=self._export_csv).pack(side="right")
        ttk.Button(top, text="Обновить", command=self.refresh).pack(side="right", padx=6)

        body = ttk.Frame(self, padding=(12, 4, 12, 12))
        body.pack(fill="both", expand=True)
        columns = ("license", "department", "workstation", "issued", "months", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=14)
        headings = {
            "license": "Лицензия",
            "department": "Подразделение",
            "workstation": "Рабочее место",
            "issued": "Создана",
            "months": "Срок",
            "status": "Статус",
        }
        widths = {"license": 125, "department": 190, "workstation": 170, "issued": 145, "months": 80, "status": 110}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=70, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in reversed(_registry_rows()):
            self.tree.insert("", "end", values=(
                row["license_number"], row["department"], row["workstation_code"],
                row["issued_at"], f"{row['months']} мес.", row["status"],
            ))

    def _export_csv(self):
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Экспорт реестра лицензий",
            defaultextension=".csv",
            initialfile="Cheviplus_license_registry.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not dest:
            return
        rows = _registry_rows()
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Лицензия", "Подразделение", "Рабочее место", "Создана", "Срок, мес.", "Статус"])
            for r in rows:
                writer.writerow([r["license_number"], r["department"], r["workstation_code"], r["issued_at"], r["months"], r["status"]])
        messagebox.showinfo("Реестр лицензий", "CSV-файл сохранён.", parent=self)


class AdminRegistryApp(lic.LicenseApp):
    """Full 5.9 app plus local administrator registry; photo processing is inherited unchanged."""

    def _build(self):
        super()._build()
        self._install_registry_controls()

    def _install_registry_controls(self):
        # Add only administrator controls; employee interface stays unchanged.
        try:
            ttk.Button(self.admin_license_box, text="Реестр лицензий", command=self._open_registry).pack(side="right", padx=4)
        except Exception:
            pass

    def _open_registry(self):
        if not self._admin_unlocked:
            return
        RegistryWindow(self)

    def _prepare_workstation(self):
        if not self._admin_unlocked:
            return
        dialog = WorkstationDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        department, workstation = dialog.result
        default_name = f"Cheviplus_{_safe_filename(department)}_{_safe_filename(workstation)}.cpslicense"
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Сохранить лицензию для подразделения",
            defaultextension=".cpslicense",
            initialfile=default_name,
            filetypes=[("Cheviplus license", "*.cpslicense")],
        )
        if not dest:
            return
        try:
            payload = create_named_workstation_package(department, workstation, dest)
        except Exception as exc:
            messagebox.showerror("Лицензия", f"Не удалось создать рабочее место:\n{exc}", parent=self)
            return
        messagebox.showinfo(
            "Рабочее место создано",
            f"Подразделение: {department}\n"
            f"Рабочее место: {workstation}\n"
            f"Номер лицензии: {payload['license_number']}\n"
            f"Срок после активации: 6 месяцев.\n\n"
            "Запись сохранена в вашем локальном реестре. Отправьте файл .cpslicense вместе с обычным Setup.",
            parent=self,
        )


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
aq.APP_VERSION = APP_VERSION
aq.APP_BUILD = APP_BUILD
lic.APP_VERSION = APP_VERSION
lic.APP_BUILD = APP_BUILD
