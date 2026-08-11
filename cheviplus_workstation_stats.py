"""Cheviplus Photo Studio 5.7: local workstation identity and processing counters."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import os
import threading
import time
import uuid
from tkinter import ttk, messagebox

import app
import cheviplus_ai_quality as aq

APP_VERSION = "5.7"
APP_BUILD = "2026.08.11.03"
_STATS_LOCK = threading.Lock()


def _data_dir():
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "CheviplusPhotoStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stats_path():
    return _data_dir() / "workstation_stats.json"


def _new_stats():
    return {
        "version": 1,
        "workstation_id": "CP-" + uuid.uuid4().hex[:12].upper(),
        "total_ok": 0,
        "total_errors": 0,
        "days": {},
        "history": [],
    }


def load_stats():
    with _STATS_LOCK:
        try:
            data = json.loads(_stats_path().read_text(encoding="utf-8"))
            if data.get("workstation_id"):
                data.setdefault("total_ok", 0)
                data.setdefault("total_errors", 0)
                data.setdefault("days", {})
                data.setdefault("history", [])
                return data
        except Exception:
            pass
        data = _new_stats()
        _save_stats_unlocked(data)
        return data


def _save_stats_unlocked(data):
    path = _stats_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def record_batch(ok, errors, mode, elapsed_seconds):
    with _STATS_LOCK:
        try:
            data = json.loads(_stats_path().read_text(encoding="utf-8"))
        except Exception:
            data = _new_stats()
        day = datetime.now().strftime("%Y-%m-%d")
        item = data.setdefault("days", {}).setdefault(day, {"ok": 0, "errors": 0, "batches": 0})
        item["ok"] += int(ok); item["errors"] += int(errors); item["batches"] += 1
        data["total_ok"] = int(data.get("total_ok", 0)) + int(ok)
        data["total_errors"] = int(data.get("total_errors", 0)) + int(errors)
        history = data.setdefault("history", [])
        history.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "ok": int(ok),
            "errors": int(errors),
            "seconds": round(float(elapsed_seconds), 1),
        })
        if len(history) > 500:
            del history[:-500]
        _save_stats_unlocked(data)
        return data


def reset_counters_keep_id():
    with _STATS_LOCK:
        data = load_stats() if False else None
        try:
            old = json.loads(_stats_path().read_text(encoding="utf-8"))
            wid = old.get("workstation_id") or _new_stats()["workstation_id"]
        except Exception:
            wid = _new_stats()["workstation_id"]
        data = _new_stats(); data["workstation_id"] = wid
        _save_stats_unlocked(data)
        return data


class WorkstationStatsApp(aq.AIQualityApp):
    def _build(self):
        super()._build()
        self._batch_started_at = None
        self._batch_ok = 0
        self._batch_errors = 0
        self._batch_tracking = False
        self.stats = load_stats()
        self._build_stats_panel()

    def _build_stats_panel(self):
        # Compact panel under the existing left controls; no processing settings are changed.
        left = None
        for widget in self.winfo_children():
            if widget.winfo_class().lower().endswith("panedwindow"):
                continue
        # Use the stable manual-processing frame so the panel remains visible on different resolutions.
        frame = aq._find_label_frame(self, "3. Стабильная ручная обработка") or self
        box = ttk.LabelFrame(frame, text="Статистика рабочего места", padding=6)
        box.grid(row=10, column=0, columnspan=6, sticky="ew", pady=(7, 3))
        self.stats_text = ttk.Label(box, text="", justify="left")
        self.stats_text.pack(side="left", fill="x", expand=True)
        self.reset_stats_button = ttk.Button(box, text="Сбросить счётчик", command=self._reset_stats)
        self.reset_stats_button.pack(side="right", padx=(8, 0))
        self._refresh_stats_panel()
        self.after_idle(self._sync_stats_admin_state)

    def _sync_stats_admin_state(self):
        try:
            self.reset_stats_button.configure(state="normal" if self._admin_unlocked else "disabled")
        except Exception:
            pass

    def _apply_admin_lock(self):
        super()._apply_admin_lock()
        self._sync_stats_admin_state()

    def _refresh_stats_panel(self):
        self.stats = load_stats()
        today = datetime.now().strftime("%Y-%m-%d")
        day = self.stats.get("days", {}).get(today, {})
        self.stats_text.configure(text=(
            f"ID: {self.stats['workstation_id']}    "
            f"Сегодня: {int(day.get('ok', 0))}    "
            f"Всего: {int(self.stats.get('total_ok', 0))}    "
            f"Ошибок: {int(self.stats.get('total_errors', 0))}"
        ))

    def _reset_stats(self):
        if not self._admin_unlocked:
            return
        if not messagebox.askyesno("Сброс статистики", "Сбросить счётчики этого рабочего места?\nID рабочего места сохранится.", parent=self):
            return
        self.stats = reset_counters_keep_id()
        self._refresh_stats_panel()

    def start(self):
        # Tracking starts only when a real batch is accepted by the base application.
        self._batch_ok = 0; self._batch_errors = 0; self._batch_started_at = time.monotonic()
        before = str(self.start_btn.cget("state"))
        super().start()
        self._batch_tracking = str(self.start_btn.cget("state")) == "disabled"
        if not self._batch_tracking:
            self._batch_started_at = None

    def write_log(self, text):
        if getattr(self, "_batch_tracking", False):
            if text.startswith("OK "):
                self._batch_ok += 1
            elif text.startswith("ОШИБКА ") or text.startswith("ПРОПУЩЕНО "):
                self._batch_errors += 1
        super().write_log(text)

    def batch_worker(self, files):
        try:
            return super().batch_worker(files)
        finally:
            if getattr(self, "_batch_tracking", False):
                self.after(700, self._finish_stats_batch)

    def _finish_stats_batch(self):
        if not self._batch_tracking:
            return
        self._batch_tracking = False
        elapsed = time.monotonic() - self._batch_started_at if self._batch_started_at else 0.0
        self.stats = record_batch(self._batch_ok, self._batch_errors, self.ai_quality_var.get(), elapsed)
        self._refresh_stats_panel()


app.APP_VERSION = APP_VERSION
app.APP_BUILD = APP_BUILD
aq.APP_VERSION = APP_VERSION
aq.APP_BUILD = APP_BUILD
