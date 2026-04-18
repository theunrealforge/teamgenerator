import customtkinter as ctk
import json
import os
import requests
import time
from PIL import ImageGrab
import io
import itertools
from tkinter import filedialog, messagebox
import traceback
import random
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urljoin, urlparse

# Set appearances
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# APP CONSTANTS
APP_NAME = "TeamGenerator"
APP_VERSION = "1.1.0"
REQUEST_TIMEOUT = 15
AUTO_UPDATE_DELAY_MS = 1500
GITHUB_USER = "theunrealforge"
GITHUB_REPO = "teamgenerator"
DEFAULT_MANIFEST_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version_manifest.json"

# HIDDEN STORAGE LOGIC (Stores everything in AppData so the EXE folder stays clean)
def get_data_dir():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        appdata = os.path.expanduser('~')
    path = os.path.join(appdata, APP_NAME)
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, "databases"), exist_ok=True)
    os.makedirs(os.path.join(path, "saves"), exist_ok=True)
    return path

DATA_DIR = get_data_dir()
DB_DIR = os.path.join(DATA_DIR, "databases")
SAVES_DIR = os.path.join(DATA_DIR, "saves")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# INTERNAL ASSETS (Inside EXE)
def get_asset_path(filename):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

ICON_PATH = get_asset_path("icon.ico")
ICON_PNG_PATH = get_asset_path("icon.png")

DEFAULT_CONFIG = {
    "webhook_url": "",
    "update_manifest_url": DEFAULT_MANIFEST_URL,
    "auto_check_updates": True,
    "active_db": "default"
}

def read_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def normalize_player_db(data):
    if not isinstance(data, dict): return {}
    return {str(k).strip(): str(v).strip() or "5" for k, v in data.items() if str(k).strip()}

def version_key(v):
    return tuple(int(p) for p in str(v).split('.') if p.isdigit())

def is_newer_version(latest, current):
    try: return version_key(latest) > version_key(current)
    except: return False

PLACEHOLDER = "Type player name or select..."

class CustomWarning(ctk.CTkToplevel):
    def __init__(self, master, title, message):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        f = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color="#e74c3c", corner_radius=20); f.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(f, text=message, font=ctk.CTkFont(size=14, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=20)
        ctk.CTkButton(f, text="OK", width=100, height=35, corner_radius=10, fg_color="#e74c3c", command=self.destroy).pack(pady=(0, 20))

class CustomInfo(ctk.CTkToplevel):
    def __init__(self, master, message, color="#3498db"):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        f = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color=color, corner_radius=20); f.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(f, text=message, font=ctk.CTkFont(size=14, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=20)
        ctk.CTkButton(f, text="OK", width=100, height=35, corner_radius=10, fg_color=color, command=self.destroy).pack(pady=(0, 20))

class PlayerDropdown(ctk.CTkToplevel):
    def __init__(self, master, idx, players, sel, callback):
        super().__init__(master)
        self.master_app, self.idx, self.callback = master, idx, callback
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        mf = ctk.CTkFrame(self, fg_color="#121212", border_width=1, border_color="#333333", corner_radius=15); mf.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(mf, fg_color="transparent", corner_radius=15); self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.all_players = sorted(players, key=str.casefold); self.sel_names = {n.casefold() for n in sel}
        e = self.master_app.player_entries[idx]
        self.geometry(f"{e.winfo_width()+45}x300+{e.winfo_rootx()}+{e.winfo_rooty()+e.winfo_height()+5}")
        self.refresh(""); self.bind("<FocusOut>", lambda e: self.after(200, self.destroy))
    def refresh(self, term):
        for w in self.scroll.winfo_children(): w.destroy()
        filt = [p for p in self.all_players if term.lower() in p.lower()]
        for p in filt:
            s = p.casefold() in self.sel_names
            ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(weight="bold" if s else "normal"), text_color="#2ecc71" if s else "white", anchor="w", fg_color="transparent", command=lambda n=p: (self.callback(n, self.idx), self.destroy())).pack(fill="x")

class TeamGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ULTIMATE TEAM GENERATOR"); self.geometry("1050x1100"); self.overrideredirect(True)
        self.attributes("-alpha", 0.99); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        if os.path.exists(ICON_PATH):
            try: 
                self.iconbitmap(ICON_PATH)
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"TUF.{APP_NAME}.v1")
            except: pass

        self.bg_frame = ctk.CTkFrame(self, fg_color="#080808", corner_radius=35, border_width=1, border_color="#1f1f1f"); self.bg_frame.pack(fill="both", expand=True)
        self.player_vars = [ctk.StringVar(value=PLACEHOLDER) for _ in range(10)]
        self.points_vars = [ctk.StringVar(value="5") for _ in range(10)]
        self.update_status_var = ctk.StringVar(value=f"Version {APP_VERSION}")
        self.webhook_url, self.active_db_name, self.auto_check_updates = "", "default", True
        self.player_db, self.player_entries, self.dropdown = {}, [], None,
        self.is_updating = False; self.load_config(); self.load_db(); self.setup_ui()
        for i in range(10): self.player_vars[i].trace_add("write", lambda *a, idx=i: self.on_type(idx))
        self.bg_frame.bind("<Button-1>", self.start_move); self.bg_frame.bind("<B1-Motion>", self.do_move)
        if self.auto_check_updates: self.after(AUTO_UPDATE_DELAY_MS, lambda: threading.Thread(target=self.check_updates, daemon=True).start())

    def start_move(self, e): self.x, self.y = e.x, e.y
    def do_move(self, e): self.geometry(f"+{self.winfo_x()+e.x-self.x}+{self.winfo_y()+e.y-self.y}")
    def load_config(self):
        c = read_json(CONFIG_PATH); self.webhook_url = c.get("webhook_url", "")
        self.auto_check_updates = c.get("auto_check_updates", True); self.active_db_name = c.get("active_db", "default")
    def save_config(self):
        write_json(CONFIG_PATH, {"webhook_url": self.webhook_url, "auto_check_updates": self.auto_check_updates, "active_db": self.active_db_name})
    def load_db(self):
        self.player_db = normalize_player_db(read_json(os.path.join(DB_DIR, f"{self.active_db_name}.json")))
    def save_db(self):
        write_json(os.path.join(DB_DIR, f"{self.active_db_name}.json"), self.player_db)

    def setup_ui(self):
        ts = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=60); ts.pack(fill="x", padx=30, pady=(20, 0))
        if os.path.exists(ICON_PNG_PATH):
            try:
                from PIL import Image
                self.logo_img = ctk.CTkImage(light_image=Image.open(ICON_PNG_PATH), size=(42, 42))
                ctk.CTkLabel(ts, image=self.logo_img, text="").pack(side="left", padx=(0, 2))
            except: pass
        ctk.CTkLabel(ts, text="TEAM GENERATOR", font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")
        ctk.CTkButton(ts, text="✕", width=40, height=40, corner_radius=10, fg_color="#1a1a1a", hover_color="#e74c3c", command=self.quit).pack(side="right")
        self.nav = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.nav.pack(pady=20)
        self.tabs = {}
        for c, l in [("gen", "Generator"), ("db", "Database"), ("set", "Settings")]:
            b = ctk.CTkButton(self.nav, text=l.upper(), width=160, height=45, corner_radius=12, fg_color="#1a1a1a", command=lambda x=c: self.show_tab(x))
            b.pack(side="left", padx=8); self.tabs[c] = b
        self.cont = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.cont.pack(fill="both", expand=True, padx=40, pady=(0, 30))
        self.frames = {}; self.ui_gen(); self.ui_db(); self.ui_set(); self.show_tab("gen")

    def show_tab(self, name):
        for n, f in self.frames.items():
            f.pack_forget()
            self.tabs[n].configure(fg_color="#1f538d" if n == name else "#1a1a1a")
        self.frames[name].pack(fill="both", expand=True, padx=20, pady=20)

    def ui_gen(self):
        f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.frames["gen"] = f
        r_row = ctk.CTkFrame(f, fg_color="transparent"); r_row.pack(fill="x", pady=(0, 15))
        self.roster_cb = ctk.CTkComboBox(r_row, values=self.get_rosters(), width=380); self.roster_cb.set("Select Roster..."); self.roster_cb.pack(side="left", padx=8)
        ctk.CTkButton(r_row, text="LOAD", width=90, command=self.load_roster).pack(side="left", padx=5)
        ctk.CTkButton(r_row, text="SAVE", width=90, command=self.save_roster).pack(side="left", padx=5)
        p_grid = ctk.CTkFrame(f, fg_color="transparent"); p_grid.pack(fill="both", expand=True)
        self.player_entries = []
        for i in range(10):
            r = ctk.CTkFrame(p_grid, fg_color="transparent"); r.pack(fill="x", pady=2)
            e = ctk.CTkEntry(r, textvariable=self.player_vars[i], height=35); e.pack(side="left", expand=True, fill="x")
            self.player_entries.append(e); e.bind("<Button-1>", lambda ev, idx=i: self.player_vars[idx].set("") if self.player_vars[idx].get()==PLACEHOLDER else None)
            ctk.CTkComboBox(r, values=[str(x) for x in range(1, 11)], variable=self.points_vars[i], width=70).pack(side="right", padx=5)
        ctk.CTkButton(f, text="GENERATE TEAMS", height=50, fg_color="#1f538d", font=ctk.CTkFont(weight="bold"), command=self.generate).pack(fill="x", pady=10)
        self.res = ctk.CTkFrame(f, fg_color="#050505", corner_radius=20, height=350); self.res.pack(fill="x"); self.res.pack_propagate(False)
        self.t1_l = ctk.CTkLabel(self.res, text="", font=ctk.CTkFont(size=24)); self.t1_l.place(relx=0.05, rely=0.1, relwidth=0.4)
        self.t2_l = ctk.CTkLabel(self.res, text="", font=ctk.CTkFont(size=24)); self.t2_l.place(relx=0.55, rely=0.1, relwidth=0.4)

    def ui_db(self):
        f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.frames["db"] = f
        ctrl = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15); ctrl.pack(fill="x", pady=10)
        self.db_sel = ctk.CTkComboBox(ctrl, values=self.get_dbs(), command=self.switch_db); self.db_sel.set(self.active_db_name); self.db_sel.pack(side="left", padx=20, pady=20)
        ctk.CTkButton(ctrl, text="NEW", width=60, command=self.new_db).pack(side="left", padx=5)
        add = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15); add.pack(fill="x", pady=10)
        self.name_in = ctk.CTkEntry(add, placeholder_text="Name"); self.name_in.pack(side="left", padx=15, pady=15, expand=True, fill="x")
        self.pts_in = ctk.CTkComboBox(add, values=[str(x) for x in range(1, 11)], width=80); self.pts_in.set("5"); self.pts_in.pack(side="left", padx=5)
        ctk.CTkButton(add, text="ADD", width=80, command=self.add_p).pack(side="right", padx=15)
        self.db_sc = ctk.CTkScrollableFrame(f, fg_color="transparent"); self.db_sc.pack(fill="both", expand=True)

    def ui_set(self):
        f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.frames["set"] = f
        ctk.CTkLabel(f, text="WEBHOOK URL", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=10)
        self.h_in = ctk.CTkEntry(f); self.h_in.pack(fill="x", pady=5); self.h_in.insert(0, self.webhook_url); self.h_in.bind("<KeyRelease>", lambda e: self.set_cfg())
        self.up_v = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(f, text="Auto Updates", variable=self.up_v, command=self.set_cfg).pack(anchor="w", pady=20)
        ctk.CTkLabel(f, textvariable=self.update_status_var, text_color="#f1c40f").pack(anchor="w")

    def set_cfg(self): self.webhook_url = self.h_in.get(); self.auto_check_updates = self.up_v.get()=="on"; self.save_config()
    def get_dbs(self): return [f.replace(".json","") for f in os.listdir(DB_DIR) if f.endswith(".json")] or ["default"]
    def switch_db(self, n): self.active_db_name = n; self.save_config(); self.load_db(); self.refresh_db()
    def new_db(self):
        if n := ctk.CTkInputDialog(text="Name:", title="New").get_input():
            self.active_db_name = n.strip(); self.player_db = {}; self.save_db(); self.save_config()
            self.db_sel.configure(values=self.get_dbs()); self.db_sel.set(n); self.refresh_db()
    def add_p(self):
        n = self.name_in.get().strip()
        if n: self.player_db[n] = self.pts_in.get(); self.save_db(); self.refresh_db(); self.name_in.delete(0,'end')
    def refresh_db(self):
        for w in self.db_sc.winfo_children(): w.destroy()
        for n, p in sorted(self.player_db.items()):
            r = ctk.CTkFrame(self.db_sc, fg_color="#121212", pady=5); r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=n, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=15)
            ctk.CTkButton(r, text="X", width=30, fg_color="#c0392b", command=lambda x=n: (self.player_db.pop(x), self.save_db(), self.refresh_db())).pack(side="right", padx=10)
    def on_type(self, i):
        v = self.player_vars[i].get()
        if v in self.player_db: self.points_vars[i].set(self.player_db[v]); self.player_entries[i].configure(text_color="#2ecc71")
        else: self.player_entries[i].configure(text_color="white")
    def generate(self):
        ps = [{"n": v.get(), "p": int(self.points_vars[i].get())} for i, v in enumerate(self.player_vars) if v.get() and v.get()!=PLACEHOLDER]
        if len(ps)<2: return
        best_diff, best_split = 999, ([], [])
        for _ in range(100):
            random.shuffle(ps); mid = len(ps)//2; t1, t2 = ps[:mid], ps[mid:]
            d = abs(sum(x["p"] for x in t1) - sum(x["p"] for x in t2))
            if d < best_diff: best_diff, best_split = d, (t1, t2)
        self.t1_l.configure(text="\n".join(x["n"] for x in best_split[0]))
        self.t2_l.configure(text="\n".join(x["n"] for x in best_split[1]))
    def get_rosters(self): return [f.replace(".json","") for f in os.listdir(SAVES_DIR) if f.endswith(".json")]
    def save_roster(self):
        if n := filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json"):
            d = {"ps": [{"n": v.get(), "p": self.points_vars[i].get()} for i, v in enumerate(self.player_vars)]}
            write_json(n, d); self.roster_cb.configure(values=self.get_rosters())
    def load_roster(self):
        rn = self.roster_cb.get()
        if rn and rn != "Select Roster...":
            d = read_json(os.path.join(SAVES_DIR, f"{rn}.json"))
            for i, p in enumerate(d.get("ps", [])):
                if i < 10: self.player_vars[i].set(p["n"]); self.points_vars[i].set(p["p"])
    def check_updates(self):
        try:
            m = requests.get(DEFAULT_MANIFEST_URL, timeout=5).json()
            if is_newer_version(m["version"], APP_VERSION): self.update_status_var.set(f"Update {m['version']} Available")
        except: pass

if __name__ == "__main__":
    try: TeamGeneratorApp().mainloop()
    except:
        with open(os.path.join(DATA_DIR, "crash.txt"), "w") as f: f.write(traceback.format_exc())
