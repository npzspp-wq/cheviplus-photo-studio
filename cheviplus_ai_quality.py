"""Cheviplus Photo Studio 5.3: adaptive AUTO AI mode."""
from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
import threading
from PIL import Image, ImageFilter, ImageStat
from tkinter import ttk
import app
import cheviplus_product_cutout as pc
import cheviplus_backdrop_quality as bq

APP_VERSION="5.3"; APP_BUILD="2026.08.11.01"
MODE_AUTO="AUTO — скорость + качество"
MODE_FAST="Быстро — локально"
MODE_QUALITY="Максимальное качество AI — локально"
MODES=(MODE_AUTO,MODE_FAST,MODE_QUALITY)
QUALITY_MAX_SIDE=1600; AUTO_SIMPLE_SIDE=1024; AUTO_NORMAL_SIDE=1280; MASK_CACHE_LIMIT=16
_LOCAL=threading.local(); _ORIGINAL_COMPOSE=app.compose_image; _FAST_REMOVE=bq.remove_background
_QUALITY_SESSION=None; _SESSION_LOCK=threading.Lock(); _INFERENCE_LOCK=threading.Lock()
_MASK_CACHE=OrderedDict(); _MASK_CACHE_LOCK=threading.Lock()

def get_quality_session():
 global _QUALITY_SESSION
 if _QUALITY_SESSION is None:
  with _SESSION_LOCK:
   if _QUALITY_SESSION is None:
    from rembg import new_session
    _QUALITY_SESSION=new_session("birefnet-general-lite")
 return _QUALITY_SESSION

def _auto_side(image):
 """Cheap image analysis only selects BiRefNet input resolution; it never changes model/cleanup."""
 rgb=image.convert("RGB"); w,h=rgb.size
 probe=rgb.copy(); probe.thumbnail((384,384),Image.Resampling.BILINEAR)
 gray=probe.convert("L")
 edge_mean=ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
 contrast=ImageStat.Stat(gray).stddev[0]
 # Busy/low-contrast photos are the risky cases: keep proven 1600px quality.
 if edge_mean>24 or contrast<32: return QUALITY_MAX_SIDE
 if edge_mean<13 and contrast>48: return AUTO_SIMPLE_SIDE
 return AUTO_NORMAL_SIDE

def _working_copy(image,max_side):
 w,h=image.size; longest=max(w,h)
 if longest<=max_side:return image.convert("RGBA"),(w,h)
 scale=max_side/float(longest); size=(max(1,round(w*scale)),max(1,round(h*scale)))
 return image.convert("RGBA").resize(size,Image.Resampling.LANCZOS),(w,h)

def _quality_segment_alpha(image,max_side=QUALITY_MAX_SIDE):
 from rembg import remove
 work,original_size=_working_copy(image,max_side)
 with _INFERENCE_LOCK:
  result=remove(work,session=get_quality_session(),alpha_matting=False,post_process_mask=False).convert("RGBA")
 alpha=result.getchannel("A")
 return alpha.resize(original_size,Image.Resampling.LANCZOS) if alpha.size!=original_size else alpha

def _cache_key_from_source(source,mode,side):
 if mode not in (MODE_AUTO,MODE_QUALITY):return None
 try:
  p=Path(source).resolve(); s=p.stat(); return(str(p).lower(),s.st_mtime_ns,s.st_size,mode,side)
 except Exception:return None

def _cache_get(key):
 if key is None:return None
 with _MASK_CACHE_LOCK:
  m=_MASK_CACHE.get(key)
  if m is None:return None
  _MASK_CACHE.move_to_end(key); return m.copy()

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
  if n<min_a or n>max_a or xs.min()<=margin or ys.min()<=margin or xs.max()>=w-1-margin or ys.max()>=h-1-margin:continue
  hole=ndimage.binary_dilation(labels==idx,iterations=1); out[hole]=np.minimum(out[hole],raw[hole])
 return out.astype(np.uint8)

def build_quality_mask(original,max_side=QUALITY_MAX_SIDE):
 import numpy as np
 alpha=np.asarray(_quality_segment_alpha(original,max_side),dtype=np.uint8)
 combined=bq._safe_background_cleanup(original,alpha); support=pc._meaningful_component_mask(combined)
 combined=np.where(support,combined,0).astype(np.uint8); combined=pc._solidify_product_interior(combined)
 combined=_restore_real_holes(alpha,combined); combined=pc._remove_detached_paper_components(original,combined)
 return Image.fromarray(combined,mode="L")

