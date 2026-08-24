"""Ozon marketplace cards with real product photo and useful catalog data."""
from __future__ import annotations
import re
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont
import app
import cheviplus_marketplace_catalog as catalog
APP_VERSION="5.21"; APP_BUILD="2026.08.24.09"; CARD_SIZE=(1200,1600); _ORIGINAL_BUILD=app.App._build

def _font(size,bold=False):
    for p in [r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"]:
        try:return ImageFont.truetype(p,size=size)
        except Exception:pass
    return ImageFont.load_default()
def _wrap(d,t,f,w,max_lines=4):
    words=re.split(r"\s+",(t or "").strip()); lines=[]; cur=""
    for word in words:
        test=(cur+" "+word).strip()
        if d.textbbox((0,0),test,font=f)[2]<=w:cur=test
        else:
            if cur:lines.append(cur)
            cur=word
            if len(lines)>=max_lines-1:break
    if cur and len(lines)<max_lines:lines.append(cur)
    return lines
def _name(p):return (p.get("name") or "ТОВАР").strip()
def _article(p):return (p.get("article") or p.get("code") or "").strip()
def _apps(p):return [str(x).strip() for x in (p.get("applicability") or []) if str(x).strip()]
def _base():return Image.new("RGB",CARD_SIZE,(247,248,250))
def _title(d,text,y=80):
    f=_font(57,True)
    for line in _wrap(d,text.upper(),f,1060,4):d.text((70,y),line,font=f,fill=(26,29,34));y+=66
    return y
def _fit(photo,box):
    x0,y0,x1,y1=box; im=photo.convert("RGB"); bw,bh=x1-x0,y1-y0; r=min(bw/max(1,im.width),bh/max(1,im.height)); im=im.resize((max(1,int(im.width*r)),max(1,int(im.height*r))),Image.Resampling.LANCZOS);return im,(x0+(bw-im.width)//2,y0+(bh-im.height)//2)
def build_card_main(photo,p):
    img=_base();d=ImageDraw.Draw(img);y=_title(d,_name(p));a=_article(p)
    if a:d.rounded_rectangle((70,y+20,545,y+95),radius=20,fill=(229,35,42));d.text((98,y+38),f"АРТИКУЛ {a}",font=_font(31,True),fill="white");top=y+135
    else:top=y+55
    im,pos=_fit(photo,(90,top,1110,1500));img.paste(im,pos);return img
def build_card_applicability(photo,p):
    img=_base();d=ImageDraw.Draw(img);d.text((70,80),"ПРИМЕНЯЕМОСТЬ",font=_font(68,True),fill=(26,29,34));apps=_apps(p);y=210
    if len(apps)==1:
        d.rounded_rectangle((70,y,1130,y+185),radius=28,fill="white",outline=(214,217,222),width=2);ty=y+42
        for line in _wrap(d,apps[0],_font(47,True),950,3):d.text((115,ty),line,font=_font(47,True),fill=(35,39,45));ty+=58
        top=y+220
    else:
        for i,line in enumerate(apps[:5],1):
            d.rounded_rectangle((70,y,1130,y+108),radius=22,fill="white",outline=(214,217,222),width=2);d.ellipse((98,y+30,146,y+78),fill=(229,35,42));d.text((112,y+34),str(i),font=_font(23,True),fill="white");ty=y+20
            for w in _wrap(d,line,_font(33,True),900,2):d.text((178,ty),w,font=_font(33,True),fill=(40,44,50));ty+=40
            y+=125
        top=min(y+20,990)
    im,pos=_fit(photo,(90,top,1110,1500));img.paste(im,pos);return img
def generate_cards(photo_path,p,out_dir):
    photo=Image.open(photo_path).convert("RGB");out_dir.mkdir(parents=True,exist_ok=True);cards=[("01_OZON_MAIN.jpg",build_card_main(photo,p))]
    if _apps(p):cards.append(("02_OZON_APPLICABILITY.jpg",build_card_applicability(photo,p)))
    result=[]
    for n,im in cards:path=out_dir/n;im.save(path,"JPEG",quality=92,optimize=True,progressive=True);result.append(path)
    return result
def _find(root):
    for w in root.winfo_children():
        try:
            if isinstance(w,ttk.LabelFrame) and "Маркетплейсы" in w.cget("text"):return w
        except Exception:pass
        f=_find(w)
        if f is not None:return f
def build_cards_ui(self):
    _ORIGINAL_BUILD(self);box=_find(self)
    if box is None:return
    row=ttk.Frame(box);row.pack(fill="x",pady=(10,0));ttk.Button(row,text="СОЗДАТЬ КАРТОЧКИ OZON",command=self._marketplace_create_ozon_cards).pack(side="left");ttk.Label(row,text="2 карточки 1200×1600 • без фиксированного бренда").pack(side="left",padx=10)
def create_ozon_cards(self):
    p=getattr(self,"marketplace_selected_product",None)
    if not p:messagebox.showwarning("Ozon","Сначала найдите товар по артикулу или коду.");return
    photo=filedialog.askopenfilename(title="Выберите реальное фото товара",filetypes=[("Изображения","*.jpg *.jpeg *.png *.webp")])
    if not photo:return
    parent=filedialog.askdirectory(title="Куда сохранить карточки Ozon?")
    if not parent:return
    out=Path(parent)/f"OZON_{catalog.normalize_key(_article(p) or 'OZON') or 'OZON'}"
    try:files=generate_cards(Path(photo),p,out)
    except Exception as e:messagebox.showerror("Ozon",f"Не удалось создать карточки:\n{e}");return
    self.status.set(f"Создано карточек Ozon: {len(files)}");messagebox.showinfo("Ozon",f"Готово. Создано карточек: {len(files)}.\nПапка:\n{out}")
app.App._build=build_cards_ui;app.App._marketplace_create_ozon_cards=create_ozon_cards;app.APP_VERSION=APP_VERSION;app.APP_BUILD=APP_BUILD;catalog.APP_VERSION=APP_VERSION;catalog.APP_BUILD=APP_BUILD
