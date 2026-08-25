"""Cheviplus Photo Studio UI cleanup.

- Moves the operator AI quality selector out of the service/manual block and into
  the main Photo for 1C workspace.
- Keeps the original ai_quality_var, so processing behavior is unchanged.
- Hides generic marketplace categories such as 'Прочее' instead of printing a
  meaningless badge on customer-facing cards.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import app
import cheviplus_ai_quality as aiq
import cheviplus_marketplace_visual_v1 as visual
import cheviplus_workspace_modes as workspaces

APP_VERSION = "5.33"
APP_BUILD = "2026.08.25.07"

_ORIGINAL_BUILD = app.App._build
_ORIGINAL_BASE = visual.base
_GENERIC_CATEGORIES = {
    "", "прочее", "прочие", "другое", "другие", "other", "misc", "miscellaneous",
    "автозапчасти", "авто запчасти",
}


def _walk(root):
    yield root
    for child in root.winfo_children():
        yield from _walk(child)


def _text(widget):
    try:
        return str(widget.cget("text") or "").strip()
    except Exception:
        return ""


def _find_main_settings(root):
    candidates=[]
    for node in _walk(root):
        if isinstance(node, ttk.LabelFrame):
            title=_text(node).lower()
            if "стабильная ручная обработка" in title:
                continue
            if "основн" in title and "настрой" in title:
                return node
            if "настрой" in title:
                candidates.append(node)
    return candidates[0] if candidates else None


def _hide_old_ai_controls(self):
    combo=getattr(self,"ai_quality_combo",None)
    if combo is None:return
    parent=combo.master
    for node in list(parent.winfo_children()):
        txt=_text(node).lower()
        if node is combo or "качество ai" in txt or "birefnet" in txt or "быстрый режим" in txt:
            try:node.grid_remove()
            except Exception:
                try:node.pack_forget()
                except Exception:pass


def _add_main_ai_selector(self):
    target=_find_main_settings(self)
    if target is None:return
    row=ttk.Frame(target)
    try:row.grid(row=50,column=0,columnspan=6,sticky="ew",pady=(10,2))
    except Exception:row.pack(fill="x",pady=(8,2))
    ttk.Label(row,text="Качество обработки:").pack(side="left")
    combo=ttk.Combobox(row,textvariable=self.ai_quality_var,values=aiq.MODES,state="readonly",width=32)
    combo.pack(side="left",padx=(8,0))
    self.ai_quality_main_combo=combo


def build(self):
    _ORIGINAL_BUILD(self)
    if not hasattr(self,"ai_quality_var"):
        self.ai_quality_var=tk.StringVar(master=self,value=aiq.MODE_FAST)
    _hide_old_ai_controls(self)
    _add_main_ai_selector(self)


def base_without_generic_category(title,page,cat):
    normalized=str(cat or "").strip().lower()
    if normalized in _GENERIC_CATEGORIES:
        im=visual.Image.new('RGB',visual.SIZE,visual.BG)
        d=visual.ImageDraw.Draw(im)
        d.rectangle((0,0,1200,122),fill=visual.DARK)
        d.text((64,36),title,font=visual.font(42,1),fill='white')
        d.rounded_rectangle((1080,28,1144,92),12,fill=visual.NAVY)
        d.text((1100,42),str(page),font=visual.font(30,1),fill='white')
        return im,d
    return _ORIGINAL_BASE(title,page,cat)


app.App._build=build
visual.base=base_without_generic_category
app.APP_VERSION=APP_VERSION
app.APP_BUILD=APP_BUILD
visual.APP_VERSION=APP_VERSION
visual.APP_BUILD=APP_BUILD
workspaces.APP_VERSION=APP_VERSION
workspaces.APP_BUILD=APP_BUILD