def remove_background(img,**kwargs):
 mode=getattr(_LOCAL,"mode",MODE_FAST)
 if mode==MODE_FAST:return _FAST_REMOVE(img,**kwargs)
 try:
  side=QUALITY_MAX_SIDE if mode==MODE_QUALITY else _auto_side(img)
  source=getattr(_LOCAL,"source",None); key=_cache_key_from_source(source,mode,side); mask=_cache_get(key); hit=mask is not None
  if mask is None:mask=build_quality_mask(img,side); _cache_put(key,mask)
  rgba=img.convert("RGBA"); rgba.putalpha(mask); info=app.analyze_object_shape(mask); info["mask_cache_hit"]=hit; info["ai_input_side"]=side
  return rgba,info
 except Exception as exc:
  if "allocate memory" in str(exc).lower() or "onnxruntimeerror" in str(exc).lower():return _FAST_REMOVE(img,**kwargs)
  raise

def compose_image(*args,processing_mode=MODE_AUTO,**kwargs):
 pm=getattr(_LOCAL,"mode",MODE_FAST); ps=getattr(_LOCAL,"source",None); mode=processing_mode if processing_mode in MODES else MODE_AUTO
 _LOCAL.mode=mode; _LOCAL.source=args[0] if args else kwargs.get("source")
 try:return _ORIGINAL_COMPOSE(*args,**kwargs)
 finally:_LOCAL.mode=pm; _LOCAL.source=ps

def _find_label_frame(root,title):
 for child in root.winfo_children():
  try:
   if isinstance(child,ttk.LabelFrame) and child.cget("text")==title:return child
  except Exception:pass
  found=_find_label_frame(child,title)
  if found is not None:return found
 return None

class AIQualityApp(bq.BackdropQualityApp):
 def _build(self):
  super()._build(); import tkinter as tk
  self._ai_busy=False; self._ai_busy_phase=0; self.ai_quality_var=tk.StringVar(value=MODE_AUTO)
  frame=_find_label_frame(self,"3. Стабильная ручная обработка") or self
  ttk.Label(frame,text="Качество AI:").grid(row=7,column=0,sticky="w",pady=(10,4))
  ttk.Combobox(frame,textvariable=self.ai_quality_var,values=MODES,state="readonly",width=36).grid(row=7,column=1,columnspan=4,sticky="w",padx=8,pady=(10,4))
  ttk.Label(frame,text="AUTO сам выбирает 1024 / 1280 / 1600 px для BiRefNet. Проверенный максимальный режим 1600 px сохранён отдельно.",wraplength=720).grid(row=8,column=0,columnspan=6,sticky="w",pady=(0,4))
 def current_options(self):
  o=super().current_options(); o["processing_mode"]=self.ai_quality_var.get(); return o
 def _begin_ai_indicator(self,text):
  self._ai_busy=True; self._ai_busy_phase=0; self._ai_busy_text=text; self.progress.configure(mode="indeterminate"); self.progress.start(12); self._animate_ai_indicator()
 def _animate_ai_indicator(self):
  if not self._ai_busy:return
  frames=("● ○ ○","○ ● ○","○ ○ ●","○ ● ○"); self.status.set(f"{self._ai_busy_text}  {frames[self._ai_busy_phase%len(frames)]}"); self._ai_busy_phase+=1; self.after(350,self._animate_ai_indicator)
 def _end_ai_indicator(self):self._ai_busy=False; self.progress.stop(); self.progress.configure(mode="determinate")
 def start_preview(self):
  super().start_preview()
  if self.status.get().startswith("Создание предпросмотра"):self._begin_ai_indicator("AI обрабатывает фото — пожалуйста, подождите")
 def show_preview(self,image,name):
  self._end_ai_indicator(); super().show_preview(image,name)
  if self.ai_quality_var.get() in (MODE_AUTO,MODE_QUALITY):self.status.set("Предпросмотр готов • AI-маска сохранена для быстрой обработки")
 def start(self):
  super().start()
  if str(self.start_btn.cget("state"))=="disabled":self._begin_ai_indicator("AI обрабатывает фотографии")
 def batch_worker(self,files):
  try:return super().batch_worker(files)
  finally:self.after(0,self._end_ai_indicator)

app.APP_VERSION=APP_VERSION; app.APP_BUILD=APP_BUILD; app.remove_background=remove_background; app.compose_image=compose_image
