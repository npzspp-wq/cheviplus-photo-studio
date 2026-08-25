import tkinter as tk
from tkinter import messagebox
import app
import cheviplus_marketplace_visual_v1 as visual
import cheviplus_marketplace_five_cards as five
import cheviplus_ozon_compliance as ozon

APP_VERSION='5.29'
APP_BUILD='2026.08.25.03'
MAX_ITEMS=3
WARN_CHARS=130
RECOMMENDED_CHARS=90


def _measure(draw,text,font):
    box=draw.textbbox((0,0),str(text),font=font)
    return box[2]-box[0]


def _wrap_words(draw,text,font,max_width,max_lines):
    words=str(text or '').strip().split()
    if not words:return []
    lines=[]; current=''
    for word in words:
        trial=(current+' '+word).strip()
        if not current or _measure(draw,trial,font)<=max_width:
            current=trial
        else:
            lines.append(current); current=word
            if len(lines)>=max_lines-1:break
    if current and len(lines)<max_lines:lines.append(current)
    return lines


def _fit_text(draw,text,max_width,max_lines=3):
    for size in (36,34,32,30,28,26):
        f=visual.font(size,1)
        wrapped=_wrap_words(draw,text,f,max_width,max_lines)
        if wrapped and len(wrapped)<=max_lines and all(_measure(draw,x,f)<=max_width for x in wrapped):
            return f,wrapped,size
    f=visual.font(26,1)
    return f,_wrap_words(draw,text,f,max_width,max_lines),26


def info_card(photo,p,title,page,items,brand):
    im,d=visual.base(title,page,p.get('marketplace_category'))
    usable=[str(x).strip() for x in items if str(x).strip()][:MAX_ITEMS]
    y=245
    for i,item in enumerate(usable,1):
        f,rows,size=_fit_text(d,item,900,3)
        row_height=max(118,38+len(rows)*(size+9))
        d.rounded_rectangle((64,y,1136,y+row_height),22,fill='white',outline=visual.LINE,width=2)
        center=y+row_height//2
        d.ellipse((90,center-24,138,center+24),fill=visual.RED)
        d.text((106,center-16),str(i),font=visual.font(21,1),fill='white')
        ty=y+24
        for row in rows:
            d.text((166,ty),row,font=f,fill=visual.TEXT)
            ty+=size+9
        y+=row_height+18
    top=max(y+26,720)
    if top>1050:top=1050
    d.rounded_rectangle((190,top,1010,1480),30,fill='white',outline=visual.LINE,width=2)
    obj,pos=visual.fit(photo,(225,top+35,975,1440)); im.paste(obj,pos)
    visual.footer(d,brand)
    return im


def _validate_extra(self):
    p=getattr(self,'marketplace_selected_product',None)
    if not p:return True
    extra=five.get_extra(p)
    warnings=[]
    labels={'characteristics':'Характеристики','advantages':'Преимущества','package':'Комплектация / важно'}
    for field,label in labels.items():
        vals=[str(x).strip() for x in extra.get(field,[]) if str(x).strip()]
        if len(vals)>MAX_ITEMS:
            warnings.append(f'{label}: будет использовано только первых {MAX_ITEMS} пункта')
        for idx,text in enumerate(vals[:MAX_ITEMS],1):
            if len(text)>WARN_CHARS:
                warnings.append(f'{label}, пункт {idx}: {len(text)} символов — рекомендуется сократить до {RECOMMENDED_CHARS}–{WARN_CHARS}')
    if warnings:
        return messagebox.askyesno('Длина текста','\n'.join(warnings)+'\n\nПродолжить создание карточек?')
    return True


_ORIGINAL_CREATE=app.App._marketplace_create_ozon_cards

def create_checked(self):
    if not _validate_extra(self):return
    return _ORIGINAL_CREATE(self)


five.info_card=info_card
app.App._marketplace_create_ozon_cards=create_checked
app.APP_VERSION=APP_VERSION
app.APP_BUILD=APP_BUILD
five.APP_VERSION=APP_VERSION
five.APP_BUILD=APP_BUILD
ozon.APP_VERSION=APP_VERSION
ozon.APP_BUILD=APP_BUILD
