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

# Windows Taskbar Icon Fix - Set ONCE globally
if sys.platform == "win32":
    try:
        import ctypes
        myappid = "theunrealforge.teamgenerator.final.fix.v1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass

# Set appearances
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# PORTABLE + STANDALONE LOGIC
APP_NAME = "TeamGenerator"
APP_VERSION = "1.1.0"
REQUEST_TIMEOUT = 15
AUTO_UPDATE_DELAY_MS = 1500
GITHUB_USER = "theunrealforge"
GITHUB_REPO = "teamgenerator"
DEFAULT_MANIFEST_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version_manifest.json"

# DATA PATH LOGIC
def get_root_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = get_root_dir()
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_DIR = os.path.join(DATA_DIR, "databases")
SAVES_DIR = os.path.join(DATA_DIR, "saves")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
# Internal assets (baked into EXE)
def get_asset_path(filename):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

ICON_PATH = get_asset_path("icon.ico")
ICON_PNG_PATH = get_asset_path("icon.png")

for d in [DATA_DIR, DB_DIR, SAVES_DIR]:
    os.makedirs(d, exist_ok=True)

DEFAULT_CONFIG = {
    "webhook_url": "",
    "update_manifest_url": DEFAULT_MANIFEST_URL,
    "auto_check_updates": True,
    "active_db": "default"
}

def read_json(path):
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def normalize_player_db(data):
    if not isinstance(data, dict): return {}
    return {str(k).strip(): str(v).strip() or "5" for k, v in data.items() if str(k).strip()}

def coerce_bool(value, default=True):
    if isinstance(value, bool): return value
    lowered = str(value).strip().lower()
    return lowered in {"1", "true", "yes", "on"} if lowered else default

def version_key(value):
    parts = []
    for part in str(value).replace("-", ".").split("."):
        if part.isdigit(): parts.append(int(part))
        else:
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits: parts.append(int(digits))
    return tuple(parts) if parts else (0,)

def is_newer_version(latest, current): return version_key(latest) > version_key(current)
def is_remote_url(value): return urlparse(str(value).strip()).scheme in {"http", "https"}

PLACEHOLDER = "Type player name or select..."

class CustomWarning(ctk.CTkToplevel):
    def __init__(self, master, title, message, button_text="OK"):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color="#e74c3c", corner_radius=20); self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.main_frame, text=message, font=ctk.CTkFont(size=16, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=(20, 10))
        ctk.CTkButton(self.main_frame, text=button_text, width=100, height=35, corner_radius=10, fg_color="#e74c3c", hover_color="#c0392b", command=self.destroy).pack(pady=(0, 20))

class CustomInfo(ctk.CTkToplevel):
    def __init__(self, master, message, color="#3498db"):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        master.update_idletasks()
        x, y = master.winfo_x() + (master.winfo_width()//2) - 150, master.winfo_y() + (master.winfo_height()//2) - 100
        self.geometry(f"300x200+{x}+{y}")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color=color, corner_radius=20); self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.main_frame, text=message, font=ctk.CTkFont(size=16, weight="bold"), text_color="white", wraplength=250).pack(expand=True, pady=(20, 10))
        ctk.CTkButton(self.main_frame, text="OK", width=100, height=35, corner_radius=10, fg_color=color, hover_color="#2980b9", command=self.destroy).pack(pady=(0, 20))

