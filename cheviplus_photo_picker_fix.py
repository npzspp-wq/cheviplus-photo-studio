"""Restore and harden the core 'Выбрать фото' command.

Marketplace extensions must never interfere with the original photo workflow.
This patch replaces only the photo picker method and leaves processing intact.
"""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import app

APP_VERSION = "5.24"
APP_BUILD = "2026.08.24.12"


def choose_multiple_files_fixed(self):
    """Open Windows file picker reliably and register selected source photos."""
    try:
        initial = None
        try:
            raw = self.input_var.get().strip()
            candidate = Path(raw) if raw else app.APP_DIR
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.exists():
                initial = str(candidate)
        except Exception:
            initial = None

        kwargs = dict(
            parent=self,
            title="Выберите фотографии",
            filetypes=[
                ("Изображения", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("Все файлы", "*.*"),
            ],
        )
        if initial:
            kwargs["initialdir"] = initial

        paths = filedialog.askopenfilenames(**kwargs)
        if not paths:
            return

        selected = []
        for value in paths:
            path = Path(value)
            if path.is_file() and path.suffix.lower() in app.SUPPORTED:
                selected.append(path)

        if not selected:
            messagebox.showwarning(
                "Фотографии",
                "Выбранные файлы не поддерживаются.",
                parent=self,
            )
            return

        self.selected_files = selected
        self.preview_source = selected[0]
        count = len(selected)
        if hasattr(self, "selection_info"):
            self.selection_info.set(f"Выбрано файлов: {count}")
        if hasattr(self, "status"):
            self.status.set(f"Выбрано файлов: {count}")

        # Keep input path useful for the next picker without changing batch logic.
        try:
            self.input_var.set(str(selected[0].parent))
        except Exception:
            pass
    except Exception as exc:
        messagebox.showerror(
            "Ошибка выбора фото",
            f"Не удалось открыть или выбрать фотографии:\n{exc}",
            parent=self,
        )


app.App.choose_multiple_files = choose_multiple_files_fixed
app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
