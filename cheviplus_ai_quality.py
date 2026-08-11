"""Cheviplus Photo Studio 5.6: two proven modes plus protected admin settings."""
from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
import hashlib
import hmac
import json
import os
import secrets
import threading
from PIL import Image
from tkinter import ttk
import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION="5.6"
APP_BUILD="2026.08.11.02"
MODE_FAST="Быстро — локально"
MODE_QUALITY="Максимальное качество AI — локально"
MODES=(MODE_FAST, MODE_QUALITY)
QUALITY_MAX_SIDE=1600
MASK_CACHE_LIMIT=16
PIN_ITERATIONS=200_000
_LOCAL=threading.local()
_ORIGINAL_COMPOSE=app.compose_image
_FAST_REMOVE=bq.remove_background
_QUALITY_SESSION=None
_SESSION_LOCK=threading.Lock()
_INFERENCE_LOCK=threading.Lock()
_MASK_CACHE=OrderedDict()
_MASK_CACHE_LOCK=threading.Lock()


def _admin_config_path():
 base=os.environ.get("APPDATA") or str(Path.home())
 return Path(base)/"CheviplusPhotoStudio"/"admin.json"


def _hash_pin(pin,salt=None):
 if salt is None:salt=secrets.token_bytes(16)
 digest=hashlib.pbkdf2_hmac("sha256",pin.encode("utf-8"),salt,PIN_ITERATIONS)
 return salt.hex(),digest.hex()


def _verify_pin(pin,salt_hex,digest_hex):
 try:
  salt=bytes.fromhex(salt_hex); expected=bytes.fromhex(digest_hex)
 except ValueError:return False
 actual=hashlib.pbkdf2_hmac("sha256",pin.encode("utf-8"),salt,PIN_ITERATIONS)
 return hmac.compare_digest(actual,expected)


def _load_admin_record():
 path=_admin_config_path()
 try:
  data=json.loads(path.read_text(encoding="utf-8"))
  if data.get("salt") and data.get("hash"):return data
 except Exception:pass
 return None


def _save_admin_record(pin):
 salt,digest=_hash_pin(pin); path=_admin_config_path(); path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps({"salt":salt,"hash":digest,"version":1},ensure_ascii=False,indent=2),encoding="utf-8")


def get_quality_session():
 global _QUALITY_SESSION
 if _QUALITY_SESSION is None:
  with _SESSION_LOCK:
   if _QUALITY_SESSION is None:
    from rembg import new_session
    _QUALITY_SESSION=new_session("birefnet-general-lite")
 return _QUALITY_SESSION


def _working_copy(image):
 w,h=image.size; longest=max(w,h)
 if longest<=QUALITY_MAX_SIDE:return image.convert("RGBA"),(w,h)
 scale=QUALITY_MAX_SIDE/float(longest); size=(max(1,round(w*scale)),max(1,round(h*scale)))
 return image.convert("RGBA").resize(size,Image.Resampling.LANCZOS),(w,h)


def _quality_segment_alpha(image):
 from rembg import remove
 work,original_size=_working_copy(image)
 with _INFERENCE_LOCK:
  result=remove(work,session=get_quality_session(),alpha_matting=False,post_process_mask=False).convert("RGBA")
 alpha=result.getchannel("A")
 return alpha.resize(original_size,Image.Resampling.LANCZOS) if alpha.size!=original_size else alpha


def _cache_key_from_source(source,mode):
 if mode!=MODE_QUALITY:return None
 try:
  path=Path(source).resolve(); stat=path.stat(); return(str(path).lower(),stat.st_mtime_ns,stat.st_size,mode)
 except Exception:return None


def _cache_get(key):
 if key is None:return None
 with _MASK_CACHE_LOCK:
  mask=_MASK_CACHE.get(key)
  if mask is None:return None
  _MASK_CACHE.move_to_end(key); return mask.copy()


def _cache_put(key,mask):
 if key is None:return
 with _MASK_CACHE_LOCK:
  _MASK_CACHE[key]=mask.copy(); _MASK_CACHE.move_to_end(key)
  while len(_MASK_CACHE)>MASK_CACHE_LIMIT:_MASK_CACHE.popitem(last=False)


def _restore_real_holes(raw_alpha,cleaned):
 import numpy as np
 from scipy import ndimage
 raw=np.asarray(raw_alpha,dtype=np.uint8); out=np.asarray(cleaned,dtype=np.uint8).copy(); h,w=raw.shape; area=h*w
 labels,count=ndimage.label((raw<=24)&(out>=160)); min_a=max(20,int(area*.00003)); max_a=max(min_a+1,int(area*.08)); margin=max(2,int(min(h,w)*.004))
 for idx in range(1,count+1):
  ys,xs=np.where(labels==idx); n=len(xs)
  if n<min_a or n>max_a:continue
  if xs.min()<=margin or ys.min()<=margin or xs.max()>=w-1-margin or ys.max()>=h-1-margin:continue
  hole=ndimage.binary_dilation(labels==idx,iterations=1); out[hole]=np.minimum(out[hole],raw[hole])
 return out.astype(np.uint8)


