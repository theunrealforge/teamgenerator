import customtkinter as ctk
import json
import os
import requests
import time
from PIL import ImageGrab, Image
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
import ctypes

# Windows Taskbar Icon Fix
if sys.platform == "win32":
    try:
        myappid = "theunrealforge.teamgenerator.final.v1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass

# Set appearances
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# UI THEME COLORS (Theme-aware tuples: (Light, Dark))
COLOR_BG = ("#f2f2f7", "#0f0f11")
COLOR_CARD = ("#ffffff", "#18181b")
COLOR_CARD_INNER = ("#f9f9fb", "#0a0a0c")
COLOR_PURPLE = "#7146e2"
COLOR_PURPLE_HOVER = "#5b38b6"
COLOR_GRAY_DARK = ("#e5e7eb", "#27272a")
COLOR_GRAY_HOVER = ("#d1d5db", "#3f3f46")
COLOR_TEXT_MAIN = ("#111827", "#ffffff")
COLOR_TEXT_DIM = ("#6b7280", "#a1a1aa")
COLOR_BORDER = ("#d1d5db", "#1f1f23")
COLOR_RED = ("#ef4444", "#ef4444")
COLOR_RED_BTN = ("#ff5f52", "#451a1a")
COLOR_RED_BTN_HOVER = ("#cf2c27", "#7f1d1d")
COLOR_RED_BTN_TEXT = ("white", "white")
COLOR_DISCORD_BTN = ("#5865F2", "#312e81")
COLOR_DISCORD_BTN_HOVER = ("#4752c4", "#1e1b4b")
COLOR_DISCORD_BTN_TEXT = ("white", "white")
COLOR_TEAM1 = "#3b82f6"
COLOR_TEAM2 = "#ef4444"

# APP CONSTANTS
APP_NAME = "TeamGenerator"
APP_VERSION = "1.0.1"
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

class PlayerDropdown(ctk.CTkToplevel):
    def __init__(self, master, slot_idx, players, selected_names, callback, take_focus=False):
        super().__init__(master)
        self.master_app, self.slot_idx, self.callback = master, slot_idx, callback
        self.overrideredirect(True); self.attributes("-topmost", True); self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
        mf = ctk.CTkFrame(self, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER, corner_radius=15); mf.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(mf, fg_color="transparent", corner_radius=15); self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.all_players = sorted(players, key=str.casefold); self.selected_names = {n.casefold() for n in selected_names if isinstance(n, str) and n.strip()}
        entry = self.master_app.player_entries[slot_idx]
        self.geometry(f"{entry.winfo_width()+100}x300+{entry.winfo_rootx()}+{entry.winfo_rooty()+entry.winfo_height()+5}")
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
                ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(size=13, weight="bold" if sel else "normal"), text_color="#2ecc71" if sel else COLOR_TEXT_MAIN, anchor="w", fg_color="transparent", hover_color=COLOR_GRAY_HOVER, height=30, command=lambda n=p: (self.callback(n, self.slot_idx), self.destroy())).pack(fill="x", pady=1)

class TeamGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ULTIMATE TEAM GENERATOR"); self.geometry("1050x1100"); self.overrideredirect(True)
        self.wm_attributes("-transparentcolor", "#000001"); self.configure(fg_color="#000001")
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

        self.bg_frame = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=35, border_width=1, border_color=COLOR_BORDER); self.bg_frame.pack(fill="both", expand=True)
        self.player_vars = [ctk.StringVar(value=PLACEHOLDER) for _ in range(10)]
        self.points_vars = [ctk.StringVar(value="5") for _ in range(10)]
        self.update_status_var = ctk.StringVar(value=f"Version {APP_VERSION}")
        self.webhook_url, self.active_db_name, self.auto_check_updates = "", "default", True
        self.player_entries, self.dropdown_btns, self.dropdown_window = [], [], None
        self.is_updating, self.is_checking_updates, self.is_installing_update = False, False, False

        # Load Icons (Support Light/Dark)
        self.icons = {}
        icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        for icon_name in ["discord", "save", "load", "refresh", "trash", "generate"]:
            p_w, p_b = os.path.join(icon_dir, f"{icon_name}.png"), os.path.join(icon_dir, f"{icon_name}_b.png")
            if os.path.exists(p_w) and os.path.exists(p_b):
                try:
                    from PIL import Image
                    self.icons[icon_name] = ctk.CTkImage(light_image=Image.open(p_b), dark_image=Image.open(p_w), size=(18, 18))
                except: pass

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
        ts = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=70); ts.pack(fill="x", padx=35, pady=(25, 0))
        if os.path.exists(ICON_PNG_PATH):
            try:
                from PIL import Image
                self.logo_img = ctk.CTkImage(light_image=Image.open(ICON_PNG_PATH), size=(40, 40))
                ctk.CTkLabel(ts, image=self.logo_img, text="").pack(side="left", padx=(0, 10))
            except: pass
        ctk.CTkLabel(ts, text="TEAM GENERATOR", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        ctk.CTkButton(ts, text="✕", width=45, height=45, corner_radius=12, fg_color=COLOR_GRAY_DARK, text_color=COLOR_TEXT_MAIN, hover_color=COLOR_RED, font=ctk.CTkFont(size=18), command=self.quit).pack(side="right")
        
        self.nav_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.nav_frame.pack(pady=(10, 20))
        self.tab_buttons = {}
        for code, label in [("generator", "GENERATOR"), ("database", "DATABASE"), ("settings", "SETTINGS")]:
            btn = ctk.CTkButton(self.nav_frame, text=label, width=170, height=48, corner_radius=12, fg_color=COLOR_GRAY_DARK, text_color=COLOR_TEXT_DIM, font=ctk.CTkFont(size=13, weight="bold"), command=lambda c=code: self.show_frame(c))
            btn.pack(side="left", padx=10); self.tab_buttons[code] = btn
        self.content_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent"); self.content_frame.pack(fill="both", expand=True, padx=45, pady=(0, 30))
        self.frames = {}; self.create_generator_ui(); self.create_database_ui(); self.create_settings_ui(); self.show_frame("generator")

    def show_frame(self, name):
        if self.dropdown_window: self.dropdown_window.destroy()
        for n, f in self.frames.items():
            f.pack_forget()
            btn = self.tab_buttons.get(n)
            if btn: btn.configure(fg_color=COLOR_PURPLE if n == name else COLOR_GRAY_DARK, text_color="white" if n == name else COLOR_TEXT_DIM)
        self.frames[name].pack(fill="both", expand=True)
        if name == "database": self.refresh_db_list()

    def update_points(self, val, idx):
        n = self.player_vars[idx].get().strip()
        for k in list(self.player_db.keys()):
            if k.casefold() == n.casefold(): self.player_db[k] = val; self.save_active_db(); break

    def create_generator_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["generator"] = f
        
        # 1. ROSTER SECTION
        r_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        r_card.pack(fill="x", pady=(0, 10))
        ri = ctk.CTkFrame(r_card, fg_color="transparent"); ri.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(ri, text="👥  ROSTER", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 5))
        
        r_row = ctk.CTkFrame(ri, fg_color="transparent"); r_row.pack(fill="x")
        self.roster_combo = ctk.CTkComboBox(r_row, values=self.get_saved_rosters(), height=35, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=6); self.roster_combo.set("Select Roster..."); self.roster_combo.pack(side="left", expand=True, fill="x", padx=(35, 10))
        ctk.CTkButton(r_row, text="LOAD", image=self.icons.get("load"), compound="left", width=110, height=35, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), command=self.load_roster_action).pack(side="left", padx=2)
        ctk.CTkButton(r_row, text="SAVE", image=self.icons.get("save"), compound="left", width=110, height=35, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), command=self.save_roster_action).pack(side="left", padx=2)

        # 2. PLAYERS & POINTS SECTION
        p_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        p_card.pack(fill="both", expand=True, pady=(0, 10))
        pi = ctk.CTkFrame(p_card, fg_color="transparent"); pi.pack(fill="both", expand=True, padx=15, pady=8)
        ctk.CTkLabel(pi, text="👤  PLAYERS & POINTS", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 5))
        
        n_row = ctk.CTkFrame(pi, fg_color="transparent"); n_row.pack(fill="x", pady=(0, 5))
        n_left = ctk.CTkFrame(n_row, fg_color="transparent"); n_left.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(n_left, text="Team 1 Name", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.t1_name_entry = ctk.CTkEntry(n_left, placeholder_text="Enter...", height=32, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=6); self.t1_name_entry.pack(fill="x", padx=(0, 8))
        
        n_right = ctk.CTkFrame(n_row, fg_color="transparent"); n_right.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(n_right, text="Team 2 Name", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.t2_name_entry = ctk.CTkEntry(n_right, placeholder_text="Enter...", height=32, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=6); self.t2_name_entry.pack(fill="x", padx=(8, 0))

        h_row = ctk.CTkFrame(pi, fg_color="transparent"); h_row.pack(fill="x", pady=(3, 0))
        ctk.CTkLabel(h_row, text="#", width=25, font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(h_row, text="PLAYER NAME", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_DIM).pack(side="left", padx=10)
        ctk.CTkLabel(h_row, text="POINTS", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_DIM).pack(side="right", padx=75)

        self.player_entries, self.dropdown_btns = [], []
        for i in range(10):
            r = ctk.CTkFrame(pi, fg_color="transparent"); r.pack(fill="x", pady=0)
            ctk.CTkLabel(r, text=str(i+1), width=25, text_color=COLOR_TEXT_DIM, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
            
            # Integrated Slot: Left for typing, right area for dropdown
            e = ctk.CTkEntry(r, textvariable=self.player_vars[i], height=26, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=5); e.pack(side="left", expand=True, fill="x", padx=(10, 0)); self.player_entries.append(e)
            e.bind("<Button-1>", lambda ev, idx=i: self.handle_entry_click(ev, idx))
            
            # Dropdown Icon Overlay/Button (turns green when player found)
            db = ctk.CTkButton(r, text="▼", width=30, height=26, corner_radius=5, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, command=lambda idx=i: self.sync_dropdown(idx, "", False))
            db.pack(side="left", padx=4); self.dropdown_btns.append(db)
            
            ctk.CTkComboBox(r, values=[str(x) for x in range(1, 11)], variable=self.points_vars[i], width=75, height=26, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=5, command=lambda v, idx=i: self.update_points(v, idx)).pack(side="left", padx=4)
            ctk.CTkButton(r, text="", image=self.icons.get("trash"), width=30, height=26, corner_radius=5, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_RED, command=lambda idx=i: self.clear_slot(idx)).pack(side="left")

        # 3. ACTIONS SECTION
        a_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        a_card.pack(fill="x", pady=(0, 10))
        ai = ctk.CTkFrame(a_card, fg_color="transparent"); ai.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(ai, text="⚡  ACTIONS", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 5))
        a_row = ctk.CTkFrame(ai, fg_color="transparent"); a_row.pack()
        ctk.CTkButton(a_row, text="GENERATE", image=self.icons.get("generate"), compound="left", font=ctk.CTkFont(size=12, weight="bold"), width=150, height=42, corner_radius=10, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, command=self.generate_teams).pack(side="left", padx=2)
        ctk.CTkButton(a_row, text="REFRESH", image=self.icons.get("refresh"), compound="left", width=130, height=42, corner_radius=10, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, font=ctk.CTkFont(weight="bold"), command=self.generate_teams).pack(side="left", padx=2)
        ctk.CTkButton(a_row, text="DELETE", image=self.icons.get("trash"), compound="left", width=130, height=42, corner_radius=10, fg_color=COLOR_RED_BTN, hover_color=COLOR_RED_BTN_HOVER, text_color=COLOR_RED_BTN_TEXT, font=ctk.CTkFont(weight="bold"), command=self.delete_teams).pack(side="left", padx=2)
        ctk.CTkButton(a_row, text="DISCORD", image=self.icons.get("discord"), compound="left", width=130, height=42, corner_radius=10, fg_color=COLOR_DISCORD_BTN, hover_color=COLOR_DISCORD_BTN_HOVER, text_color=COLOR_DISCORD_BTN_TEXT, font=ctk.CTkFont(weight="bold"), command=self.send_to_discord).pack(side="left", padx=2)

        # 4. TEAMS PREVIEW SECTION
        tp_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        tp_card.pack(fill="x", pady=(0, 10))
        tpi = ctk.CTkFrame(tp_card, fg_color="transparent"); tpi.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(tpi, text="👥  TEAMS PREVIEW", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 5))
        
        self.result_container = ctk.CTkFrame(tpi, fg_color="transparent", height=350); self.result_container.pack(fill="x")
        self.t1_box = ctk.CTkFrame(self.result_container, fg_color=COLOR_CARD_INNER, corner_radius=10, border_width=1, border_color=COLOR_BORDER); self.t1_box.place(relx=0, rely=0, relwidth=0.48, relheight=1)
        self.t2_box = ctk.CTkFrame(self.result_container, fg_color=COLOR_CARD_INNER, corner_radius=10, border_width=1, border_color=COLOR_BORDER); self.t2_box.place(relx=0.52, rely=0, relwidth=0.48, relheight=1)
        
        self.t1_empty = ctk.CTkFrame(self.t1_box, fg_color="transparent"); self.t1_empty.pack(expand=True)
        ctk.CTkLabel(self.t1_empty, text="👥", font=ctk.CTkFont(size=25), text_color=COLOR_TEXT_DIM).pack()
        ctk.CTkLabel(self.t1_empty, text="Teams will appear here", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_DIM).pack()
        self.t2_empty = ctk.CTkFrame(self.t2_box, fg_color="transparent"); self.t2_empty.pack(expand=True)
        ctk.CTkLabel(self.t2_empty, text="👥", font=ctk.CTkFont(size=25), text_color=COLOR_TEXT_DIM).pack()
        ctk.CTkLabel(self.t2_empty, text="Teams will appear here", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_DIM).pack()

        self.t1_res_frame = ctk.CTkFrame(self.t1_box, fg_color="transparent")
        ctk.CTkLabel(self.t1_res_frame, text="TEAM 1", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEAM1).pack(pady=(10, 2))
        self.t1_slots = []
        for _ in range(5):
            s = ctk.CTkLabel(self.t1_res_frame, text="", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT_MAIN, height=24)
            s.pack(fill="x", pady=0); self.t1_slots.append(s)
        self.t1_total_label = ctk.CTkLabel(self.t1_res_frame, text="", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_TEAM1)
        self.t1_total_label.pack(pady=(10, 0))

        self.t2_res_frame = ctk.CTkFrame(self.t2_box, fg_color="transparent")
        ctk.CTkLabel(self.t2_res_frame, text="TEAM 2", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEAM2).pack(pady=(10, 2))
        self.t2_slots = []
        for _ in range(5):
            s = ctk.CTkLabel(self.t2_res_frame, text="", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT_MAIN, height=24)
            s.pack(fill="x", pady=0); self.t2_slots.append(s)
        self.t2_total_label = ctk.CTkLabel(self.t2_res_frame, text="", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_TEAM2)
        self.t2_total_label.pack(pady=(10, 0))

    def clear_slot(self, idx):
        self.player_vars[idx].set(PLACEHOLDER)
        self.player_entries[idx].configure(text_color=COLOR_TEXT_MAIN)
        self.dropdown_btns[idx].configure(text_color=COLOR_TEXT_MAIN)

    def on_type_search(self, idx):
        if self.is_updating: return
        val = self.player_vars[idx].get().strip(); match = None
        for k in self.player_db:
            if k.casefold() == val.casefold(): match = k; break
        if match:
            self.player_entries[idx].configure(text_color="#2ecc71")
            self.dropdown_btns[idx].configure(text_color="#2ecc71") # Turn icon green
            self.points_vars[idx].set(self.player_db[match])
        else:
            self.player_entries[idx].configure(text_color=COLOR_TEXT_MAIN)
            self.dropdown_btns[idx].configure(text_color=COLOR_TEXT_MAIN)
        if val and val != PLACEHOLDER: self.sync_dropdown(idx, val, False)

    def handle_entry_click(self, ev, idx):
        if self.player_vars[idx].get() == PLACEHOLDER: self.player_vars[idx].set(""); self.player_entries[idx].configure(text_color=COLOR_TEXT_MAIN)
        # Clicking right side of entry opens dropdown (if within 40px of right edge)
        if ev.x > (self.player_entries[idx].winfo_width() - 40): self.sync_dropdown(idx, "", False)

    def sync_dropdown(self, idx, term, force_close):
        sel = [v.get().strip() for i, v in enumerate(self.player_vars) if i != idx and v.get().strip() != PLACEHOLDER]
        if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx:
            if not term: self.dropdown_window.destroy(); return
            self.dropdown_window.refresh(term)
        else:
            if self.dropdown_window: self.dropdown_window.destroy()
            self.dropdown_window = PlayerDropdown(self, idx, list(self.player_db.keys()), sel, self.on_player_chosen); self.dropdown_window.refresh(term)

    def on_player_chosen(self, n, idx):
        if any(v.get().strip().casefold() == n.casefold() for i, v in enumerate(self.player_vars) if i != idx):
            messagebox.showwarning("Already Selected", f"Player '{n}' is already in the list.")
            return
        self.is_updating = True; self.player_vars[idx].set(n); self.player_entries[idx].configure(text_color="#2ecc71")
        self.dropdown_btns[idx].configure(text_color="#2ecc71") # Turn icon green
        if n in self.player_db: self.points_vars[idx].set(self.player_db[n])
        self.is_updating = False

    def create_database_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["database"] = f
        p_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); p_card.pack(fill="x", pady=(0, 15))
        pi = ctk.CTkFrame(p_card, fg_color="transparent"); pi.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(pi, text="👤  PROFILE MANAGEMENT", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 10))
        row1 = ctk.CTkFrame(pi, fg_color="transparent"); row1.pack(fill="x")
        c1 = ctk.CTkFrame(row1, fg_color="transparent"); c1.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(c1, text="Active Profile", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.db_selector = ctk.CTkComboBox(c1, values=self.get_db_list(), width=320, height=40, command=self.switch_db, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8); self.db_selector.set(self.active_db_name); self.db_selector.pack(anchor="w", padx=(0, 10))
        c2 = ctk.CTkFrame(row1, fg_color="transparent"); c2.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(c2, text="New Profile Name", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.new_profile_entry = ctk.CTkEntry(c2, placeholder_text="Enter profile name...", height=40, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8); self.new_profile_entry.pack(fill="x", padx=(10, 20))
        ctk.CTkButton(row1, text="CREATE", image=self.icons.get("save"), compound="left", width=120, height=40, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, font=ctk.CTkFont(weight="bold"), corner_radius=8, command=self.new_db_action).pack(side="left", pady=(18, 0), padx=5)
        ctk.CTkButton(row1, text="DELETE", image=self.icons.get("trash"), compound="left", width=120, height=40, fg_color=COLOR_RED_BTN, hover_color=COLOR_RED_BTN_HOVER, text_color=COLOR_RED_BTN_TEXT, font=ctk.CTkFont(weight="bold"), corner_radius=8, command=self.delete_db_action).pack(side="left", pady=(18, 0), padx=5)
        a_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); a_card.pack(fill="x", pady=(0, 15))
        ai = ctk.CTkFrame(a_card, fg_color="transparent"); ai.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(ai, text="👤+  ADD PLAYER", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 10))
        row2 = ctk.CTkFrame(ai, fg_color="transparent"); row2.pack(fill="x")
        c3 = ctk.CTkFrame(row2, fg_color="transparent"); c3.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(c3, text="Player Name", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.db_name_input = ctk.CTkEntry(c3, height=40, placeholder_text="Enter player name...", fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8); self.db_name_input.pack(fill="x", padx=(0, 20))
        c4 = ctk.CTkFrame(row2, fg_color="transparent"); c4.pack(side="left")
        ctk.CTkLabel(c4, text="Points", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        self.db_pts_input = ctk.CTkComboBox(c4, values=[str(x) for x in range(1, 11)], width=120, height=40, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8); self.db_pts_input.set("5"); self.db_pts_input.pack(padx=(0, 20))
        ctk.CTkButton(row2, text="ADD TO LIST", width=220, height=45, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, font=ctk.CTkFont(weight="bold"), corner_radius=10, command=self.db_add_player).pack(side="right", pady=(18, 0))
        d_card = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); d_card.pack(fill="x", pady=(0, 15))
        di = ctk.CTkFrame(d_card, fg_color="transparent"); di.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(di, text="🗄️  DATABASE ACTIONS", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 15))
        grid = ctk.CTkFrame(di, fg_color="transparent"); grid.pack(fill="x")
        def create_box(master, title):
            b = ctk.CTkFrame(master, fg_color=COLOR_CARD_INNER, corner_radius=10, border_width=1, border_color=COLOR_BORDER); b.pack(side="left", expand=True, fill="both", padx=8)
            ctk.CTkLabel(b, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_DIM).pack(pady=(15, 10)); return b
        g1 = create_box(grid, "IMPORT / EXPORT")
        ctk.CTkButton(g1, text="IMPORT", image=self.icons.get("load"), compound="left", width=200, height=38, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, font=ctk.CTkFont(size=12, weight="bold"), command=self.load_external_db).pack(pady=5, padx=15)
        ctk.CTkButton(g1, text="EXPORT", image=self.icons.get("save"), compound="left", width=200, height=38, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, font=ctk.CTkFont(size=12, weight="bold"), command=self.save_db_as).pack(pady=(5, 15), padx=15)
        g2 = create_box(grid, "LIST MANAGEMENT")
        ctk.CTkButton(g2, text="CLEAR LIST", image=self.icons.get("trash"), compound="left", width=200, height=42, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, font=ctk.CTkFont(size=12, weight="bold"), command=self.new_database).pack(pady=(15, 20), padx=15)
        g3 = create_box(grid, "DANGER ZONE")
        ctk.CTkButton(g3, text="WIPE PROFILE", image=self.icons.get("trash"), compound="left", width=200, height=42, fg_color=COLOR_RED_BTN, hover_color=COLOR_RED_BTN_HOVER, text_color=COLOR_RED_BTN_TEXT, font=ctk.CTkFont(size=12, weight="bold"), command=self.delete_database).pack(pady=(15, 20), padx=15)
        self.db_scroll = ctk.CTkScrollableFrame(f, fg_color=COLOR_CARD_INNER, corner_radius=15, border_width=1, border_color=COLOR_BORDER); self.db_scroll.pack(fill="both", expand=True, pady=0)
        
    def refresh_db_list(self):
        for w in self.db_scroll.winfo_children(): w.destroy()
        if not self.player_db:
            e = ctk.CTkFrame(self.db_scroll, fg_color="transparent"); e.pack(expand=True, pady=100)
            ctk.CTkLabel(e, text="👥", font=ctk.CTkFont(size=40), text_color=COLOR_BORDER[1]).pack()
            ctk.CTkLabel(e, text="No players in the list.", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT_DIM).pack(); return
        for name, pts in sorted(self.player_db.items(), key=lambda x: x[0].casefold()):
            r = ctk.CTkFrame(self.db_scroll, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_BORDER); r.pack(fill="x", pady=4, padx=15)
            ctk.CTkLabel(r, text=name, width=250, anchor="w", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left", padx=20, pady=12)
            ctk.CTkLabel(r, text=f"Power: {pts}", text_color=COLOR_TEXT_DIM, font=ctk.CTkFont(size=13)).pack(side="left")
            ctk.CTkButton(r, text="DELETE", image=self.icons.get("trash"), width=90, height=32, fg_color=COLOR_RED_BTN, hover_color=COLOR_RED_BTN_HOVER, text_color=COLOR_RED_BTN_TEXT, font=ctk.CTkFont(size=11, weight="bold"), command=lambda n=name: (self.player_db.pop(n), self.save_active_db(), self.refresh_db_list())).pack(side="right", padx=15)

    def get_db_list(self): return [f.replace(".json","") for f in os.listdir(DB_DIR) if f.endswith(".json")] or ["default"]
    def switch_db(self, name): self.active_db_name = name; self.save_config(); self.load_active_db(); self.refresh_db_list()
    def new_db_action(self):
        n = self.new_profile_entry.get().strip()
        if n: self.active_db_name = n; self.player_db = {}; self.save_active_db(); self.save_config(); self.new_profile_entry.delete(0, 'end'); self.db_selector.configure(values=self.get_db_list()); self.db_selector.set(n); self.refresh_db_list()
    def delete_db_action(self):
        if self.active_db_name != "default" and messagebox.askyesno("Confirm", f"Delete profile '{self.active_db_name}'?"):
            try: os.remove(os.path.join(DB_DIR, f"{self.active_db_name}.json"))
            except: pass
            self.active_db_name = "default"; self.save_config(); self.load_active_db(); self.db_selector.configure(values=self.get_db_list()); self.db_selector.set("default"); self.refresh_db_list()
    def db_add_player(self):
        n, pts = self.db_name_input.get().strip(), self.db_pts_input.get()
        if n:
            for k in list(self.player_db.keys()):
                if k.casefold() == n.casefold(): del self.player_db[k]
            self.player_db[n] = pts; self.save_active_db(); self.refresh_db_list(); self.db_name_input.delete(0, 'end')
    def load_external_db(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if p and self.load_active_db(p): self.save_active_db(); self.refresh_db_list()
    def save_db_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if p: write_json(p, self.player_db)
    def new_database(self):
        if messagebox.askyesno("NEW", "Clear current list?"): self.player_db = {}; self.save_active_db(); self.refresh_db_list()
    def delete_database(self):
        if messagebox.askyesno("CONFIRM", "Wipe active?"): self.player_db = {}; self.save_active_db(); self.refresh_db_list()

    def create_settings_ui(self):
        f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); self.frames["settings"] = f
        h = ctk.CTkFrame(f, fg_color="transparent"); h.pack(fill="x", pady=(10, 20))
        ctk.CTkLabel(h, text="⚙️  APPLICATION SETTINGS", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_PURPLE).pack(side="left")
        dc = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); dc.pack(fill="x", pady=(0, 15))
        idc = ctk.CTkFrame(dc, fg_color="transparent"); idc.pack(fill="x", padx=20, pady=15)
        dh = ctk.CTkFrame(idc, fg_color="transparent"); dh.pack(fill="x", pady=(0, 10))
        try:
            self.settings_discord = ctk.CTkImage(light_image=Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "discord_b.png")), dark_image=Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "discord.png")), size=(24, 24))
            ctk.CTkLabel(dh, text="", image=self.settings_discord).pack(side="left", padx=(0, 8))
        except: pass
        ctk.CTkLabel(dh, text="DISCORD INTEGRATION", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_PURPLE).pack(side="left")
        ctk.CTkLabel(idc, text="Enter your server webhook URL to share results.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM).pack(anchor="w", pady=(0, 10))
        self.hook_in = ctk.CTkEntry(idc, height=42, placeholder_text="Paste URL...", fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8); self.hook_in.pack(fill="x", pady=(0, 10)); self.hook_in.insert(0, self.webhook_url)
        ctk.CTkLabel(idc, text="ⓘ  Create a webhook in Discord settings under Integrations > Webhooks.", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(anchor="w")
        uc = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); uc.pack(fill="x", pady=(0, 15))
        iuc = ctk.CTkFrame(uc, fg_color="transparent"); iuc.pack(fill="x", padx=20, pady=15)
        self.up_v = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(iuc, text="Enable automatic version checks on startup", variable=self.up_v, onvalue="on", offvalue="off", font=ctk.CTkFont(size=12, weight="bold"), fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, border_color=COLOR_BORDER[1]).pack(side="left")
        sf = ctk.CTkFrame(iuc, fg_color="transparent"); sf.pack(side="right")
        ctk.CTkLabel(sf, textvariable=self.update_status_var, font=ctk.CTkFont(size=11, weight="bold"), text_color="#2ecc71").pack(side="left", padx=10)
        ctk.CTkButton(sf, text="CHECK", width=80, height=28, corner_radius=6, fg_color=COLOR_GRAY_DARK, hover_color=COLOR_GRAY_HOVER, text_color=COLOR_TEXT_MAIN, font=ctk.CTkFont(size=10, weight="bold"), command=lambda: self.schedule_auto_update_check()).pack(side="left")
        at = ctk.CTkFrame(f, fg_color="transparent"); at.pack(fill="x")
        ac = ctk.CTkFrame(at, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); ac.pack(side="left", expand=True, fill="both", padx=(0, 8))
        iac = ctk.CTkFrame(ac, fg_color="transparent"); iac.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(iac, text="ⓘ  ABOUT", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(iac, text=f"Version: {APP_VERSION}", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        tc = ctk.CTkFrame(at, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); tc.pack(side="left", expand=True, fill="both", padx=(8, 0))
        itc = ctk.CTkFrame(tc, fg_color="transparent"); itc.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(itc, text="🎨  THEME", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_PURPLE).pack(anchor="w", pady=(0, 5))
        self.theme_combo = ctk.CTkComboBox(itc, values=["Dark", "Light", "System"], width=140, height=35, fg_color=COLOR_CARD_INNER, border_color=COLOR_BORDER, corner_radius=8, command=lambda v: ctk.set_appearance_mode(v)); self.theme_combo.set("Dark"); self.theme_combo.pack(anchor="w")
        actc = ctk.CTkFrame(f, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER); actc.pack(fill="x", pady=(15, 0))
        iactc = ctk.CTkFrame(actc, fg_color="transparent"); iactc.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(iactc, text="SAVE CHANGES", image=self.icons.get("save"), compound="left", width=220, height=45, corner_radius=10, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_HOVER, font=ctk.CTkFont(weight="bold"), command=self.manual_save_settings).pack(side="left", padx=(0, 10))

    def manual_save_settings(self): self.webhook_url = self.hook_in.get().strip(); self.auto_check_updates = self.up_v.get() == "on"; self.save_config()
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
            self.t1_empty.pack_forget(); self.t2_empty.pack_forget()
            self.t1_res_frame.pack(expand=True, fill="both"); self.t2_res_frame.pack(expand=True, fill="both")
            for i in range(5):
                if i < len(best_split[0]): self.t1_slots[i].configure(text=best_split[0][i]['name'])
                else: self.t1_slots[i].configure(text="")
                if i < len(best_split[1]): self.t2_slots[i].configure(text=best_split[1][i]['name'])
                else: self.t2_slots[i].configure(text="")
            self.t1_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[0])}")
            self.t2_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[1])}")
        except: pass
    def delete_teams(self): self.t1_res_frame.pack_forget(); self.t2_res_frame.pack_forget(); self.t1_empty.pack(expand=True); self.t2_empty.pack(expand=True)
    def get_saved_rosters(self): return sorted([f.replace(".json", "") for f in os.listdir(SAVES_DIR) if f.endswith(".json")], key=str.casefold)
    def save_roster_action(self):
        p = filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json")
        if p: write_json(p, {"ps": [{"n": self.player_vars[i].get(), "p": self.points_vars[i].get()} for i in range(10)]}); self.roster_combo.configure(values=self.get_saved_rosters()); self.roster_combo.set(os.path.basename(p).replace(".json",""))
    def load_roster_action(self):
        rn = self.roster_combo.get()
        if rn and rn != "Select Roster...":
            d = read_json(os.path.join(SAVES_DIR, f"{rn}.json"))
            for i, p in enumerate(d.get("ps", [])):
                if i < 10: self.player_vars[i].set(p["n"]); self.points_vars[i].set(p["p"]); self.player_entries[i].configure(text_color="#2ecc71" if p["n"] and p["n"]!=PLACEHOLDER else COLOR_TEXT_MAIN); self.dropdown_btns[i].configure(text_color="#2ecc71" if p["n"] and p["n"]!=PLACEHOLDER else COLOR_TEXT_MAIN)
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
