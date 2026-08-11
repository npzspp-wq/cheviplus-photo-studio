"""Cheviplus Photo Studio 5.9: hidden workstation license and first-PC binding."""
from __future__ import annotations
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path
import hashlib, hmac, json, os, secrets, uuid
from tkinter import ttk, messagebox, simpledialog, filedialog

import app
import cheviplus_ai_quality as aq
from cheviplus_workstation_stats import WorkstationStatsApp, load_stats

APP_VERSION="5.9"
APP_BUILD="2026.08.11.09"
STATUS_ACTIVE="active"; STATUS_SUSPENDED="suspended"; STATUS_BLOCKED="blocked"; STATUS_UNLICENSED="unlicensed"
GRACE_DAYS=7; WARN_DAYS=14; CLOCK_ROLLBACK_TOLERANCE_HOURS=12
_PACKAGE_SECRET=b"Cheviplus-Photo-Studio-5.9-workstation-package"
LICENSE_PREFIX="CPS"


def _data_dir():
 base=os.environ.get("APPDATA") or str(Path.home()); p=Path(base)/"CheviplusPhotoStudio"; p.mkdir(parents=True,exist_ok=True); return p

def _license_path(): return _data_dir()/"license.json"
def _issued_path(): return _data_dir()/"issued_workstations.json"
def _registry_path(): return _data_dir()/"license_registry.json"

def _machine_fingerprint():
 parts=[]
 try:
  import winreg
  k=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SOFTWARE\Microsoft\Cryptography")
  parts.append(str(winreg.QueryValueEx(k,"MachineGuid")[0]))
 except Exception: pass
 parts += [str(uuid.getnode()), os.environ.get("COMPUTERNAME","")]
 raw="|".join(parts).encode("utf-8",errors="ignore")
 return hashlib.sha256(raw).hexdigest().upper()

def _add_months(dt, months):
 m=dt.month-1+months; year=dt.year+m//12; month=m%12+1; day=min(dt.day,monthrange(year,month)[1])
 return dt.replace(year=year,month=month,day=day)

def _parse_dt(v):
 try:return datetime.fromisoformat(v) if v else None
 except Exception:return None

def _sign_payload(payload):
 raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
 return hmac.new(_PACKAGE_SECRET,raw,hashlib.sha256).hexdigest()

def _verify_package(data):
 sig=data.get("signature",""); payload={k:v for k,v in data.items() if k!="signature"}
 return hmac.compare_digest(sig,_sign_payload(payload))

def _load_registry():
 try:
  data=json.loads(_registry_path().read_text(encoding="utf-8"))
  if not isinstance(data,dict):raise ValueError
 except Exception:
  data={"version":1,"next_sequence":1,"licenses":[]}
 # Migrate already issued packages from 5.9 pre-numbering so sequence never goes backwards.
 try:
  issued=json.loads(_issued_path().read_text(encoding="utf-8"))
  if isinstance(issued,list) and not data.get("licenses"):
   for item in issued:
    if not isinstance(item,dict):continue
    seq=int(data.get("next_sequence",1)); number=f"{LICENSE_PREFIX}-{seq:06d}"
    data.setdefault("licenses",[]).append({"license_number":number,"name":item.get("name",""),"token":item.get("token",""),"issued_at":item.get("issued_at","")})
    data["next_sequence"]=seq+1
 except Exception:pass
 data.setdefault("version",1); data.setdefault("next_sequence",1); data.setdefault("licenses",[])
 return data