def build_quality_mask(original):
 import numpy as np
 alpha=np.asarray(_quality_segment_alpha(original),dtype=np.uint8)
 combined=bq._safe_background_cleanup(original,alpha); support=pc._meaningful_component_mask(combined)
 combined=np.where(support,combined,0).astype(np.uint8); combined=pc._solidify_product_interior(combined)
 combined=_restore_real_holes(alpha,combined); combined=pc._remove_detached_paper_components(original,combined)
 return Image.fromarray(combined,mode="L")


def remove_background(img,**kwargs):
 mode=getattr(_LOCAL,"mode",MODE_FAST)
 if mode!=MODE_QUALITY:return _FAST_REMOVE(img,**kwargs)
 try:
  key=getattr(_LOCAL,"cache_key",None); mask=_cache_get(key); hit=mask is not None
  if mask is None:mask=build_quality_mask(img); _cache_put(key,mask)
  rgba=img.convert("RGBA"); rgba.putalpha(mask); info=app.analyze_object_shape(mask); info["mask_cache_hit"]=hit
  return rgba,info
 except Exception as exc:
  message=str(exc).lower()
  if "allocate memory" in message or "onnxruntimeerror" in message:return _FAST_REMOVE(img,**kwargs)
  raise


def compose_image(*args,processing_mode=MODE_FAST,**kwargs):
 previous_mode=getattr(_LOCAL,"mode",MODE_FAST); previous_key=getattr(_LOCAL,"cache_key",None)
 mode=processing_mode if processing_mode in MODES else MODE_FAST
 _LOCAL.mode=mode; source=args[0] if args else kwargs.get("source"); _LOCAL.cache_key=_cache_key_from_source(source,mode)
 try:return _ORIGINAL_COMPOSE(*args,**kwargs)
 finally:_LOCAL.mode=previous_mode; _LOCAL.cache_key=previous_key


def _find_label_frame(root,title):
 for child in root.winfo_children():
  try:
   if isinstance(child,ttk.LabelFrame) and child.cget("text")==title:return child
  except Exception:pass
  found=_find_label_frame(child,title)
  if found is not None:return found
 return None


def _all_children(root):
 for child in root.winfo_children():
  yield child
  yield from _all_children(child)


