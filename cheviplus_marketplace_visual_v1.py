from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageFont
import app
import cheviplus_marketplace_cards as cards
import cheviplus_marketplace_catalog as catalog
APP_VERSION='5.26'; APP_BUILD='2026.08.24.14'; SIZE=(1200,1600)
NAVY=(24,49,88); DARK=(15,29,46); RED=(224,45,48); TEXT=(29,34,41); BG=(247,248,250); LINE=(218,222,228)
_ORIGINAL_BUILD=app.App._build; _ORIGINAL_CREATE=app.App._marketplace_create_ozon_cards

def font(size,bold=False):
    for name in (('arialbd.ttf','DejaVuSans-Bold.ttf') if bold else ('arial.ttf','DejaVuSans.ttf')):
        try:return ImageFont.truetype(name,size)
        except Exception:pass
    return ImageFont.load_default()

def tw(d,t,f):
    b=d.textbbox((0,0),t,font=f); return b[2]-b[0]

def wrap(d,text,f,maxw,n=4):
    out=[]; cur=''
    for w in str(text or '').split():
        x=(cur+' '+w).strip()
        if not cur or tw(d,x,f)<=maxw:cur=x
        else:
            out.append(cur); cur=w
            if len(out)>=n-1:break
    if cur and len(out)<n:out.append(cur)
    return out

def fit(photo,box):
    x0,y0,x1,y1=box; bw,bh=x1-x0,y1-y0; im=photo.convert('RGB'); r=min(bw/im.width,bh/im.height,1.3); im=im.resize((int(im.width*r),int(im.height*r)),Image.Resampling.LANCZOS); return im,(x0+(bw-im.width)//2,y0+(bh-im.height)//2)

def brand(profile,bg):
    if profile=='Без бренда':return ''
    if profile in ('DriveTime','Cheviplus'):return profile
    low=bg.lower()
    if 'drive' in low:return 'DriveTime'
    if 'chevi' in low:return 'Cheviplus'
    return ''

def base(title,page,cat):
    im=Image.new('RGB',SIZE,BG); d=ImageDraw.Draw(im); d.rectangle((0,0,1200,122),fill=DARK); d.text((64,36),title,font=font(42,1),fill='white'); d.rounded_rectangle((1080,28,1144,92),12,fill=NAVY); d.text((1100,42),str(page),font=font(30,1),fill='white'); d.rounded_rectangle((64,145,520,198),14,fill=(233,238,245)); d.text((86,158),str(cat or 'АВТОЗАПЧАСТИ').upper(),font=font(24,1),fill=NAVY); return im,d

def footer(d,b):
    if b:
        f=font(30,1); t=b.upper(); d.text((1120-tw(d,t,f),1518),t,font=f,fill=NAVY)

def main_card(photo,p,b):
    im,d=base('КАРТОЧКА ТОВАРА',1,p.get('marketplace_category')); y=235; f=font(54,1)
    for line in wrap(d,str(p.get('name') or 'ТОВАР').upper(),f,1060):d.text((64,y),line,font=f,fill=TEXT); y+=64
    art=str(p.get('article') or p.get('code') or '').strip()
    if art:
        label='АРТИКУЛ  '+art; w=min(650,tw(d,label,font(29,1))+64); d.rounded_rectangle((64,y+10,64+w,y+78),18,fill=RED); d.text((92,y+27),label,font=font(29,1),fill='white'); top=y+112
    else:top=y+35
    d.rounded_rectangle((64,top,1136,1480),34,fill='white',outline=LINE,width=2); obj,pos=fit(photo,(105,top+38,1095,1400)); im.paste(obj,pos); footer(d,b); return im

def app_card(photo,p,b):
    im,d=base('ПРИМЕНЯЕМОСТЬ',2,p.get('marketplace_category')); apps=[str(x).strip() for x in p.get('applicability',[]) if str(x).strip()]; y=235; rowh=122 if len(apps)<=3 else 96; fs=38 if len(apps)<=3 else 31
    for i,line in enumerate(apps[:6],1):
        d.rounded_rectangle((64,y,1136,y+rowh),22,fill='white',outline=LINE,width=2); d.ellipse((88,y+rowh//2-24,136,y+rowh//2+24),fill=RED); d.text((104,y+rowh//2-16),str(i),font=font(21,1),fill='white'); ty=y+22
        for x in wrap(d,line,font(fs,1),930,2):d.text((162,ty),x,font=font(fs,1),fill=TEXT); ty+=int(fs*1.18)
        y+=rowh+14
    top=min(y+30,970); d.rounded_rectangle((120,top,1080,1480),30,fill='white',outline=LINE,width=2); obj,pos=fit(photo,(160,top+35,1040,1440)); im.paste(obj,pos); footer(d,b); return im

def generate(photo_path,p,out_dir,b=''):
    photo=Image.open(photo_path).convert('RGB'); out_dir.mkdir(parents=True,exist_ok=True); items=[('01_OZON_MAIN.jpg',main_card(photo,p,b))]
    if p.get('applicability'):items.append(('02_OZON_APPLICABILITY.jpg',app_card(photo,p,b)))
    out=[]
    for name,img in items:
        path=out_dir/name; img.save(path,'JPEG',quality=92,optimize=True); out.append(path)
    return out

def find_box(root):
    for w in root.winfo_children():
        try:
            if isinstance(w,ttk.LabelFrame) and 'Маркетплейсы' in w.cget('text'):return w
        except Exception:pass
        f=find_box(w)
        if f:return f

def build(self):
    _ORIGINAL_BUILD(self); self.marketplace_brand_var=tk.StringVar(value='Авто'); box=find_box(self)
    if box:
        row=ttk.Frame(box); row.pack(fill='x',pady=(6,0)); ttk.Label(row,text='Бренд карточки:').pack(side='left'); ttk.Combobox(row,textvariable=self.marketplace_brand_var,values=('Авто','DriveTime','Cheviplus','Без бренда'),state='readonly',width=16).pack(side='left',padx=6); ttk.Label(row,text='Marketplace 1.0').pack(side='left',padx=12)
def create(self):
    b=brand(self.marketplace_brand_var.get() if hasattr(self,'marketplace_brand_var') else 'Авто',self.bg_choice_var.get() if hasattr(self,'bg_choice_var') else ''); old=cards.generate_cards; cards.generate_cards=lambda photo,p,out:generate(photo,p,out,b)
    try:return _ORIGINAL_CREATE(self)
    finally:cards.generate_cards=old
app.App._build=build; app.App._marketplace_create_ozon_cards=create; app.APP_VERSION=APP_VERSION; app.APP_BUILD=APP_BUILD; catalog.APP_VERSION=APP_VERSION; catalog.APP_BUILD=APP_BUILD
