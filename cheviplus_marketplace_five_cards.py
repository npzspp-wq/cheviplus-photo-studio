from pathlib import Path
import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw
import app
import cheviplus_marketplace_catalog as catalog
import cheviplus_marketplace_visual_v1 as visual
APP_VERSION='5.27'; APP_BUILD='2026.08.25.01'
DATA_FILE=catalog.CATALOG_DIR/'marketplace_extra_blocks.json'
_ORIGINAL_BUILD=app.App._build

def key(p): return catalog.normalize_key(p.get('article') or p.get('code') or p.get('query') or '')
def load_all():
    try:return json.loads(DATA_FILE.read_text(encoding='utf-8')) if DATA_FILE.exists() else {}
    except Exception:return {}
def save_all(data):
    catalog.CATALOG_DIR.mkdir(parents=True,exist_ok=True); DATA_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def get_extra(p): return load_all().get(key(p),{'characteristics':[],'advantages':[],'package':[]})
def lines(text): return [x.strip() for x in text.splitlines() if x.strip()]
def info_card(photo,p,title,page,items,brand):
    im,d=visual.base(title,page,p.get('marketplace_category')); y=245
    for i,item in enumerate(items[:6],1):
        d.rounded_rectangle((64,y,1136,y+112),22,fill='white',outline=visual.LINE,width=2); d.ellipse((90,y+32,138,y+80),fill=visual.RED); d.text((106,y+36),str(i),font=visual.font(21,1),fill='white')
        f=visual.font(34,1)
        for row in visual.wrap(d,item,f,920,2): d.text((166,y+25),row,font=f,fill=visual.TEXT); y+=38
        y+=88 if y<400 else 36
        if y>1000:break
    top=max(y+20,760); d.rounded_rectangle((190,top,1010,1480),30,fill='white',outline=visual.LINE,width=2); obj,pos=visual.fit(photo,(225,top+35,975,1440)); im.paste(obj,pos); visual.footer(d,brand); return im
def generate_five(photo_path,p,out_dir,brand=''):
    photo=Image.open(photo_path).convert('RGB'); out_dir.mkdir(parents=True,exist_ok=True); extra=get_extra(p); items=[('01_OZON_MAIN.jpg',visual.main_card(photo,p,brand))]
    if p.get('applicability'):items.append(('02_OZON_APPLICABILITY.jpg',visual.app_card(photo,p,brand)))
    if extra.get('characteristics'):items.append(('03_OZON_CHARACTERISTICS.jpg',info_card(photo,p,'ХАРАКТЕРИСТИКИ',3,extra['characteristics'],brand)))
    if extra.get('advantages'):items.append(('04_OZON_ADVANTAGES.jpg',info_card(photo,p,'ПРЕИМУЩЕСТВА',4,extra['advantages'],brand)))
    if extra.get('package'):items.append(('05_OZON_PACKAGE.jpg',info_card(photo,p,'КОМПЛЕКТАЦИЯ / ВАЖНО',5,extra['package'],brand)))
    out=[]
    for name,img in items:
        path=out_dir/name; img.save(path,'JPEG',quality=92,optimize=True); out.append(path)
    return out

def editor(self):
    p=getattr(self,'marketplace_selected_product',None)
    if not p: messagebox.showwarning('Маркетплейсы','Сначала найдите товар.'); return
    win=tk.Toplevel(self); win.title('Дополнительные карточки маркетплейса'); win.geometry('820x720'); win.transient(self); win.grab_set(); frame=ttk.Frame(win,padding=16); frame.pack(fill='both',expand=True); data=get_extra(p); widgets={}
    specs=[('characteristics','3. Характеристики','Например: Материал: алюминий 4 мм'),('advantages','4. Преимущества','Только подтвержденные преимущества, одна строка = один пункт'),('package','5. Комплектация / важная информация','Что входит в комплект, особенности установки и т.п.')]
    for field,title,hint in specs:
        ttk.Label(frame,text=title).pack(anchor='w',pady=(6,2)); ttk.Label(frame,text=hint).pack(anchor='w'); t=tk.Text(frame,height=6,wrap='word'); t.pack(fill='x',pady=(3,8)); t.insert('1.0','\n'.join(data.get(field,[]))); widgets[field]=t
    def save():
        all_data=load_all(); all_data[key(p)]={f:lines(w.get('1.0','end')) for f,w in widgets.items()}; save_all(all_data); win.destroy(); update_status(self)
    row=ttk.Frame(frame); row.pack(fill='x',pady=8); ttk.Button(row,text='СОХРАНИТЬ',command=save).pack(side='left'); ttk.Button(row,text='Отмена',command=win.destroy).pack(side='right')
def update_status(self):
    p=getattr(self,'marketplace_selected_product',None)
    if not p:return
    e=get_extra(p); n=1+(1 if p.get('applicability') else 0)+sum(1 for x in ('characteristics','advantages','package') if e.get(x)); self.marketplace_five_status.set('Будет создано карточек: '+str(n)+' из 5')
def find_box(root):
    for w in root.winfo_children():
        try:
            if isinstance(w,ttk.LabelFrame) and 'Маркетплейсы' in w.cget('text'):return w
        except Exception:pass
        f=find_box(w)
        if f:return f
def build(self):
    _ORIGINAL_BUILD(self); self.marketplace_five_status=tk.StringVar(value='Доп. карточки не заполнены'); box=find_box(self)
    if box:
        row=ttk.Frame(box); row.pack(fill='x',pady=(7,0)); ttk.Button(row,text='КАРТОЧКИ 3–5: ЗАПОЛНИТЬ',command=lambda:editor(self)).pack(side='left'); ttk.Label(row,textvariable=self.marketplace_five_status).pack(side='left',padx=10)
app.App._build=build
app.App._marketplace_edit_extra_cards=editor
visual.generate=generate_five
app.APP_VERSION=APP_VERSION; app.APP_BUILD=APP_BUILD; catalog.APP_VERSION=APP_VERSION; catalog.APP_BUILD=APP_BUILD; visual.APP_VERSION=APP_VERSION; visual.APP_BUILD=APP_BUILD
