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
        # Fresh unique ID
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

DEFAULT_CONFIG = {
    "webhook_url": "",
    "update_manifest_url": DEFAULT_MANIFEST_URL,
    "auto_check_updates": True,
}

def get_base_path():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', BASE_DIR), APP_NAME)

def get_portable_dirs():
    dirs = [BASE_DIR]
    if not getattr(sys, 'frozen', False):
        parent_dir = os.path.dirname(BASE_DIR)
        if os.path.basename(BASE_DIR).lower() == "source code" and parent_dir not in dirs:
            dirs.append(parent_dir)
    return dirs

PORTABLE_DIRS = get_portable_dirs()

def ensure_directory(path):
    if path:
        os.makedirs(path, exist_ok=True)

def resolve_path(filename, is_dir=False):
    for directory in PORTABLE_DIRS:
        candidate = os.path.join(directory, filename)
        if os.path.exists(candidate):
            return candidate
    if is_dir:
        local_candidate = os.path.join(PORTABLE_DIRS[0], filename)
        try:
            ensure_directory(local_candidate)
            return local_candidate
        except OSError: pass
    ensure_directory(APPDATA_DIR)
    return os.path.join(APPDATA_DIR, filename)

def read_json(path):
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def write_json(path, data):
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def normalize_player_db(data):
    if not isinstance(data, dict): raise ValueError("Player database must be a JSON object.")
    normalized = {}
    for raw_name, raw_points in data.items():
        name = str(raw_name).strip()
        if not name: continue
        points = str(raw_points).strip() or "5"
        normalized[name] = points
    return normalized

def coerce_bool(value, default=True):
    if isinstance(value, bool): return value
    if value is None: return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}: return True
    if lowered in {"0", "false", "no", "off"}: return False
    return default

def version_key(value):
    parts = []
    for part in str(value).replace("-", ".").split("."):
        if part.isdigit(): parts.append(int(part))
        else:
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits: parts.append(int(digits))
    return tuple(parts) if parts else (0,)

def is_newer_version(latest, current): return version_key(latest) > version_key(current)
def is_remote_url(value):
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"}

CONFIG_PATH = resolve_path("config.json")
PLAYER_DB_PATH = resolve_path("player_database.json")
ICON_PATH = resolve_path("icon.ico")
SAVES_DIR = resolve_path("saves", is_dir=True)
CRASH_LOG_PATH = os.path.join(BASE_DIR, "crash_log.txt")

if not os.path.exists(SAVES_DIR):
    try: os.makedirs(SAVES_DIR)
    except: pass

PLACEHOLDER = "Type player name or select..."

class CustomWarning(ctk.CTkToplevel):
    def __init__(self, master, title, message, button_text="OK"):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")
        master.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - 150
        y = master.winfo_y() + (master.winfo_height() // 2) - 100
        self.geometry(f"300x200+{x}+{y}")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color="#e74c3c", corner_radius=20)
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.msg_label = ctk.CTkLabel(self.main_frame, text=message, font=ctk.CTkFont(size=16, weight="bold"), text_color="white", wraplength=250)
        self.msg_label.pack(expand=True, pady=(20, 10))
        self.btn = ctk.CTkButton(self.main_frame, text=button_text, width=100, height=35, corner_radius=10, fg_color="#e74c3c", hover_color="#c0392b", command=self.destroy)
        self.btn.pack(pady=(0, 20))

class CustomInfo(ctk.CTkToplevel):
    def __init__(self, master, message, color="#3498db"):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")
        master.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - 150
        y = master.winfo_y() + (master.winfo_height() // 2) - 100
        self.geometry(f"300x200+{x}+{y}")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=2, border_color=color, corner_radius=20)
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.msg_label = ctk.CTkLabel(self.main_frame, text=message, font=ctk.CTkFont(size=16, weight="bold"), text_color="white", wraplength=250)
        self.msg_label.pack(expand=True, pady=(20, 10))
        self.btn = ctk.CTkButton(self.main_frame, text="OK", width=100, height=35, corner_radius=10, fg_color=color, hover_color="#2980b9", command=self.destroy)
        self.btn.pack(pady=(0, 20))