def _save_registry(data):
 tmp=_registry_path().with_suffix(".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(_registry_path())

def _allocate_license_number(name, token, issued_at):
 data=_load_registry(); seq=max(1,int(data.get("next_sequence",1)))
 existing={str(x.get("license_number","")) for x in data.get("licenses",[]) if isinstance(x,dict)}
 while f"{LICENSE_PREFIX}-{seq:06d}" in existing:seq+=1
 number=f"{LICENSE_PREFIX}-{seq:06d}"
 data["next_sequence"]=seq+1
 data.setdefault("licenses",[]).append({"license_number":number,"name":name,"token":token,"issued_at":issued_at,"status":"issued"})
 _save_registry(data)
 return number

def create_workstation_package(name, destination):
 now=datetime.now(); token=secrets.token_urlsafe(18); issued_at=now.isoformat(timespec="seconds")
 license_number=_allocate_license_number(name.strip(),token,issued_at)
 payload={"version":2,"license_number":license_number,"workstation_name":name.strip(),"token":token,"months":6,"issued_at":issued_at}
 payload["signature"]=_sign_payload(payload)
 Path(destination).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 try:
  issued=json.loads(_issued_path().read_text(encoding="utf-8"))
 except Exception: issued=[]
 issued.append({"license_number":license_number,"name":payload["workstation_name"],"token":payload["token"],"issued_at":payload["issued_at"]})
 _issued_path().write_text(json.dumps(issued[-500:],ensure_ascii=False,indent=2),encoding="utf-8")
 return payload

def _candidate_packages():
 dirs=[Path.cwd(),Path.home()/"Downloads",Path.home()/"Desktop",Path(os.environ.get("USERPROFILE",str(Path.home())))/"Downloads"]
 seen=set()
 for d in dirs:
  try:
   for p in d.glob("*.cpslicense"):
    if str(p) not in seen: seen.add(str(p)); yield p
  except Exception: pass

def _bind_from_package(path):
 data=json.loads(Path(path).read_text(encoding="utf-8"))
 if not _verify_package(data): raise ValueError("Некорректный файл активации")
 now=datetime.now(); lic={"version":3,"license_number":data.get("license_number") or "LEGACY","workstation_name":data["workstation_name"],"workstation_id":load_stats()["workstation_id"],"machine_fingerprint":_machine_fingerprint(),"activation_token":data["token"],"status":STATUS_ACTIVE,"activated_at":now.isoformat(timespec="seconds"),"valid_until":_add_months(now,int(data.get("months",6))).isoformat(timespec="seconds"),"last_seen_at":now.isoformat(timespec="seconds")}
 _license_path().write_text(json.dumps(lic,ensure_ascii=False,indent=2),encoding="utf-8")
 try: Path(path).unlink()
 except Exception: pass
 return lic

def _auto_bind_if_possible():
 if _license_path().exists(): return
 valid=[]
 for p in _candidate_packages():
  try:
   data=json.loads(p.read_text(encoding="utf-8"))
   if _verify_package(data): valid.append(p)
  except Exception: pass
 if len(valid)==1:
  try:_bind_from_package(valid[0])
  except Exception:pass

def load_license():
 _auto_bind_if_possible()
 try:return json.loads(_license_path().read_text(encoding="utf-8"))
 except Exception:return {"version":3,"license_number":"","workstation_name":"","workstation_id":load_stats()["workstation_id"],"machine_fingerprint":None,"status":STATUS_UNLICENSED,"valid_until":None,"last_seen_at":None}

def save_license(data):
 tmp=_license_path().with_suffix(".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(_license_path())

def license_state(now=None):
 now=now or datetime.now(); data=load_license(); bound=data.get("machine_fingerprint")
 if bound and not hmac.compare_digest(bound,_machine_fingerprint()): return data,"wrong_pc",False
 last=_parse_dt(data.get("last_seen_at")); rollback=bool(last and now<last-timedelta(hours=CLOCK_ROLLBACK_TOLERANCE_HOURS))
 if not rollback: data["last_seen_at"]=max(now,last or now).isoformat(timespec="seconds"); save_license(data)
 status=data.get("status",STATUS_UNLICENSED); until=_parse_dt(data.get("valid_until"))
 if rollback:return data,"clock_rollback",False
 if status==STATUS_BLOCKED:return data,"blocked",False
 if status==STATUS_SUSPENDED:return data,"suspended",False
 if status!=STATUS_ACTIVE or until is None:return data,"unlicensed",False
 if now<=until:return data,("expiring" if (until.date()-now.date()).days<=WARN_DAYS else "active"),True
 if now<=until+timedelta(days=GRACE_DAYS):return data,"grace",True
 return data,"expired",False

class LicenseApp(WorkstationStatsApp):
 def _build(self):
  super()._build(); self._apply_branding(); frame=aq._find_label_frame(self,"3. Стабильная ручная обработка") or self
  self.admin_license_box=ttk.LabelFrame(frame,text="Администрирование рабочего места",padding=6); self.admin_license_box.grid(row=11,column=0,columnspan=6,sticky="ew",pady=(7,3)); self.admin_license_box.grid_remove()
  self.workstation_label=ttk.Label(self.admin_license_box,text=""); self.workstation_label.pack(side="left",fill="x",expand=True)
  ttk.Button(self.admin_license_box,text="Подготовить рабочее место",command=self._prepare_workstation).pack(side="right",padx=4)
  ttk.Button(self.admin_license_box,text="Приостановить",command=lambda:self._set_status(STATUS_SUSPENDED)).pack(side="right",padx=4)
  ttk.Button(self.admin_license_box,text="Возобновить",command=lambda:self._set_status(STATUS_ACTIVE)).pack(side="right",padx=4)
  self._refresh_license(); self.after_idle(self._sync_license_admin_state)
 def _apply_branding(self):
  try:
   icon=app.resource_path("assets/app_icon.ico")
   if icon.exists(): self.iconbitmap(default=str(icon))
  except Exception:pass
 def _apply_admin_lock(self):
  super()._apply_admin_lock(); self._sync_license_admin_state()
 def _sync_license_admin_state(self):
  try:
   if self._admin_unlocked:self.admin_license_box.grid()
   else:self.admin_license_box.grid_remove()
  except Exception:pass
 def _refresh_license(self):
  data,state,allowed=license_state(); self._license_allowed=allowed; self._license_state=state
  until=_parse_dt(data.get("valid_until")); d=until.strftime("%d.%m.%Y") if until else "—"
  name=data.get("workstation_name") or "не задано"; number=data.get("license_number") or "—"
  self.workstation_label.configure(text=f"Лицензия: {number}   Рабочее место: {name}   ID: {data.get('workstation_id','—')}   До: {d}   Статус: {state}")
 def _prepare_workstation(self):
  if not self._admin_unlocked:return
  name=simpledialog.askstring("Рабочее место","Введите название рабочего места:",parent=self)
  if not name or not name.strip():return
  safe="".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ","_")
  dest=filedialog.asksaveasfilename(parent=self,title="Сохранить файл для филиала",defaultextension=".cpslicense",initialfile=f"Cheviplus_{safe}.cpslicense",filetypes=[("Cheviplus license","*.cpslicense")])
  if not dest:return
  payload=create_workstation_package(name,dest)
  messagebox.showinfo("Готово",f"Рабочее место подготовлено.\n\nНомер лицензии: {payload['license_number']}\nНазвание: {payload['workstation_name']}\nСрок после активации: 6 календарных месяцев.\n\nОтправьте файл в филиал вместе с Setup. При первом запуске программа привяжется к первому компьютеру.",parent=self)
 def _set_status(self,status):
  if not self._admin_unlocked:return
  data=load_license()
  if not data.get("machine_fingerprint"):return
  data["status"]=status; save_license(data); self._refresh_license()
 def start_preview(self):
  self._refresh_license()
  if not self._license_allowed:
   messagebox.showwarning("Cheviplus Photo Studio","Рабочее место не активировано или программа запущена не на зарегистрированном компьютере. Обратитесь к администратору.",parent=self); return
  super().start_preview()
 def start(self):
  self._refresh_license()
  if not self._license_allowed:
   messagebox.showwarning("Cheviplus Photo Studio","Рабочее место не активировано или программа запущена не на зарегистрированном компьютере. Обратитесь к администратору.",parent=self); return
  super().start()

app.APP_VERSION=APP_VERSION; app.APP_BUILD=APP_BUILD; aq.APP_VERSION=APP_VERSION; aq.APP_BUILD=APP_BUILD
