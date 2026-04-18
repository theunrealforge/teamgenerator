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

# Windows Taskbar Icon Fix
if sys.platform == "win32":
    try:
        import ctypes
        myappid = "theunrealforge.teamgenerator.final.v1.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass

# Set appearances
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# APP CONSTANTS
APP_NAME = "TeamGenerator"
APP_VERSION = "1.0.0"
REQUEST_TIMEOUT = 15
AUTO_UPDATE_DELAY_MS = 1500
GITHUB_USER = "theunrealforge"
GITHUB_REPO = "teamgenerator"
DEFAULT_MANIFEST_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version_manifest.json"

# HIDDEN STORAGE LOGIC
def get_data_dir():
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    path = os.path.join(appdata, APP_NAME)
    os.makedirs(os.path.join(path, "databases"), exist_ok=True)
    os.makedirs(os.path.join(path, "saves"), exist_ok=True)
    return path

DATA_DIR = get_data_dir()
DB_DIR = os.path.join(DATA_DIR, "databases")
SAVES_DIR = os.path.join(DATA_DIR, "saves")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

def get_asset_path(filename):
    if getattr(sys, 'frozen', False): return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

ICON_PATH, ICON_PNG_PATH = get_asset_path("icon.ico"), get_asset_path("icon.png")

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

def coerce_bool(value, default=True):
    if isinstance(value, bool): return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}: return True
    if lowered in {"0", "false", "no", "off"}: return False
    return default

def version_key(v): return tuple(int(p) for p in str(v).split('.') if p.isdigit())
def is_newer_version(latest, current):
    try: return version_key(latest) > version_key(current)
    except: return False

PLACEHOLDER = "Type player name or select..."

class CustomWarning(ctk.CTkToplevel):
    def __init__(self, master, title, message, button_text="OK"):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        f = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color="#e74c3c", corner_radius=20); f.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(f, text=message, font=ctk.CTkFont(size=14, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=(20, 10))
        ctk.CTkButton(f, text=button_text, width=100, height=35, corner_radius=10, fg_color="#e74c3c", hover_color="#c0392b", command=self.destroy).pack(pady=(0, 20))

class CustomInfo(ctk.CTkToplevel):
    def __init__(self, master, message, color="#3498db"):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        f = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color=color, corner_radius=20); f.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(f, text=message, font=ctk.CTkFont(size=14, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=(20, 10))
        ctk.CTkButton(f, text="OK", width=100, height=35, corner_radius=10, fg_color=color, hover_color="#2980b9", command=self.destroy).pack(pady=(0, 20))

class PlayerDropdown(ctk.CTkToplevel):
    def __init__(self, master, slot_idx, players, selected_names, callback, take_focus=False):
        super().__init__(master)
        self.master_app, self.slot_idx, self.callback = master, slot_idx, callback
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        mf = ctk.CTkFrame(self, fg_color="#121212", border_width=1, border_color="#333333", corner_radius=15); mf.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(mf, fg_color="transparent", corner_radius=15); self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.all_players = sorted(players, key=str.casefold); self.selected_names = {n.casefold() for n in selected_names if isinstance(n, str) and n.strip()}
        entry = self.master_app.player_entries[slot_idx]
        self.geometry(f"{entry.winfo_width()+45}x300+{entry.winfo_rootx()}+{entry.winfo_rooty()+entry.winfo_height()+5}")
        self.refresh(""); self.bind("<FocusOut>", lambda e: self.after(200, self.check_destroy))
    def check_destroy(self):
        try:
            f = self.focus_get()
            if not f or (f != self and not str(f).startswith(str(self))):
                if f != self.master_app.player_entries[self.slot_idx]: self.destroy()
        except: self.destroy()
    def refresh(self, term):
        for w in self.scroll.winfo_children(): w.destroy()
        filt = [p for p in self.all_players if term.lower().strip() in p.lower()]
        if not filt: ctk.CTkLabel(self.scroll, text="No players found", text_color="gray").pack(pady=10)
        else:
            for p in sorted(filt):
                sel = p.casefold() in self.selected_names
                ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(size=13, weight="bold" if sel else "normal"), text_color="#2ecc71" if sel else "white", anchor="w", fg_color="transparent", hover_color="#252525", height=30, command=lambda n=p: (self.callback(n, self.slot_idx), self.destroy())).pack(fill="x", pady=1)

class TeamGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ULTIMATE TEAM GENERATOR"); self.geometry("1050x1100"); self.overrideredirect(True)
        self.attributes("-alpha", 0.99); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
                def force_icon():
                    try:
                        hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                        hicon = ctypes.windll.user32.LoadImageW(None, ICON_PATH, 1, 256, 256, 0x00000010)
                        if hicon:
                            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, hicon)
                            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, hicon)
                    except: pass
                self.after(200, force_icon)
            except: pass

        self.bg_frame = ctk.CTkFrame(self, fg_color="#080808", corner_radius=35, border_width=1, border_color="#1f1f1f"); self.bg_frame.pack(fill="both", expand=True)
        self.player_vars = [ctk.StringVar(value=PLACEHOLDER) for _ in range(10)]
        self.points_vars = [ctk.StringVar(value="5") for _ in range(10)]
        self.update_status_var = ctk.StringVar(value=f"Version {APP_VERSION}")
        self.webhook_url, self.active_db_name, self.auto_check_updates = "", "default", True
        self.player_db, self.player_entries, self.dropdown_window = {}, [], None
        self.is_updating, self.is_checking_updates, self.is_installing_update = False, False, False
        self.load_config(); self.load_active_db(); self.setup_ui()
        for i in range(10): self.player_vars[i].trace_add("write", lambda *a, idx=i: self.on_type_search(idx))
        self.bg_frame.bind("<Button-1>", self.start_move); self.bg_frame.bind("<B1-Motion>", self.do_move)
        self.after(AUTO_UPDATE_DELAY_MS, self.schedule_auto_update_check)

    def start_move(self, e): self.x, self.y = e.x, e.y
    def do_move(self, e): self.geometry(f"+{self.winfo_x() + e.x - self.x}+{self.winfo_y() + e.y - self.y}")
    def load_config(self):
        c = DEFAULT_CONFIG.copy(); c.update(read_json(CONFIG_PATH))
        self.webhook_url, self.auto_check_updates, self.active_db_name = str(c["webhook_url"]), coerce_bool(c["auto_check_updates"]), str(c["active_db"])
        self.update_manifest_url = str(c.get("update_manifest_url", DEFAULT_MANIFEST_URL))
    def save_config(self): write_json(CONFIG_PATH, {"webhook_url": self.webhook_url, "update_manifest_url": self.update_manifest_url, "auto_check_updates": self.auto_check_updates, "active_db": self.active_db_name})
    def load_active_db(self, path=None):
        if path:
            try: self.player_db = normalize_player_db(read_json(path)); return True
            except: return False
        p = os.path.join(DB_DIR, f"{self.active_db_name}.json")
        if not os.path.exists(p) and self.active_db_name == "default": write_json(p, {})
        self.player_db = normalize_player_db(read_json(p))
    def save_active_db(self, path=None): write_json(path if path else os.path.join(DB_DIR, f"{self.active_db_name}.json"), self.player_db)

    def setup_ui(self):
        ts = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=60); ts.pack(fill="x", padx=30, pady=(20, 0))
        if os.path.exists(ICON_PNG_PATH):
            try:
                from PIL import Image
                self.logo_img = ctk.CTkImage(light_image=Image.open(ICON_PNG_PATH), size=(42, 42))
                ctk.CTkLabel(ts, image=self.logo_img, text="").pack(side="left", padx=(0, 2))
            except: pass
        ctk.CTkLabel(ts, text="TEAM GENERATOR", font=ctk.CTkFont(size=17, weight="bold"), text_color="#ffffff").pack(side="left")
        ctk.CTkButton(ts, text="✕", width=40, height=40, corner_radius=10, fg_color="#1a1a1a", text_color="gray", hover_color="#e74c3c", command=self.quit).pack(side="right")
        self.nav_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.nav_frame.pack(pady=20)
        self.tab_buttons = {}
        for code, label in [("generator", "Generator"), ("database", "Database"), ("settings", "Settings")]:
            btn = ctk.CTkButton(self.nav_frame, text=label.upper(), width=160, height=45, corner_radius=12, fg_color="#1a1a1a", text_color="#aaaaaa", font=ctk.CTkFont(size=12, weight="bold"), command=lambda c=code: self.show_frame(c))
            btn.pack(side="left", padx=8); self.tab_buttons[code] = btn
        self.content_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.content_frame.pack(fill="both", expand=True, padx=40, pady=(0, 30))
        self.frames = {}; self.create_generator_ui(); self.create_database_ui(); self.create_settings_ui(); self.show_frame("generator")

    def show_frame(self, name):
        if self.dropdown_window: self.dropdown_window.destroy()
        for n, f in self.frames.items():
            f.pack_forget()
            btn = self.tab_buttons.get(n)
            if btn: btn.configure(fg_color="#1f538d" if n == name else "#1a1a1a", text_color="white" if n == name else "#aaaaaa")
        self.frames[name].pack(fill="both", expand=True, padx=20, pady=20)
        if name == "database": self.refresh_db_list()

    def create_generator_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["generator"] = f
        r_row = ctk.CTkFrame(f, fg_color="transparent"); r_row.pack(fill="x", pady=(0, 15))
        ri = ctk.CTkFrame(r_row, fg_color="transparent"); ri.pack(expand=True)
        self.roster_combo = ctk.CTkComboBox(ri, values=self.get_saved_rosters(), width=380, height=38, fg_color="#151515", border_color="#2a2a2a", corner_radius=10); self.roster_combo.set("Select Roster..."); self.roster_combo.pack(side="left", padx=8)
        ctk.CTkButton(ri, text="LOAD", width=90, height=38, fg_color="#1f538d", corner_radius=10, command=self.load_roster_action).pack(side="left", padx=5)
        ctk.CTkButton(ri, text="SAVE ROSTER", width=130, height=38, fg_color="#2a2a2a", corner_radius=10, command=self.save_roster_action).pack(side="left", padx=5)
        n_row = ctk.CTkFrame(f, fg_color="transparent"); n_row.pack(fill="x", pady=5)
        self.t1_name_entry = ctk.CTkEntry(n_row, placeholder_text="Team 1 Name", height=40, fg_color="#121212", border_color="#252525", corner_radius=10); self.t1_name_entry.pack(side="left", expand=True, fill="x", padx=(0, 10))
        self.t2_name_entry = ctk.CTkEntry(n_row, placeholder_text="Team 2 Name", height=40, fg_color="#121212", border_color="#252525", corner_radius=10); self.t2_name_entry.pack(side="left", expand=True, fill="x", padx=(10, 0))
        p_grid = ctk.CTkFrame(f, fg_color="transparent"); p_grid.pack(fill="both", expand=True, pady=5)
        self.player_entries = []
        for i in range(10):
            r = ctk.CTkFrame(p_grid, fg_color="transparent"); r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=str(i+1), width=35, text_color="#555555", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=5)
            e = ctk.CTkEntry(r, textvariable=self.player_vars[i], height=35, fg_color="#111111", border_color="#222222", corner_radius=8); e.pack(side="left", expand=True, fill="x", padx=(10, 0)); self.player_entries.append(e)
            ctk.CTkButton(r, text="▼", width=35, height=35, corner_radius=8, fg_color="#1a1a1a", border_width=1, border_color="#222222", command=lambda idx=i: self.sync_dropdown(idx, "", True)).pack(side="left", padx=(5, 10))
            e.bind("<Button-1>", lambda ev, idx=i: self.handle_entry_click(ev, idx))
            ctk.CTkComboBox(r, values=[str(x) for x in range(1, 11)], variable=self.points_vars[i], width=90, height=35, fg_color="#111111", border_color="#222222", corner_radius=8, command=lambda v, idx=i: self.update_points(v, idx)).pack(side="right", padx=5)
        act_row = ctk.CTkFrame(f, fg_color="transparent"); act_row.pack(pady=10, fill="x")
        ai = ctk.CTkFrame(act_row, fg_color="transparent"); ai.pack(expand=True)
        ctk.CTkButton(ai, text="GENERATE TEAMS", font=ctk.CTkFont(size=16, weight="bold"), width=250, height=55, corner_radius=15, fg_color="#1f538d", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="REFRESH", width=120, height=55, corner_radius=15, fg_color="#2a2a2a", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="DELETE TEAMS", width=120, height=55, corner_radius=15, fg_color="#c0392b", command=self.delete_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="DISCORD", width=120, height=55, corner_radius=15, fg_color="#5865F2", command=self.send_to_discord).pack(side="left", padx=10)
        self.result_container = ctk.CTkFrame(f, fg_color="#050505", corner_radius=30, border_width=1, border_color="#1f1f1f", height=420); self.result_container.pack(fill="x", pady=(5, 0)); self.result_container.pack_propagate(False)
        self.t1_box = ctk.CTkFrame(self.result_container, fg_color="#0a0a0a", corner_radius=25); self.t1_box.place(relx=0.02, rely=0.05, relwidth=0.46, relheight=0.9)
        self.t2_box = ctk.CTkFrame(self.result_container, fg_color="#0a0a0a", corner_radius=25); self.t2_box.place(relx=0.52, rely=0.05, relwidth=0.46, relheight=0.9)
        self.t1_title = ctk.CTkLabel(self.t1_box, text="TEAM 1", font=ctk.CTkFont(size=18, weight="bold"), text_color="#3498db"); self.t1_title.pack(pady=(10, 2))
        self.t1_list = ctk.CTkLabel(self.t1_box, text="", font=ctk.CTkFont(size=28, weight="bold"), justify="center", text_color="#ecf0f1"); self.t1_list.pack(expand=True, fill="both", pady=5)
        self.t1_total_label = ctk.CTkLabel(self.t1_box, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3498db"); self.t1_total_label.pack(pady=(0, 10))
        self.t2_title = ctk.CTkLabel(self.t2_box, text="TEAM 2", font=ctk.CTkFont(size=18, weight="bold"), text_color="#e74c3c"); self.t2_title.pack(pady=(10, 2))
        self.t2_list = ctk.CTkLabel(self.t2_box, text="", font=ctk.CTkFont(size=28, weight="bold"), justify="center", text_color="#ecf0f1"); self.t2_list.pack(expand=True, fill="both", pady=5)
        self.t2_total_label = ctk.CTkLabel(self.t2_box, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color="#e74c3c"); self.t2_total_label.pack(pady=(0, 10))

    def on_type_search(self, idx):
        if self.is_updating: return
        val = self.player_vars[idx].get().strip(); match = None
        for k in self.player_db:
            if k.casefold() == val.casefold(): match = k; break
        if match: self.player_entries[idx].configure(text_color="#2ecc71"); self.points_vars[idx].set(self.player_db[match])
        else: self.player_entries[idx].configure(text_color="white")
        if val and val != PLACEHOLDER: self.sync_dropdown(idx, val, False)
    def handle_entry_click(self, ev, idx):
        if self.player_vars[idx].get() == PLACEHOLDER: self.player_vars[idx].set(""); self.player_entries[idx].configure(text_color="white")
        if not (self.player_entries[idx].winfo_width() * 0.45 < ev.x < self.player_entries[idx].winfo_width() * 0.55): self.sync_dropdown(idx, "", False)
    def sync_dropdown(self, idx, term, take_focus):
        sel = [v.get().strip() for i, v in enumerate(self.player_vars) if i != idx and v.get().strip() != PLACEHOLDER]
        if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx: self.dropdown_window.refresh(term)
        else:
            if self.dropdown_window: self.dropdown_window.destroy()
            self.dropdown_window = PlayerDropdown(self, idx, list(self.player_db.keys()), sel, self.on_player_chosen); self.dropdown_window.refresh(term)
    def on_player_chosen(self, n, idx):
        self.is_updating = True; self.player_vars[idx].set(n); self.player_entries[idx].configure(text_color="#2ecc71")
        if n in self.player_db: self.points_vars[idx].set(self.player_db[n])
        self.is_updating = False
    def update_points(self, val, idx):
        n = self.player_vars[idx].get().strip()
        for k in list(self.player_db.keys()):
            if k.casefold() == n.casefold(): self.player_db[k] = val; self.save_active_db(); break

    def create_database_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["database"] = f
        # 1. Profile Section (MATCHING database.png)
        p_frame = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f")
        p_frame.pack(fill="x", pady=(0, 10))
        p_inner = ctk.CTkFrame(p_frame, fg_color="transparent"); p_inner.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(p_inner, text="👤  PROFILE MANAGEMENT", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a29bfe").pack(anchor="w", pady=(0, 10))
        
        row1 = ctk.CTkFrame(p_inner, fg_color="transparent"); row1.pack(fill="x")
        c1 = ctk.CTkFrame(row1, fg_color="transparent"); c1.pack(side="left")
        ctk.CTkLabel(c1, text="Active Profile", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        self.db_selector = ctk.CTkComboBox(c1, values=self.get_db_list(), width=280, height=35, command=self.switch_db, fg_color="#0a0a0a"); self.db_selector.set(self.active_db_name); self.db_selector.pack()
        
        c2 = ctk.CTkFrame(row1, fg_color="transparent"); c2.pack(side="left", padx=20)
        ctk.CTkLabel(c2, text="New Profile Name", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        self.new_profile_entry = ctk.CTkEntry(c2, placeholder_text="Enter profile name...", width=250, height=35, fg_color="#0a0a0a"); self.new_profile_entry.pack()
        
        ctk.CTkButton(row1, text="＋ CREATE", width=100, height=35, fg_color="#1f538d", font=ctk.CTkFont(weight="bold"), command=self.new_db_action).pack(side="left", padx=(5, 0), pady=(18, 0))
        ctk.CTkButton(row1, text="🗑 DELETE", width=100, height=35, fg_color="#c0392b", font=ctk.CTkFont(weight="bold"), command=self.delete_db_action).pack(side="left", padx=10, pady=(18, 0))

        # 2. Player Entry Card
        a_frame = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f")
        a_frame.pack(fill="x", pady=5)
        a_inner = ctk.CTkFrame(a_frame, fg_color="transparent"); a_inner.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(a_inner, text="👤+  ADD PLAYER", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a29bfe").pack(anchor="w", pady=(0, 10))
        
        row2 = ctk.CTkFrame(a_inner, fg_color="transparent"); row2.pack(fill="x")
        c3 = ctk.CTkFrame(row2, fg_color="transparent"); c3.pack(side="left")
        ctk.CTkLabel(c3, text="Player Name", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        self.db_name_input = ctk.CTkEntry(c3, width=450, height=35, fg_color="#0a0a0a"); self.db_name_input.pack()
        
        c4 = ctk.CTkFrame(row2, fg_color="transparent"); c4.pack(side="left", padx=20)
        ctk.CTkLabel(c4, text="Points", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        self.db_pts_input = ctk.CTkComboBox(c4, values=[str(x) for x in range(1, 11)], width=120, height=35, fg_color="#0a0a0a"); self.db_pts_input.set("5"); self.db_pts_input.pack()
        
        ctk.CTkButton(row2, text="ADD TO LIST", width=180, height=45, fg_color="#1f538d", font=ctk.CTkFont(weight="bold"), command=self.db_add_player).pack(side="right", pady=(18, 0))

        # 3. Database Actions Unit
        d_frame = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f")
        d_frame.pack(fill="x", pady=5)
        d_inner = ctk.CTkFrame(d_frame, fg_color="transparent"); d_inner.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(d_inner, text="🗄️  DATABASE ACTIONS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a29bfe").pack(anchor="w", pady=(0, 15))
        
        grid = ctk.CTkFrame(d_inner, fg_color="transparent"); grid.pack(fill="x")
        
        # Sub-sections
        g1 = ctk.CTkFrame(grid, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#252525"); g1.pack(side="left", expand=True, fill="both", padx=5)
        ctk.CTkLabel(g1, text="IMPORT / EXPORT", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(pady=10)
        ctk.CTkButton(g1, text="📤 IMPORT FROM FILE", width=220, height=35, fg_color="#2a2a2a", command=self.load_external_db).pack(pady=5)
        ctk.CTkButton(g1, text="📥 EXPORT DATABASE", width=220, height=35, fg_color="#2a2a2a", command=self.save_db_as).pack(pady=(5, 15))

        g2 = ctk.CTkFrame(grid, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#252525"); g2.pack(side="left", expand=True, fill="both", padx=5)
        ctk.CTkLabel(g2, text="LIST MANAGEMENT", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(pady=10)
        ctk.CTkButton(g2, text="🧹 CLEAR CURRENT LIST", width=220, height=35, fg_color="#2a2a2a", command=self.new_database).pack(pady=(5, 15))

        g3 = ctk.CTkFrame(grid, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#252525"); g3.pack(side="left", expand=True, fill="both", padx=5)
        ctk.CTkLabel(g3, text="DANGER ZONE", font=ctk.CTkFont(size=11, weight="bold"), text_color="#e74c3c").pack(pady=10)
        ctk.CTkButton(g3, text="⚠️ WIPE ACTIVE PROFILE", width=220, height=35, fg_color="#4b1d1d", hover_color="#6b2525", command=self.delete_database).pack(pady=(5, 15))

        # 4. Scroll List
        self.db_scroll = ctk.CTkScrollableFrame(f, fg_color="#050505", corner_radius=20, border_width=1, border_color="#1f1f1f")
        self.db_scroll.pack(fill="both", expand=True, pady=10)
        self.empty_lbl = ctk.CTkLabel(self.db_scroll, text="👥\n\nNo players in the list.", font=ctk.CTkFont(size=16), text_color="#444444")

    def get_db_list(self): return [f.replace(".json","") for f in os.listdir(DB_DIR) if f.endswith(".json")] or ["default"]
    def switch_db(self, name): self.active_db_name = name; self.save_config(); self.load_active_db(); self.refresh_db_list()
    def new_db_action(self):
        n = self.new_profile_entry.get().strip()
        if n:
            self.active_db_name = n; self.player_db = {}; self.save_active_db(); self.save_config(); self.new_profile_entry.delete(0, 'end')
            self.db_selector.configure(values=self.get_db_list()); self.db_selector.set(n); self.refresh_db_list()
    def delete_db_action(self):
        if self.active_db_name == "default": return
        if messagebox.askyesno("Confirm", f"Delete profile '{self.active_db_name}'?"):
            try: os.remove(os.path.join(DB_DIR, f"{self.active_db_name}.json"))
            except: pass
            self.active_db_name = "default"; self.save_config(); self.load_active_db(); self.db_selector.configure(values=self.get_db_list()); self.db_selector.set("default"); self.refresh_db_list()

    def db_add_player(self):
        name, pts = self.db_name_input.get().strip(), self.db_pts_input.get()
        if name:
            for k in list(self.player_db.keys()):
                if k.casefold() == name.casefold(): del self.player_db[k]
            self.player_db[name] = pts; self.save_active_db(); self.refresh_db_list(); self.db_name_input.delete(0, 'end')

    def refresh_db_list(self):
        for widget in self.db_scroll.winfo_children(): widget.destroy()
        if not self.player_db:
            self.empty_lbl = ctk.CTkLabel(self.db_scroll, text="👥\n\nNo players in the list.", font=ctk.CTkFont(size=16), text_color="#444444")
            self.empty_lbl.pack(expand=True, pady=100); return
        for name, pts in sorted(self.player_db.items(), key=lambda x: x[0].casefold()):
            row = ctk.CTkFrame(self.db_scroll, fg_color="#121212", corner_radius=10); row.pack(fill="x", pady=4, padx=5)
            ctk.CTkLabel(row, text=name, width=250, anchor="w", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(row, text=f"Power: {pts}", text_color="#888888").pack(side="left")
            ctk.CTkButton(row, text="DELETE", width=80, height=30, fg_color="#c0392b", command=lambda n=name: (self.player_db.pop(n), self.save_active_db(), self.refresh_db_list())).pack(side="right", padx=15)

    def load_external_db(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if p:
            if self.load_active_db(p): self.save_active_db(); self.refresh_db_list(); CustomInfo(self, "Database Imported!", "#2ecc71")
    def save_db_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if p: write_json(p, self.player_db); CustomInfo(self, "Database Exported!", "#3498db")
    def new_database(self):
        if messagebox.askyesno("NEW", "Clear current list?"): self.player_db = {}; self.save_active_db(); self.refresh_db_list()
    def delete_database(self):
        if messagebox.askyesno("CONFIRM", "Wipe active?"): self.player_db = {}; self.save_active_db(); self.refresh_db_list()

    def create_settings_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["settings"] = f
        ctk.CTkLabel(f, text="APPLICATION SETTINGS", font=ctk.CTkFont(size=22, weight="bold"), text_color="#ffffff").pack(anchor="w", pady=(20, 30))
        
        # Original logic restored: Manual Save Button
        dc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); dc.pack(fill="x", pady=10)
        idc = ctk.CTkFrame(dc, fg_color="transparent"); idc.pack(fill="x", padx=30, pady=25)
        ctk.CTkLabel(idc, text="DISCORD INTEGRATION", font=ctk.CTkFont(size=14, weight="bold"), text_color="#5865F2").pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(idc, text="Enter your server webhook URL to share results.", font=ctk.CTkFont(size=12), text_color="gray").pack(anchor="w", pady=(0, 10))
        self.hook_in = ctk.CTkEntry(idc, height=45, placeholder_text="Paste Webhook URL..."); self.hook_in.pack(fill="x"); self.hook_in.insert(0, self.webhook_url)
        
        uc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); uc.pack(fill="x", pady=10)
        iuc = ctk.CTkFrame(uc, fg_color="transparent"); iuc.pack(fill="x", padx=30, pady=25)
        self.up_v = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(iuc, text="Enable automatic version checks on startup", variable=self.up_v, onvalue="on", offvalue="off").pack(side="left")
        ctk.CTkLabel(iuc, textvariable=self.update_status_var, font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1c40f").pack(side="right")
        
        btn_row = ctk.CTkFrame(f, fg_color="transparent"); btn_row.pack(fill="x", pady=40)
        ctk.CTkButton(btn_row, text="SAVE CHANGES", width=220, height=50, corner_radius=15, fg_color="#1f538d", font=ctk.CTkFont(weight="bold"), command=self.manual_save_settings).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="CHECK FOR UPDATES", width=220, height=50, corner_radius=15, fg_color="#2a2a2a", font=ctk.CTkFont(weight="bold"), command=lambda: self.schedule_auto_update_check()).pack(side="left", padx=10)

    def manual_save_settings(self):
        self.webhook_url = self.hook_in.get().strip()
        self.auto_check_updates = self.up_v.get() == "on"
        self.save_config(); CustomInfo(self, "Settings Saved!", "#3498db")

    def generate_teams(self):
        try:
            ps = []
            for i in range(10):
                n = self.player_vars[i].get().strip()
                if n and n != PLACEHOLDER: ps.append({"name": n, "points": int(self.points_vars[i].get())})
            if len(ps) < 2: return
            best_diff, best_split = float('inf'), ([], [])
            rp = ps[:]; random.shuffle(rp)
            for combo in itertools.combinations(rp, len(rp)//2):
                t1, t2 = list(combo), [p for p in rp if p not in combo]
                diff = abs(sum(p['points'] for p in t1) - sum(p['points'] for p in t2))
                if diff < best_diff: best_diff, best_split = diff, (t1, t2)
                if diff == 0: break
            self.t1_list.configure(text="\n".join([p['name'] for p in best_split[0]])); self.t2_list.configure(text="\n".join([p['name'] for p in best_split[1]]))
            self.t1_total_label.configure(text=f"Total: {sum(p['points'] for p in best_split[0])}"); self.t2_total_label.configure(text=f"Total: {sum(p['points'] for p in best_split[1])}")
        except: pass

    def delete_teams(self):
        self.t1_list.configure(text=""); self.t2_list.configure(text="")
        self.t1_total_label.configure(text=""); self.t2_total_label.configure(text="")

    def get_saved_rosters(self): return sorted([f.replace(".json", "") for f in os.listdir(SAVES_DIR) if f.endswith(".json")], key=str.casefold)
    def save_roster_action(self):
        p = filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json")
        if p:
            d = {"ps": [{"n": self.player_vars[i].get(), "p": self.points_vars[i].get()} for i in range(10)]}
            write_json(p, d); self.roster_combo.configure(values=self.get_saved_rosters()); self.roster_combo.set(os.path.basename(p).replace(".json",""))
    def load_roster_action(self):
        rn = self.roster_combo.get()
        if rn and rn != "Select Roster...":
            d = read_json(os.path.join(SAVES_DIR, f"{rn}.json"))
            for i, p in enumerate(d.get("ps", [])):
                if i < 10: self.player_vars[i].set(p["n"]); self.points_vars[i].set(p["p"])
                self.player_entries[i].configure(text_color="#2ecc71" if p["n"] and p["n"]!=PLACEHOLDER else "white")

    def schedule_auto_update_check(self): threading.Thread(target=self._up_worker, daemon=True).start()
    def _up_worker(self):
        try:
            m = requests.get(DEFAULT_MANIFEST_URL, timeout=5).json()
            if is_newer_version(m["version"], APP_VERSION): self.update_status_var.set(f"Update {m['version']} Available")
        except: pass
    def send_to_discord(self):
        if not self.webhook_url: return
        self.update(); img = ImageGrab.grab(bbox=(self.result_container.winfo_rootx(), self.result_container.winfo_rooty(), self.result_container.winfo_rootx() + self.result_container.winfo_width(), self.result_container.winfo_rooty() + self.result_container.winfo_height()))
        buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        requests.post(self.webhook_url, files={"file": ("teams.png", buf, "image/png")}, data={"content": "**Teams**"}).raise_for_status()

if __name__ == "__main__":
    try: TeamGeneratorApp().mainloop()
    except Exception:
        with open(os.path.join(DATA_DIR, "crash_log.txt"), "w") as f: f.write(traceback.format_exc())
