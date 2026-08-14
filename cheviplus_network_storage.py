"""Cheviplus Photo Studio 5.14: safe local/network output folders.

Adds preflight write checks for local, mapped and UNC paths and makes image
writes safer on Windows/network shares. It never bypasses Windows/SMB ACLs.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from tkinter import messagebox

import app

APP_VERSION = "5.14"
APP_BUILD = "2026.08.14.02"
_ORIGINAL_SAVE_RESULT = app.save_result
_ORIGINAL_START = app.App.start
_ORIGINAL_OPEN_OUTPUT = app.App.open_output


def _path_kind(path: Path) -> str:
    text = str(path)
    if text.startswith("\\\\") or text.startswith("//"):
        return "сетевая UNC-папка"
    if len(text) >= 2 and text[1] == ":":
        return "диск/подключённый сетевой диск"
    return "папка"


def check_writable_folder(path_value, create=True):
    """Return (ok, message). Test real create/write/flush/delete permissions."""
    raw = str(path_value or "").strip().strip('"')
    if not raw:
        return False, "Папка для готовых фото не выбрана."
    path = Path(raw)
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return False, f"Папка не найдена: {path}"
        if not path.is_dir():
            return False, f"Указанный путь не является папкой: {path}"

        probe = path / f".cheviplus_write_test_{uuid.uuid4().hex}.tmp"
        try:
            with open(probe, "xb") as fh:
                fh.write(b"Cheviplus Photo Studio write test")
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
        finally:
            try:
                probe.unlink(missing_ok=True)
            except Exception:
                pass
        return True, f"Доступ подтверждён: {_path_kind(path)} — {path}"
    except PermissionError as exc:
        return False, (
            f"Нет прав на запись в выбранную папку:\n{path}\n\n"
            "Windows или сервер запретил создание/изменение файлов. "
            "Проверьте права пользователя на эту сетевую папку.\n"
            f"Системная ошибка: {exc}"
        )
    except OSError as exc:
        return False, (
            f"Папка сейчас недоступна:\n{path}\n\n"
            "Проверьте подключение к серверу/диску и права пользователя.\n"
            f"Системная ошибка: {exc}"
        )


def _replace_with_retry(temp_path: Path, final_path: Path, attempts=6):
    """Windows/SMB can briefly lock a just-written file; retry short locks."""
    last = None
    for attempt in range(attempts):
        try:
            os.replace(str(temp_path), str(final_path))
            return
        except PermissionError as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.15 * (attempt + 1))
    if last:
        raise last


def network_safe_save_result(image, source, output_dir, output_format, target_kb=0, jpeg_quality=90):
    output_dir = Path(output_dir)
    ok, reason = check_writable_folder(output_dir, create=True)
    if not ok:
        raise PermissionError(reason)

    # Existing app.save_result already supports Path/UNC correctly. Save to the
    # requested directory, but convert raw permission errors into useful text.
    try:
        return _ORIGINAL_SAVE_RESULT(
            image, source, output_dir, output_format,
            target_kb=target_kb, jpeg_quality=jpeg_quality,
        )
    except PermissionError as exc:
        raise PermissionError(
            f"Нет доступа на запись: {output_dir}. "
            "Закройте файл, если он открыт в другой программе, и проверьте права Windows/сервера. "
            f"{exc}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Не удалось сохранить в {output_dir}. Возможно, сетевой ресурс временно недоступен. {exc}"
        ) from exc


def start_with_output_preflight(self):
    ok, reason = check_writable_folder(self.output_var.get(), create=True)
    if not ok:
        self.status.set("Нет доступа к папке готовых фото")
        try:
            self.write_log("ПАПКА НЕДОСТУПНА: " + reason.replace("\n", " "))
        except Exception:
            pass
        messagebox.showerror("Нет доступа к папке", reason, parent=self)
        return
    try:
        self.write_log("Проверка папки: " + reason)
    except Exception:
        pass
    return _ORIGINAL_START(self)


def open_output_safe(self):
    path = Path(self.output_var.get())
    ok, reason = check_writable_folder(path, create=True)
    if not ok:
        messagebox.showerror("Папка недоступна", reason, parent=self)
        return
    try:
        os.startfile(str(path))
    except OSError as exc:
        messagebox.showerror("Не удалось открыть папку", str(exc), parent=self)


def install():
    app.save_result = network_safe_save_result
    app.App.start = start_with_output_preflight
    app.App.open_output = open_output_safe
    app.APP_VERSION = APP_VERSION
    app.APP_BUILD = APP_BUILD


install()