class PlayerDropdown(ctk.CTkToplevel):
    def __init__(self, master, slot_idx, players, selected_names, callback, take_focus=False):
        super().__init__(master)
        self.master_app, self.slot_idx, self.callback = master, slot_idx, callback
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=1, border_color="#333333", corner_radius=15); self.main_frame.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent", corner_radius=15); self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.update_context(slot_idx, players, selected_names); self.refresh_list("", take_focus=take_focus); self.bind("<FocusOut>", lambda e: self.after(200, self.check_destroy))
    def check_destroy(self):
        try:
            f = self.focus_get()
            if not f or (f != self and not str(f).startswith(str(self))):
                if f != self.master_app.player_entries[self.slot_idx]: self.destroy()
        except: self.destroy()
    def update_context(self, slot_idx, players, selected_names):
        self.slot_idx, self.all_players = slot_idx, sorted(players, key=str.casefold)
        self.selected_names = {n.casefold() for n in selected_names if isinstance(n, str) and n.strip()}
        entry = self.master_app.player_entries[slot_idx]
        self.geometry(f"{entry.winfo_width()+45}x300+{entry.winfo_rootx()}+{entry.winfo_rooty()+entry.winfo_height()+5}")
    def refresh_list(self, term, take_focus=False):
        for w in self.scroll.winfo_children(): w.destroy()
        filtered = [p for p in self.all_players if term.lower().strip() in p.lower()]
        if not filtered: ctk.CTkLabel(self.scroll, text="No players found", text_color="gray").pack(pady=10)
        else:
            for p in sorted(filtered):
                sel = p.casefold() in self.selected_names
                ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(size=13, weight="bold" if sel else "normal"), text_color="#2ecc71" if sel else "white", anchor="w", fg_color="transparent", hover_color="#252525", height=30, command=lambda n=p: (self.callback(n, self.slot_idx), self.destroy())).pack(fill="x", pady=1)
        if take_focus: self.focus_set()

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
        self.webhook_url, self.update_manifest_url, self.auto_check_updates, self.active_db_name = "", "", True, "default"
        self.player_db, self.player_entries, self.dropdown_window, self.is_updating, self.is_checking_updates, self.is_installing_update = {}, [], None, False, False, False
        self.load_config(); self.load_active_db(); self.setup_ui()
        for i in range(10): self.player_vars[i].trace_add("write", lambda *a, idx=i: self.on_type_search(idx))
        self.bg_frame.bind("<Button-1>", self.start_move); self.bg_frame.bind("<B1-Motion>", self.do_move)
        self.after(AUTO_UPDATE_DELAY_MS, self.schedule_auto_update_check)

    def start_move(self, event): self.x, self.y = event.x, event.y
    def do_move(self, event): self.geometry(f"+{self.winfo_x() + event.x - self.x}+{self.winfo_y() + event.y - self.y}")
    def load_config(self):
        c = DEFAULT_CONFIG.copy(); c.update(read_json(CONFIG_PATH))
        self.webhook_url, self.update_manifest_url, self.auto_check_updates, self.active_db_name = str(c["webhook_url"]), str(c["update_manifest_url"]), coerce_bool(c["auto_check_updates"]), str(c["active_db"])

    def save_config(self):
        write_json(CONFIG_PATH, {"webhook_url": self.webhook_url, "update_manifest_url": self.update_manifest_url, "auto_check_updates": self.auto_check_updates, "active_db": self.active_db_name})

    def load_active_db(self):
        p = os.path.join(DB_DIR, f"{self.active_db_name}.json")
        if not os.path.exists(p) and self.active_db_name == "default": write_json(p, {})
        self.player_db = normalize_player_db(read_json(p))

    def save_active_db(self):
        write_json(os.path.join(DB_DIR, f"{self.active_db_name}.json"), self.player_db)

    def setup_ui(self):
        ts = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=60); ts.pack(side="top", fill="x", padx=30, pady=(20, 0))
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
        for c, l in [("generator", "Generator"), ("database", "Database"), ("settings", "Settings")]:
            btn = ctk.CTkButton(self.nav_frame, text=l.upper(), width=160, height=45, corner_radius=12, fg_color="#1a1a1a", text_color="#aaaaaa", font=ctk.CTkFont(size=12, weight="bold"), command=lambda code=c: self.show_frame(code))
            btn.pack(side="left", padx=8); self.tab_buttons[c] = btn
        self.content_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.content_frame.pack(fill="both", expand=True, padx=40, pady=(0, 30))
        self.frames = {}; self.create_generator_ui(); self.create_database_ui(); self.create_settings_ui(); self.show_frame("generator")

    def show_frame(self, name):
        if self.dropdown_window: self.dropdown_window.destroy()
        for n, f in self.frames.items():
            f.pack_forget()
            b = self.tab_buttons.get(n)
            if b: b.configure(fg_color="#1f538d" if n == name else "#1a1a1a", text_color="white" if n == name else "#aaaaaa")
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
        if not (self.player_entries[idx].winfo_width() * 0.45 < ev.x < self.player_entries[idx].winfo_width() * 0.55):
            self.sync_dropdown(idx, "", False)

    def sync_dropdown(self, idx, term, take_focus):
        sel = [v.get().strip() for i, v in enumerate(self.player_vars) if i != idx and v.get().strip() != PLACEHOLDER]
        if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx:
            self.dropdown_window.update_context(idx, list(self.player_db.keys()), sel)
            self.dropdown_window.refresh_list(term, take_focus)
        else:
            if self.dropdown_window: self.dropdown_window.destroy()
            self.dropdown_window = PlayerDropdown(self, idx, list(self.player_db.keys()), sel, self.on_player_chosen, take_focus)

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
        ctrl = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f"); ctrl.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(ctrl, text="DATABASE PROFILE:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(20, 10), pady=20)
        self.db_selector = ctk.CTkComboBox(ctrl, values=self.get_db_list(), width=250, height=35, command=self.switch_db); self.db_selector.set(self.active_db_name); self.db_selector.pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="NEW", width=80, height=35, fg_color="#2ecc71", text_color="black", font=ctk.CTkFont(weight="bold"), command=self.new_db_profile).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="DELETE", width=80, height=35, fg_color="#c0392b", command=self.delete_db_profile).pack(side="left", padx=5)
        add = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f"); add.pack(fill="x", pady=5)
        ctk.CTkLabel(add, text="NAME:").pack(side="left", padx=15); self.db_name_in = ctk.CTkEntry(add, width=300, height=35); self.db_name_in.pack(side="left", padx=5, pady=15)
        ctk.CTkLabel(add, text="POINTS:").pack(side="left", padx=10); self.db_pts_in = ctk.CTkComboBox(add, values=[str(x) for x in range(1, 11)], width=80); self.db_pts_in.set("5"); self.db_pts_in.pack(side="left", padx=5)
        ctk.CTkButton(add, text="ADD PLAYER", width=120, height=35, fg_color="#1f538d", command=self.db_add_player).pack(side="right", padx=15)
        self.db_scroll = ctk.CTkScrollableFrame(f, fg_color="transparent"); self.db_scroll.pack(fill="both", expand=True, pady=10)

    def get_db_list(self): return [f.replace(".json", "") for f in os.listdir(DB_DIR) if f.endswith(".json")] or ["default"]
    def switch_db(self, name): self.active_db_name = name; self.save_config(); self.load_active_db(); self.refresh_db_list()
    def new_db_profile(self):
        n = tempfile.NamedTemporaryFile().name # Just for a simple prompt placeholder
        if msg := ctk.CTkInputDialog(text="Enter new profile name:", title="New Database").get_input():
            if msg.strip(): self.active_db_name = msg.strip(); self.player_db = {}; self.save_active_db(); self.save_config(); self.db_selector.configure(values=self.get_db_list()); self.db_selector.set(self.active_db_name); self.refresh_db_list()
    def delete_db_profile(self):
        if self.active_db_name == "default": return
        if messagebox.askyesno("Confirm", f"Delete profile '{self.active_db_name}'?"):
            os.remove(os.path.join(DB_DIR, f"{self.active_db_name}.json")); self.active_db_name = "default"; self.save_config(); self.load_active_db(); self.db_selector.configure(values=self.get_db_list()); self.db_selector.set("default"); self.refresh_db_list()

    def db_add_player(self):
        n, p = self.db_name_in.get().strip(), self.db_pts_in.get()
        if n:
            for k in list(self.player_db.keys()):
                if k.casefold() == n.casefold(): del self.player_db[k]
            self.player_db[n] = p; self.save_active_db(); self.refresh_db_list(); self.db_name_in.delete(0, 'end')

    def refresh_db_list(self):
        for w in self.db_scroll.winfo_children(): w.destroy()
        for n, p in sorted(self.player_db.items(), key=lambda x: x[0].casefold()):
            r = ctk.CTkFrame(self.db_scroll, fg_color="#121212", corner_radius=10); r.pack(fill="x", pady=4, padx=5)
            ctk.CTkLabel(r, text=n, width=250, anchor="w", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(r, text=f"Power: {p}", text_color="#888888").pack(side="left")
            ctk.CTkButton(r, text="DELETE", width=80, height=30, fg_color="#c0392b", command=lambda name=n: (self.player_db.pop(name), self.save_active_db(), self.refresh_db_list())).pack(side="right", padx=15)

    def create_settings_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["settings"] = f
        ctk.CTkLabel(f, text="APPLICATION SETTINGS", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", pady=(20, 30))
        dc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); dc.pack(fill="x", pady=10)
        idc = ctk.CTkFrame(dc, fg_color="transparent"); idc.pack(fill="x", padx=30, pady=25)
        ctk.CTkLabel(idc, text="DISCORD WEBHOOK", font=ctk.CTkFont(size=14, weight="bold"), text_color="#5865F2").pack(anchor="w", pady=(0, 10))
        self.hook_in = ctk.CTkEntry(idc, height=45, placeholder_text="Paste URL..."); self.hook_in.pack(fill="x"); self.hook_in.insert(0, self.webhook_url); self.hook_in.bind("<KeyRelease>", lambda e: self.auto_save_settings())
        uc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); uc.pack(fill="x", pady=10)
        iuc = ctk.CTkFrame(uc, fg_color="transparent"); iuc.pack(fill="x", padx=30, pady=25)
        self.auto_up_var = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(iuc, text="Enable automatic updates on startup", variable=self.auto_up_var, onvalue="on", offvalue="off", command=self.auto_save_settings).pack(side="left")
        ctk.CTkLabel(iuc, textvariable=self.update_status_var, font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1c40f").pack(side="right")
        ctk.CTkButton(f, text="CHECK FOR UPDATES NOW", height=50, fg_color="#2a2a2a", command=lambda: self.check_for_updates(False)).pack(fill="x", pady=20)

    def auto_save_settings(self):
        self.webhook_url, self.auto_check_updates = self.hook_in.get().strip(), self.auto_up_var.get() == "on"; self.save_config()

    def generate_teams(self):
        try:
            p_list = []
            for i in range(10):
                n = self.player_vars[i].get().strip()
                if n and n != PLACEHOLDER: p_list.append({"name": n, "points": int(self.points_vars[i].get())})
            if len(p_list) < 2: return
            best_diff, best_split = float('inf'), ([], [])
            rp = p_list[:]; random.shuffle(rp)
            for combo in itertools.combinations(rp, len(rp)//2):
                t1, t2 = list(combo), [p for p in rp if p not in combo]
                diff = abs(sum(p['points'] for p in t1) - sum(p['points'] for p in t2))
                if diff < best_diff: best_diff, best_split = diff, (t1, t2)
                if diff == 0: break
            self.t1_list.configure(text="\n".join([p['name'] for p in best_split[0]])); self.t2_list.configure(text="\n".join([p['name'] for p in best_split[1]]))
            self.t1_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[0])}"); self.t2_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[1])}")
        except Exception as e: CustomWarning(self, "ERROR", str(e))

    def get_saved_rosters(self): return sorted([f.replace(".json", "") for f in os.listdir(SAVES_DIR) if f.endswith(".json")], key=str.casefold)
    def save_roster_action(self):
        if n := filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json"):
            d = {"players": [{"name": self.player_vars[i].get() if self.player_vars[i].get() != PLACEHOLDER else "", "pts": self.points_vars[i].get()} for i in range(10)]}
            write_json(n, d); self.roster_combo.configure(values=self.get_saved_rosters()); self.roster_combo.set(os.path.basename(n).replace(".json", ""))
    def load_roster_action(self):
        rn = self.roster_combo.get()
        if rn and rn != "Select Roster...":
            ld = read_json(os.path.join(SAVES_DIR, f"{rn}.json"))
            ps = ld.get("players", [])
            for i in range(10):
                row = ps[i] if i < len(ps) else {}; n = str(row.get("name", ""))
                self.player_vars[i].set(n if n else PLACEHOLDER); self.points_vars[i].set(str(row.get("pts", "5")))
                self.player_entries[i].configure(text_color="#2ecc71" if n else "white")

    def schedule_auto_update_check(self):
        if self.auto_check_updates: self.check_for_updates(True)
    def check_for_updates(self, silent):
        if self.is_checking_updates: return
        self.is_checking_updates = True; threading.Thread(target=self._update_worker, args=(silent,), daemon=True).start()
    def _update_worker(self, s):
        try:
            m = requests.get(DEFAULT_MANIFEST_URL, timeout=10).json()
            if is_newer_version(m["version"], APP_VERSION): self.after(0, lambda: self.handle_up(m))
            elif not s: self.after(0, lambda: CustomInfo(self, "App is up to date!"))
        except: pass
        finally: self.is_checking_updates = False
    def handle_up(self, m):
        if messagebox.askyesno("Update", f"Version {m['version']} available. Install?"):
            self.is_installing_update = True
            threading.Thread(target=self._install_worker, args=(m,), daemon=True).start()
    def _install_worker(self, m):
        try:
            r = requests.get(m["url"], stream=True); wd = tempfile.mkdtemp(); tp = os.path.join(wd, "update.exe")
            with open(tp, "wb") as f:
                for c in r.iter_content(chunk_size=1024*1024): f.write(c)
            sp = os.path.join(tempfile.gettempdir(), f"up_{os.getpid()}.bat")
            with open(sp, "w") as f: f.write(f"@echo off\n:retry\ncopy /Y \"{tp}\" \"{sys.executable}\" >nul 2>&1\nif errorlevel 1 (timeout /t 1 >nul & goto retry)\nstart \"\" \"{sys.executable}\"\ndel \"%~f0\"")
            subprocess.Popen(["cmd", "/c", sp], creationflags=0x08000000); self.destroy()
        except: self.is_installing_update = False
    def send_to_discord(self):
        if not self.webhook_url: return
        self.update(); img = ImageGrab.grab(bbox=(self.result_container.winfo_rootx(), self.result_container.winfo_rooty(), self.result_container.winfo_rootx() + self.result_container.winfo_width(), self.result_container.winfo_rooty() + self.result_container.winfo_height()))
        buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        requests.post(self.webhook_url, files={"file": ("teams.png", buf, "image/png")}, data={"content": "**Teams**"}).raise_for_status()
        CustomInfo(self, "Shared!")

if __name__ == "__main__":
    try: app = TeamGeneratorApp(); app.mainloop()
    except Exception:
        with open(os.path.join(get_root_dir(), "crash_log.txt"), "w") as f: f.write(traceback.format_exc())