class AIQualityApp(bq.BackdropQualityApp):
 def _build(self):
  super()._build(); import tkinter as tk
  self._ai_busy=False; self._ai_busy_phase=0; self._admin_unlocked=False
  self.ai_quality_var=tk.StringVar(value=MODE_FAST)
  frame=_find_label_frame(self,"3. Стабильная ручная обработка") or self
  ttk.Label(frame,text="Качество AI:").grid(row=7,column=0,sticky="w",pady=(10,4))
  self.ai_quality_combo=ttk.Combobox(frame,textvariable=self.ai_quality_var,values=MODES,state="readonly",width=36)
  self.ai_quality_combo.grid(row=7,column=1,columnspan=4,sticky="w",padx=8,pady=(10,4))
  ttk.Label(frame,text="Быстрый режим — для массовой обработки. Максимальное качество — BiRefNet Lite для сложных фото.",wraplength=720).grid(row=8,column=0,columnspan=6,sticky="w",pady=(0,4))
  admin_bar=ttk.Frame(frame); admin_bar.grid(row=9,column=0,columnspan=6,sticky="w",pady=(8,3))
  self.admin_button=ttk.Button(admin_bar,text="🔒 Настройки администратора",command=self._toggle_admin_settings)
  self.admin_button.pack(side="left")
  self.change_pin_button=ttk.Button(admin_bar,text="Сменить PIN",command=self._change_pin)
  self.admin_note=ttk.Label(admin_bar,text="  Основные настройки защищены")
  self.admin_note.pack(side="left")
  self.after_idle(self._apply_admin_lock)

 def _protected_frames(self):
  result=[]
  for widget in _all_children(self):
   try:
    if isinstance(widget,ttk.LabelFrame):
     title=str(widget.cget("text")).strip()
     if title.startswith(("1.","2.","3.")):result.append(widget)
   except Exception:pass
  return result

 def _set_widget_locked(self,widget,locked):
  if widget in (getattr(self,"admin_button",None),getattr(self,"change_pin_button",None),getattr(self,"ai_quality_combo",None)):return
  cls=widget.winfo_class().lower()
  editable=("entry","spinbox","combobox","checkbutton","radiobutton","scale","button")
  if not any(name in cls for name in editable):return
  try:
   if locked:
    if not hasattr(widget,"_cheviplus_prev_state"):
     try:widget._cheviplus_prev_state=str(widget.cget("state"))
     except Exception:widget._cheviplus_prev_state="normal"
    widget.configure(state="disabled")
   else:
    previous=getattr(widget,"_cheviplus_prev_state","normal")
    widget.configure(state=previous)
  except Exception:pass

 def _apply_admin_lock(self):
  locked=not self._admin_unlocked
  for frame in self._protected_frames():
   for widget in _all_children(frame):self._set_widget_locked(widget,locked)
  self.ai_quality_combo.configure(state="readonly")
  if self._admin_unlocked:
   self.admin_button.configure(text="🔓 Заблокировать настройки")
   self.change_pin_button.pack(side="left",padx=(8,0))
   self.admin_note.configure(text="  Режим администратора открыт")
  else:
   self.admin_button.configure(text="🔒 Настройки администратора")
   self.change_pin_button.pack_forget()
   self.admin_note.configure(text="  Основные настройки защищены")

 def _create_first_pin(self):
  from tkinter import simpledialog,messagebox
  pin=simpledialog.askstring("PIN администратора","Придумайте PIN из 4–8 цифр:",show="*",parent=self)
  if pin is None:return False
  if not(pin.isdigit() and 4<=len(pin)<=8):
   messagebox.showerror("PIN","PIN должен содержать от 4 до 8 цифр.",parent=self); return False
  repeat=simpledialog.askstring("PIN администратора","Повторите PIN:",show="*",parent=self)
  if repeat!=pin:
   messagebox.showerror("PIN","PIN-коды не совпадают.",parent=self); return False
  try:_save_admin_record(pin)
  except Exception as exc:
   messagebox.showerror("PIN",f"Не удалось сохранить PIN: {exc}",parent=self); return False
  messagebox.showinfo("PIN","PIN администратора создан. Настройки открыты.",parent=self); return True

 def _toggle_admin_settings(self):
  from tkinter import simpledialog,messagebox
  if self._admin_unlocked:
   self._admin_unlocked=False; self._apply_admin_lock(); return
  record=_load_admin_record()
  if record is None:
   if not self._create_first_pin():return
  else:
   pin=simpledialog.askstring("Настройки администратора","Введите PIN:",show="*",parent=self)
   if pin is None:return
   if not _verify_pin(pin,record.get("salt",""),record.get("hash","")):
    messagebox.showerror("Доступ запрещён","Неверный PIN.",parent=self); return
  self._admin_unlocked=True; self._apply_admin_lock()

 def _change_pin(self):
  from tkinter import simpledialog,messagebox
  if not self._admin_unlocked:return
  new_pin=simpledialog.askstring("Смена PIN","Новый PIN из 4–8 цифр:",show="*",parent=self)
  if new_pin is None:return
  if not(new_pin.isdigit() and 4<=len(new_pin)<=8):
   messagebox.showerror("PIN","PIN должен содержать от 4 до 8 цифр.",parent=self); return
  repeat=simpledialog.askstring("Смена PIN","Повторите новый PIN:",show="*",parent=self)
  if repeat!=new_pin:
   messagebox.showerror("PIN","PIN-коды не совпадают.",parent=self); return
  try:_save_admin_record(new_pin)
  except Exception as exc:
   messagebox.showerror("PIN",f"Не удалось сохранить PIN: {exc}",parent=self); return
  messagebox.showinfo("PIN","PIN администратора изменён.",parent=self)

 def current_options(self):
  options=super().current_options(); options["processing_mode"]=self.ai_quality_var.get(); return options
 def _begin_ai_indicator(self,text):
  self._ai_busy=True; self._ai_busy_phase=0; self._ai_busy_text=text; self.progress.configure(mode="indeterminate"); self.progress.start(12); self._animate_ai_indicator()
 def _animate_ai_indicator(self):
  if not self._ai_busy:return
  frames=("● ○ ○","○ ● ○","○ ○ ●","○ ● ○"); self.status.set(f"{self._ai_busy_text}  {frames[self._ai_busy_phase%len(frames)]}"); self._ai_busy_phase+=1; self.after(350,self._animate_ai_indicator)
 def _end_ai_indicator(self):
  self._ai_busy=False; self.progress.stop(); self.progress.configure(mode="determinate")
 def start_preview(self):
  super().start_preview()
  if self.status.get().startswith("Создание предпросмотра"):self._begin_ai_indicator("AI обрабатывает фото — пожалуйста, подождите")
 def show_preview(self,image,name):
  self._end_ai_indicator(); super().show_preview(image,name)
  if self.ai_quality_var.get()==MODE_QUALITY:self.status.set("Предпросмотр готов • AI-маска сохранена для быстрой обработки")
 def start(self):
  super().start()
  if str(self.start_btn.cget("state"))=="disabled":self._begin_ai_indicator("AI обрабатывает фотографии")
 def batch_worker(self,files):
  try:return super().batch_worker(files)
  finally:self.after(0,self._end_ai_indicator)

app.APP_VERSION=APP_VERSION
app.APP_BUILD=APP_BUILD
app.remove_background=remove_background
app.compose_image=compose_image