class PlayerDropdown(ctk.CTkToplevel):
    def __init__(self, master, slot_idx, players, selected_names, callback, take_focus=False):
        super().__init__(master)
        self.master_app = master
        self.slot_idx = slot_idx
        self.all_players = []
        self.selected_names = set()
        self.callback = callback
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")
        self.main_frame = ctk.CTkFrame(self, fg_color="#121212", border_width=1, border_color="#333333", corner_radius=15)
        self.main_frame.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent", corner_radius=15)
        self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.update_context(slot_idx, players, selected_names)
        self.refresh_list("", take_focus=take_focus)
        self.bind("<FocusOut>", self.on_focus_out)
    def on_focus_out(self, event): self.after(200, self.check_destroy)
    def check_destroy(self):
        try:
            focus = self.focus_get()
            if not focus or (focus != self and not str(focus).startswith(str(self))):
                if focus != self.master_app.player_entries[self.slot_idx]: self.destroy()
        except: self.destroy()
    def update_context(self, slot_idx, players, selected_names):
        self.slot_idx = slot_idx
        self.all_players = sorted(players, key=str.casefold)
        self.selected_names = {name.casefold() for name in selected_names if isinstance(name, str) and name.strip()}
        entry = self.master_app.player_entries[slot_idx]
        x, y, w = entry.winfo_rootx(), entry.winfo_rooty() + entry.winfo_height() + 5, entry.winfo_width() + 45
        self.geometry(f"{w}x300+{x}+{y}")
    def refresh_list(self, search_term, take_focus=False):
        for widget in self.scroll.winfo_children(): widget.destroy()
        filtered = [p for p in self.all_players if search_term.lower().strip() in p.lower()]
        if not filtered: ctk.CTkLabel(self.scroll, text="No players found", text_color="gray").pack(pady=10)
        else:
            for p in sorted(filtered):
                is_selected = p.casefold() in self.selected_names
                btn = ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(size=13, weight="bold" if is_selected else "normal"), text_color="#2ecc71" if is_selected else "white", anchor="w", fg_color="transparent", hover_color="#252525", height=30, command=lambda name=p: self.select_player(name))
                btn.pack(fill="x", pady=1)
        if take_focus: self.focus_set()
    def select_player(self, name): self.callback(name, self.slot_idx); self.destroy()

class TeamGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ULTIMATE TEAM GENERATOR")
        self.geometry("1050x1100")
        
        # Professional Taskbar Fix: Keep overrideredirect(True) but force the icon on taskbar
        self.overrideredirect(True)
        self.after(10, self.set_windows_taskbar_presence)
        
        self.attributes("-alpha", 0.99)
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")
        
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
                # Force high-res icon handles directly onto the window manager handles
                def force_high_res_icon():
                    try:
                        import ctypes
                        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                        if not hwnd: hwnd = self.winfo_id()
                        hicon = ctypes.windll.user32.LoadImageW(None, ICON_PATH, 1, 256, 256, 0x00000010)
                        if hicon:
                            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, hicon) # ICON_BIG
                            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, hicon) # ICON_SMALL
                    except: pass
                self.after(200, force_high_res_icon)
            except: pass

        self.bg_frame = ctk.CTkFrame(self, fg_color="#080808", corner_radius=35, border_width=1, border_color="#1f1f1f")
        self.bg_frame.pack(fill="both", expand=True)
        self.player_vars = [ctk.StringVar(value=PLACEHOLDER) for _ in range(10)]
        self.points_vars = [ctk.StringVar(value="5") for _ in range(10)]
        self.update_status_var = ctk.StringVar(value=f"Version {APP_VERSION}")
        self.webhook_url = ""; self.update_manifest_url = ""; self.auto_check_updates = True
        self.player_db = {}; self.player_entries = []; self.dropdown_window = None
        self.is_updating = False; self.is_checking_updates = False; self.is_installing_update = False
        self.load_config(); self.load_player_db(); self.setup_ui()
        for i in range(10): self.player_vars[i].trace_add("write", lambda *args, idx=i: self.on_type_search(idx))
        self.bg_frame.bind("<Button-1>", self.start_move)
        self.bg_frame.bind("<B1-Motion>", self.do_move)
        self.after(AUTO_UPDATE_DELAY_MS, self.schedule_auto_update_check)

    def set_windows_taskbar_presence(self):
        if sys.platform == "win32":
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd: hwnd = self.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.withdraw(); self.after(10, self.deiconify)

    def start_move(self, event): self.x, self.y = event.x, event.y
    def do_move(self, event): self.geometry(f"+{self.winfo_x() + event.x - self.x}+{self.winfo_y() + event.y - self.y}")
    def find_player_db_key(self, name):
        target = name.strip().casefold()
        if not target: return None
        for k in self.player_db:
            if k.casefold() == target: return k
        return None
    def get_selected_names(self, exclude_idx=None):
        names = []
        for i, var in enumerate(self.player_vars):
            if i != exclude_idx:
                v = var.get().strip()
                if v and v != PLACEHOLDER: names.append(v)
        return names
    def close_dropdown(self):
        if self.dropdown_window and self.dropdown_window.winfo_exists(): self.dropdown_window.destroy()
        self.dropdown_window = None
    def sync_dropdown(self, idx, search_term="", take_focus=False):
        selected_names = self.get_selected_names(exclude_idx=idx)
        if not self.dropdown_window or not self.dropdown_window.winfo_exists() or self.dropdown_window.slot_idx != idx:
            self.close_dropdown()
            self.dropdown_window = PlayerDropdown(self, idx, list(self.player_db.keys()), selected_names, self.on_player_chosen, take_focus=take_focus)
        else: self.dropdown_window.update_context(idx, list(self.player_db.keys()), selected_names)
        self.dropdown_window.refresh_list(search_term, take_focus=take_focus)
    def load_config(self):
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                loaded = read_json(CONFIG_PATH)
                if isinstance(loaded, dict): config.update(loaded)
            except: pass
        self.webhook_url, self.update_manifest_url = str(config.get("webhook_url", "")).strip(), str(config.get("update_manifest_url", "")).strip()
        self.auto_check_updates = coerce_bool(config.get("auto_check_updates", True), True)
    def load_player_db(self, path=None):
        target = path if path else PLAYER_DB_PATH
        if os.path.exists(target):
            try: self.player_db = normalize_player_db(read_json(target)); return True
            except:
                if path is None: self.player_db = {}
                return False
        if path is None: self.player_db = {}
        return False
    def save_player_db(self, path=None):
        try: write_json(path if path else PLAYER_DB_PATH, self.player_db); return True
        except: return False

    def setup_ui(self):
        self.top_section = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=60)
        self.top_section.pack(side="top", fill="x", padx=30, pady=(20, 0))
        icon_png_path = os.path.join(BASE_DIR, "icon.png")
        if not os.path.exists(icon_png_path): icon_png_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if os.path.exists(icon_png_path):
            try:
                from PIL import Image
                self.logo_img = ctk.CTkImage(light_image=Image.open(icon_png_path), size=(42, 42))
                ctk.CTkLabel(self.top_section, image=self.logo_img, text="").pack(side="left", padx=(0, 2))
            except: pass
        ctk.CTkLabel(self.top_section, text="TEAM GENERATOR", font=ctk.CTkFont(size=17, weight="bold"), text_color="#ffffff").pack(side="left")
        ctk.CTkButton(self.top_section, text="✕", width=40, height=40, corner_radius=10, fg_color="#1a1a1a", text_color="gray", hover_color="#e74c3c", command=self.quit).pack(side="right")
        self.nav_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.nav_frame.pack(pady=20)
        self.tab_buttons = {}
        for code, label in [("generator", "Generator"), ("database", "Database"), ("settings", "Settings")]:
            btn = ctk.CTkButton(self.nav_frame, text=label.upper(), width=160, height=45, corner_radius=12, fg_color="#1a1a1a", text_color="#aaaaaa", font=ctk.CTkFont(size=12, weight="bold"), command=lambda c=code: self.show_frame(c))
            btn.pack(side="left", padx=8); self.tab_buttons[code] = btn
        self.content_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.content_frame.pack(fill="both", expand=True, padx=40, pady=(0, 30))
        self.frames = {}; self.create_generator_ui(); self.create_database_ui(); self.create_settings_ui(); self.show_frame("generator")

    def show_frame(self, name):
        self.close_dropdown()
        for f, fr in self.frames.items():
            fr.pack_forget()
            b = self.tab_buttons.get(f)
            if b: b.configure(fg_color="#1f538d" if f == name else "#1a1a1a", text_color="white" if f == name else "#aaaaaa")
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
        self.t1_name_entry.bind("<KeyRelease>", lambda e: self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper()))
        self.t2_name_entry.bind("<KeyRelease>", lambda e: self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper()))
        p_grid = ctk.CTkFrame(f, fg_color="transparent"); p_grid.pack(fill="both", expand=True, pady=5)
        self.player_entries = []
        for i in range(10):
            r = ctk.CTkFrame(p_grid, fg_color="transparent"); r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=str(i+1), width=35, text_color="#555555", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=5)
            e = ctk.CTkEntry(r, textvariable=self.player_vars[i], height=35, fg_color="#111111", border_color="#222222", corner_radius=8); e.pack(side="left", expand=True, fill="x", padx=(10, 0)); self.player_entries.append(e)
            ctk.CTkButton(r, text="▼", width=35, height=35, corner_radius=8, fg_color="#1a1a1a", border_width=1, border_color="#222222", command=lambda idx=i: self.toggle_dropdown(idx)).pack(side="left", padx=(5, 10))
            e.bind("<Button-1>", lambda ev, idx=i: self.handle_entry_click(ev, idx))
            ctk.CTkComboBox(r, values=[str(x) for x in range(1, 11)], variable=self.points_vars[i], width=90, height=35, fg_color="#111111", border_color="#222222", corner_radius=8, command=lambda v, idx=i: self.check_player_locks(v, idx)).pack(side="right", padx=5)
        act_row = ctk.CTkFrame(f, fg_color="transparent"); act_row.pack(pady=10, fill="x")
        ai = ctk.CTkFrame(act_row, fg_color="transparent"); ai.pack(expand=True)
        ctk.CTkButton(ai, text="GENERATE TEAMS", font=ctk.CTkFont(size=16, weight="bold"), width=250, height=55, corner_radius=15, fg_color="#1f538d", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="REFRESH", width=120, height=55, corner_radius=15, fg_color="#2a2a2a", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="DELETE TEAMS", width=120, height=55, corner_radius=15, fg_color="#c0392b", command=self.delete_teams).pack(side="left", padx=10)
        ctk.CTkButton(ai, text="DISCORD", width=120, height=55, corner_radius=15, fg_color="#5865F2", command=self.send_to_discord).pack(side="left", padx=10)
        self.result_container = ctk.CTkFrame(f, fg_color="#050505", corner_radius=30, border_width=1, border_color="#1f1f1f", height=420); self.result_container.pack(fill="x", pady=(5, 0)); self.result_container.pack_propagate(False)
        self.t1_box = ctk.CTkFrame(self.result_container, fg_color="#0a0a0a", corner_radius=25); self.t1_box.place(relx=0.02, rely=0.05, relwidth=0.46, relheight=0.9)
        self.t2_box = ctk.CTkFrame(self.result_container, fg_color="#0a0a0a", corner_radius=25); self.t2_box.place(relx=0.52, rely=0.05, relwidth=0.46, relheight=0.9)
        self.t1_title = ctk.CTkLabel(self.t1_box, text="TEAM 1", font=ctk.CTkFont(size=18, weight="bold"), text_color="#3498db"); self.t1_title.pack(pady=(10, 2)); ctk.CTkFrame(self.t1_box, fg_color="#3498db", height=2, width=150).pack(pady=(0, 2))
        self.t1_list = ctk.CTkLabel(self.t1_box, text="", font=ctk.CTkFont(size=28, weight="bold"), justify="center", text_color="#ecf0f1"); self.t1_list.pack(expand=True, fill="both", pady=5)
        self.t1_total_label = ctk.CTkLabel(self.t1_box, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3498db"); self.t1_total_label.pack(pady=(0, 10))
        self.t2_title = ctk.CTkLabel(self.t2_box, text="TEAM 2", font=ctk.CTkFont(size=18, weight="bold"), text_color="#e74c3c"); self.t2_title.pack(pady=(10, 2)); ctk.CTkFrame(self.t2_box, fg_color="#e74c3c", height=2, width=150).pack(pady=(0, 2))
        self.t2_list = ctk.CTkLabel(self.t2_box, text="", font=ctk.CTkFont(size=28, weight="bold"), justify="center", text_color="#ecf0f1"); self.t2_list.pack(expand=True, fill="both", pady=5)
        self.t2_total_label = ctk.CTkLabel(self.t2_box, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color="#e74c3c"); self.t2_total_label.pack(pady=(0, 10))

    def on_type_search(self, idx):
        if self.is_updating: return
        val = self.player_vars[idx].get().strip(); db_match = self.find_player_db_key(val)
        if db_match: self.player_entries[idx].configure(text_color="#2ecc71"); self.points_vars[idx].set(self.player_db[db_match])
        else: self.player_entries[idx].configure(text_color="white")
        if val == PLACEHOLDER or not val:
            if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx: self.close_dropdown()
            return
        self.sync_dropdown(idx, val, take_focus=False)
    def handle_entry_click(self, ev, idx):
        w = self.player_entries[idx].winfo_width(); is_center = (w * 0.45 < ev.x < w * 0.55)
        if self.player_vars[idx].get() == PLACEHOLDER: self.player_vars[idx].set(""); self.player_entries[idx].configure(text_color="white")
        if not is_center:
            val = self.player_vars[idx].get().strip()
            self.sync_dropdown(idx, "" if val == PLACEHOLDER else val, take_focus=False)
    def toggle_dropdown(self, idx, take_focus=True):
        if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx: self.close_dropdown()
        else:
            val = self.player_vars[idx].get().strip()
            self.sync_dropdown(idx, "" if val == PLACEHOLDER else val, take_focus=take_focus)
    def on_player_chosen(self, name, idx):
        for i, var in enumerate(self.player_vars):
            if i != idx and var.get().strip().casefold() == name.casefold(): CustomWarning(self, "SYSTEM ERROR", f"{name} is already chosen!", "OK"); return
        self.is_updating = True; self.player_vars[idx].set(name); self.player_entries[idx].configure(text_color="#2ecc71")
        if name in self.player_db: self.points_vars[idx].set(self.player_db[name])
        self.is_updating = False; self.close_dropdown()
    def delete_teams(self):
        self.t1_list.configure(text=""); self.t2_list.configure(text=""); self.t1_total_label.configure(text=""); self.t2_total_label.configure(text="")
    def check_player_locks(self, val, idx):
        name = self.player_vars[idx].get().strip(); db_match = self.find_player_db_key(name)
        if name and name != PLACEHOLDER and db_match: self.player_db[db_match] = val; self.save_player_db()
    def create_database_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["database"] = f
        af = ctk.CTkFrame(f, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f"); af.pack(fill="x", pady=15, padx=10)
        ctk.CTkLabel(af, text="NAME:").pack(side="left", padx=15); self.db_name_input = ctk.CTkEntry(af, width=320, height=35, fg_color="#0a0a0a", border_color="#252525"); self.db_name_input.pack(side="left", padx=5, pady=15)
        ctk.CTkLabel(af, text="POINTS:").pack(side="left", padx=15); self.db_pts_input = ctk.CTkComboBox(af, values=[str(x) for x in range(1, 11)], width=90, height=35, fg_color="#0a0a0a"); self.db_pts_input.pack(side="left", padx=5)
        ctk.CTkButton(af, text="ADD / UPDATE", width=140, height=35, corner_radius=8, fg_color="#1f538d", command=self.db_add_player).pack(side="right", padx=15)
        m_row = ctk.CTkFrame(f, fg_color="transparent"); m_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(m_row, text="LOAD DATABASE", width=150, fg_color="#2ecc71", text_color="black", font=ctk.CTkFont(weight="bold"), command=self.load_external_db).pack(side="left", padx=5)
        ctk.CTkButton(m_row, text="SAVE DATABASE AS", width=150, fg_color="#3498db", text_color="black", font=ctk.CTkFont(weight="bold"), command=self.save_db_as).pack(side="left", padx=5)
        ctk.CTkButton(m_row, text="NEW DATABASE", width=150, fg_color="#333333", command=self.new_database).pack(side="left", padx=5)
        ctk.CTkButton(m_row, text="DELETE ACTIVE", width=150, fg_color="#c0392b", command=self.delete_database).pack(side="left", padx=5)
        self.db_scroll = ctk.CTkScrollableFrame(f, fg_color="transparent"); self.db_scroll.pack(fill="both", expand=True, pady=10); self.refresh_db_list()
    def load_external_db(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if p:
            if self.load_player_db(p): self.save_player_db(); self.refresh_db_list(); CustomInfo(self, "Database Loaded Successfully", "#2ecc71")
            else: CustomWarning(self, "LOAD FAILED", "That database file could not be read.", "OK")
    def save_db_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if p: self.save_player_db(p); CustomInfo(self, "Database Saved Successfully", "#3498db")
    def new_database(self):
        if messagebox.askyesno("NEW", "Create fresh empty list?"): self.player_db = {}; self.save_player_db(); self.refresh_db_list()
    def delete_database(self):
        if messagebox.askyesno("CONFIRM", "Proceed?"): self.player_db = {}; self.save_player_db(); self.refresh_db_list()
    def db_add_player(self):
        n, pts = self.db_name_input.get().strip(), self.db_pts_input.get()
        if n:
            ex = self.find_player_db_key(n)
            if ex and ex != n: del self.player_db[ex]
            self.player_db[n] = pts; self.save_player_db(); self.refresh_db_list(); self.db_name_input.delete(0, 'end')
    def refresh_db_list(self):
        for w in self.db_scroll.winfo_children(): w.destroy()
        for n, pts in sorted(self.player_db.items(), key=lambda item: item[0].casefold()):
            r = ctk.CTkFrame(self.db_scroll, fg_color="#121212", corner_radius=10); r.pack(fill="x", pady=4, padx=5)
            ctk.CTkLabel(r, text=n, width=250, anchor="w", text_color="#ecf0f1", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(r, text=f"Power: {pts}", width=120, text_color="#888888").pack(side="left")
            ctk.CTkButton(r, text="DELETE", width=80, height=30, fg_color="#c0392b", command=lambda name=n: self.delete_player(name)).pack(side="right", padx=15)
    def delete_player(self, n):
        if messagebox.askyesno("Confirm", f"Remove {n}?"):
            if n in self.player_db: del self.player_db[n]; self.save_player_db(); self.refresh_db_list()
    def create_settings_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["settings"] = f
        hf = ctk.CTkFrame(f, fg_color="transparent"); hf.pack(fill="x", pady=(20, 30))
        ctk.CTkLabel(hf, text="APPLICATION SETTINGS", font=ctk.CTkFont(size=22, weight="bold"), text_color="#ffffff").pack(side="left")
        ctk.CTkLabel(hf, text=f"Build v{APP_VERSION}", font=ctk.CTkFont(size=12), text_color="#555555").pack(side="right", pady=(10, 0))
        dc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); dc.pack(fill="x", pady=10, padx=2)
        idc = ctk.CTkFrame(dc, fg_color="transparent"); idc.pack(fill="x", padx=30, pady=25)
        ctk.CTkLabel(idc, text="DISCORD INTEGRATION", font=ctk.CTkFont(size=14, weight="bold"), text_color="#5865F2").pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(idc, text="Enter your server webhook URL to share team results automatically.", font=ctk.CTkFont(size=12), text_color="#888888").pack(anchor="w", pady=(0, 15))
        self.hook_input = ctk.CTkEntry(idc, width=700, height=45, placeholder_text="Paste Webhook URL...", fg_color="#0a0a0a", border_color="#2a2a2a", corner_radius=10); self.hook_input.pack(fill="x")
        if self.webhook_url: self.hook_input.insert(0, self.webhook_url)
        uc = ctk.CTkFrame(f, fg_color="#121212", corner_radius=20, border_width=1, border_color="#1f1f1f"); uc.pack(fill="x", pady=10, padx=2)
        iuc = ctk.CTkFrame(uc, fg_color="transparent"); iuc.pack(fill="x", padx=30, pady=25)
        ctk.CTkLabel(iuc, text="SOFTWARE UPDATES", font=ctk.CTkFont(size=14, weight="bold"), text_color="#2ecc71").pack(anchor="w", pady=(0, 5))
        cr = ctk.CTkFrame(iuc, fg_color="transparent"); cr.pack(fill="x", pady=(10, 0))
        self.auto_update_var = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(cr, text="Enable automatic version checks on startup", variable=self.auto_update_var, onvalue="on", offvalue="off", font=ctk.CTkFont(size=13), border_color="#2ecc71").pack(side="left")
        ctk.CTkLabel(iuc, textvariable=self.update_status_var, font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1c40f").pack(anchor="w", pady=(15, 0))
        ab = ctk.CTkFrame(f, fg_color="transparent"); ab.pack(fill="x", pady=(40, 0))
        iac = ctk.CTkFrame(ab, fg_color="transparent"); iac.pack(expand=True)
        ctk.CTkButton(iac, text="SAVE CHANGES", width=200, height=50, corner_radius=15, fg_color="#1f538d", font=ctk.CTkFont(size=14, weight="bold"), command=self.save_settings).pack(side="left", padx=10)
        ctk.CTkButton(iac, text="CHECK FOR UPDATES", width=200, height=50, corner_radius=15, fg_color="#2a2a2a", font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.check_for_updates(silent=False)).pack(side="left", padx=10)
    def save_settings(self):
        self.webhook_url, self.auto_check_updates = self.hook_input.get().strip(), self.auto_update_var.get() == "on"
        try: write_json(CONFIG_PATH, {"webhook_url": self.webhook_url, "update_manifest_url": self.update_manifest_url, "auto_check_updates": self.auto_check_updates}); self.update_status_var.set(f"Version {APP_VERSION}"); CustomInfo(self, "Settings Saved Successfully", "#3498db")
        except: CustomWarning(self, "SAVE FAILED", "Could not save config.", "OK")
    def schedule_auto_update_check(self):
        if self.auto_check_updates and self.get_manifest_source(): self.check_for_updates(silent=True)
    def get_manifest_source(self): return self.update_manifest_url
    def set_update_status(self, m): self.update_status_var.set(m)
    def check_for_updates(self, silent=False):
        if self.is_checking_updates or self.is_installing_update: return
        manifest_source = self.get_manifest_source()
        if not manifest_source:
            self.set_update_status(f"Version {APP_VERSION}")
            if not silent: CustomWarning(self, "UPDATE CONFIG", "Add an update manifest URL first.", "OK")
            return
        self.is_checking_updates = True; self.set_update_status("Checking for updates...")
        threading.Thread(target=self._check_for_updates_worker, args=(manifest_source, silent), daemon=True).start()
    def _check_for_updates_worker(self, ms, s):
        try:
            m = self.load_update_manifest(ms)
            if not is_newer_version(m["version"], APP_VERSION): self.after(0, lambda: self.finish_update_check(f"Already up to date ({APP_VERSION}).", s, False))
            else: self.after(0, lambda: self.handle_available_update(m, s))
        except Exception as e: self.after(0, lambda: self.finish_update_check(f"Update check failed: {e}", s, True))
    def finish_update_check(self, m, s, err=False):
        self.is_checking_updates = False; self.set_update_status(m)
        if s: return
        if err: CustomWarning(self, "UPDATE ERROR", m, "OK")
        else: CustomInfo(self, m, "#2ecc71")
    def load_update_manifest(self, ms):
        src = ms.strip()
        if is_remote_url(src):
            r = requests.get(src, timeout=REQUEST_TIMEOUT); r.raise_for_status(); d = r.json()
        else:
            mp = src if os.path.isabs(src) else os.path.join(BASE_DIR, src)
            d = read_json(mp); src = mp
        if not isinstance(d, dict): raise ValueError("Update manifest must be a JSON object.")
        v, url, n = str(d.get("version", "")).strip(), str(d.get("url", "")).strip(), str(d.get("notes", "")).strip()
        if not v or not url: raise ValueError("Update manifest must include version and url.")
        return {"version": v, "url": url, "notes": n, "source": src}
    def resolve_update_asset_source(self, m):
        a, ms = m["url"], m["source"]
        if is_remote_url(a) or os.path.isabs(a): return a
        if is_remote_url(ms): return urljoin(ms, a)
        return os.path.join(os.path.dirname(ms), a)
    def handle_available_update(self, m, s):
        self.is_checking_updates = False; v, n = m["version"], m.get("notes", "")
        if not getattr(sys, "frozen", False):
            self.set_update_status(f"Update {v} is available.")
            if not s: CustomInfo(self, f"Update {v} is available.\nAutomatic install works from EXE builds.", "#2ecc71")
            return
        msg = f"Version {v} is available."
        if n: msg = f"{msg}\n\nNotes:\n{n}"
        self.set_update_status(f"Update {v} is available.")
        if messagebox.askyesno("Update Available", f"{msg}\n\nInstall now?"): self.install_update(m)
    def install_update(self, m):
        if self.is_installing_update: return
        self.is_installing_update = True; self.set_update_status(f"Downloading update {m['version']}...")
        threading.Thread(target=self._install_update_worker, args=(m,), daemon=True).start()
    def _install_update_worker(self, m):
        wd = tempfile.mkdtemp(prefix="teamgenerator_update_")
        try:
            a = self.resolve_update_asset_source(m); d_exe = self.download_update_asset(a, wd)
            sp = self.create_update_script(d_exe, wd); self.after(0, lambda: self.launch_update_script(sp, m["version"]))
        except Exception as e: shutil.rmtree(wd, ignore_errors=True); self.after(0, lambda: self.fail_update_install(str(e)))
    def download_update_asset(self, a, wd):
        if is_remote_url(a):
            p = urlparse(a); tp = os.path.join(wd, os.path.basename(p.path) or "TeamGenerator.exe")
            with requests.get(a, stream=True, timeout=REQUEST_TIMEOUT) as r:
                r.raise_for_status()
                with open(tp, "wb") as f:
                    for c in r.iter_content(chunk_size=1024*1024):
                        if c: f.write(c)
            return tp
        if not os.path.exists(a): raise FileNotFoundError(f"Update file not found: {a}")
        tp = os.path.join(wd, os.path.basename(a) or "TeamGenerator.exe")
        shutil.copy2(a, tp); return tp
    def create_update_script(self, d_exe, wd):
        sp = os.path.join(tempfile.gettempdir(), f"tg_up_{os.getpid()}.bat")
        script = f"@echo off\nsetlocal enableextensions\n:retry\ncopy /Y \"{d_exe}\" \"{sys.executable}\" >nul 2>&1\nif errorlevel 1 (\n  timeout /t 1 /nobreak >nul\n  goto retry\n)\nstart \"\" \"{sys.executable}\"\nrmdir /S /Q \"{wd}\" >nul 2>&1\ndel \"%~f0\"\n"
        with open(sp, "w", encoding="utf-8", newline="\r\n") as f: f.write(script)
        return sp
    def launch_update_script(self, sp, v):
        try: subprocess.Popen(["cmd", "/c", sp], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e: self.fail_update_install(str(e)); return
        self.set_update_status(f"Installing update {v}..."); messagebox.showinfo("Installing Update", f"The app will close to install version {v}."); self.destroy()
    def fail_update_install(self, m): self.is_installing_update = False; self.set_update_status(f"Update failed: {m}"); CustomWarning(self, "UPDATE FAILED", m, "OK")
    def generate_teams(self):
        try:
            p_list = []
            seen = set()
            for i in range(10):
                n = self.player_vars[i].get().strip()
                if not n or n == PLACEHOLDER: continue
                if n.casefold() in seen: raise ValueError(f"{n} is duplicated.")
                seen.add(n.casefold()); p_list.append({"name": n, "points": int(self.points_vars[i].get())})
            if len(p_list) < 2: CustomWarning(self, "NOT ENOUGH PLAYERS", "Add at least two players.", "OK"); return
            best_diff, best_split = float('inf'), ([], [])
            rp = p_list[:]; random.shuffle(rp)
            for combo in itertools.combinations(rp, len(rp)//2):
                t1, t2 = list(combo), [p for p in rp if p not in combo]
                diff = abs(sum(p['points'] for p in t1) - sum(p['points'] for p in t2))
                if diff < best_diff: best_diff, best_split = diff, (t1, t2)
                if diff == 0: break
            self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper()); self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper())
            self.t1_list.configure(text="\n".join([p['name'] for p in best_split[0]])); self.t2_list.configure(text="\n".join([p['name'] for p in best_split[1]]))
            self.t1_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[0])}"); self.t2_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[1])}")
        except Exception as e: CustomWarning(self, "SYSTEM ERROR", str(e), "OK")
    def get_roster_path(self, rn):
        cn = rn.strip()
        if not cn: raise ValueError("Empty name.")
        if not cn.lower().endswith(".json"): cn = f"{cn}.json"
        return os.path.join(SAVES_DIR, os.path.basename(cn))
    def save_roster_action(self):
        n = filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if n:
            tp = self.get_roster_path(os.path.basename(n))
            d = {"team_names": {"team_1": self.t1_name_entry.get().strip(), "team_2": self.t2_name_entry.get().strip()}, "players": [{"name": self.player_vars[i].get().strip() if self.player_vars[i].get().strip() != PLACEHOLDER else "", "pts": self.points_vars[i].get()} for i in range(10)]}
            try: write_json(tp, d); self.roster_combo.configure(values=self.get_saved_rosters()); self.roster_combo.set(os.path.splitext(os.path.basename(tp))[0]); CustomInfo(self, "Roster Saved Successfully", "#2ecc71")
            except: CustomWarning(self, "SAVE FAILED", "Could not save roster.", "OK")
    def load_roster_action(self):
        rn = self.roster_combo.get()
        if not rn or rn == "Select Roster...": return
        p = self.get_roster_path(rn)
        if os.path.exists(p):
            self.is_updating = True
            try: ld = read_json(p)
            except: self.is_updating = False; CustomWarning(self, "LOAD FAILED", "Invalid JSON.", "OK"); return
            ps = ld if isinstance(ld, list) else ld.get("players", [])
            tn = {} if isinstance(ld, list) else ld.get("team_names", {})
            for i in range(10):
                row = ps[i] if i < len(ps) else {}; n = str(row.get("name", "")).strip(); pts = str(row.get("pts", "5")).strip() or "5"
                self.player_vars[i].set(n if n else PLACEHOLDER); self.points_vars[i].set(pts); self.player_entries[i].configure(text_color="#2ecc71" if n else "white")
            self.is_updating = False; self.t1_name_entry.delete(0, 'end'); self.t2_name_entry.delete(0, 'end')
            if str(tn.get("team_1", "")).strip(): self.t1_name_entry.insert(0, str(tn.get("team_1", "")).strip())
            if str(tn.get("team_2", "")).strip(): self.t2_name_entry.insert(0, str(tn.get("team_2", "")).strip())
            self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper()); self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper()); CustomInfo(self, "Roster Loaded Successfully", "#3498db")
    def get_saved_rosters(self):
        if not os.path.exists(SAVES_DIR): return []
        return sorted([f.replace(".json", "") for f in os.listdir(SAVES_DIR) if f.endswith(".json")], key=str.casefold)
    def send_to_discord(self):
        if not self.webhook_url: CustomWarning(self, "CONFIG MISSING", "No Webhook!", "OK"); return
        if not self.t1_list.cget("text") and not self.t2_list.cget("text"): CustomWarning(self, "NO TEAMS", "Generate teams first!", "OK"); return
        try:
            self.update(); img = ImageGrab.grab(bbox=(self.result_container.winfo_rootx(), self.result_container.winfo_rooty(), self.result_container.winfo_rootx() + self.result_container.winfo_width(), self.result_container.winfo_rooty() + self.result_container.winfo_height()))
            buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
            requests.post(self.webhook_url, files={"file": ("teams.png", buf, "image/png")}, data={"content": "**Balanced Teams**"}, timeout=REQUEST_TIMEOUT).raise_for_status(); CustomInfo(self, "Teams shared to Discord!", "#5865F2")
        except Exception as e: CustomWarning(self, "DISCORD FAILED", str(e), "OK")

if __name__ == "__main__":
    try: app = TeamGeneratorApp(); app.mainloop()
    except Exception:
        with open(CRASH_LOG_PATH, "w", encoding="utf-8") as f: f.write(traceback.format_exc())
