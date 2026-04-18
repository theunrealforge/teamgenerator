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
        return os.path.dirname(sys.executable)
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
        except OSError:
            pass

    ensure_directory(APPDATA_DIR)
    return os.path.join(APPDATA_DIR, filename)

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def normalize_player_db(data):
    if not isinstance(data, dict):
        raise ValueError("Player database must be a JSON object.")

    normalized = {}
    for raw_name, raw_points in data.items():
        name = str(raw_name).strip()
        if not name:
            continue
        points = str(raw_points).strip() or "5"
        normalized[name] = points
    return normalized

def coerce_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default

    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default

def version_key(value):
    parts = []
    for part in str(value).replace("-", ".").split("."):
        if part.isdigit():
            parts.append(int(part))
        else:
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits:
                parts.append(int(digits))
    return tuple(parts) if parts else (0,)

def is_newer_version(latest, current):
    return version_key(latest) > version_key(current)

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
        
        # Auto-close logic
        self.bind("<FocusOut>", self.on_focus_out)

    def on_focus_out(self, event):
        # Delay check to see where focus went
        self.after(200, self.check_destroy)

    def check_destroy(self):
        try:
            focus = self.focus_get()
            # If focus is not in the dropdown and not in the entry that opened it, close
            if not focus or (focus != self and not str(focus).startswith(str(self))):
                if focus != self.master_app.player_entries[self.slot_idx]:
                    self.destroy()
        except: 
            try: self.destroy()
            except: pass

    def update_context(self, slot_idx, players, selected_names):
        self.slot_idx = slot_idx
        self.all_players = sorted(players, key=str.casefold)
        self.selected_names = {
            name.casefold() for name in selected_names if isinstance(name, str) and name.strip()
        }

        entry = self.master_app.player_entries[slot_idx]
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 5
        w = entry.winfo_width() + 45
        self.geometry(f"{w}x300+{x}+{y}")

    def refresh_list(self, search_term, take_focus=False):
        for widget in self.scroll.winfo_children(): widget.destroy()
        search_term = search_term.lower().strip()
        filtered = [p for p in self.all_players if search_term in p.lower()]
        
        if not filtered:
            ctk.CTkLabel(self.scroll, text="No players found", text_color="gray").pack(pady=10)
        else:
            for p in sorted(filtered):
                is_selected = p.casefold() in self.selected_names
                color = "#2ecc71" if is_selected else "white"
                btn = ctk.CTkButton(self.scroll, text=p, font=ctk.CTkFont(size=13, weight="bold" if is_selected else "normal"), 
                                    text_color=color, anchor="w", fg_color="transparent", hover_color="#252525", height=30, 
                                    command=lambda name=p: self.select_player(name))
                btn.pack(fill="x", pady=1)
        
        if take_focus:
            self.focus_set()

    def select_player(self, name):
        self.callback(name, self.slot_idx)
        self.destroy()

class TeamGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ULTIMATE TEAM GENERATOR")
        self.geometry("1050x1100")
        self.overrideredirect(True)
        self.attributes("-alpha", 0.99)
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")
        
        self.bg_frame = ctk.CTkFrame(self, fg_color="#080808", corner_radius=35, border_width=1, border_color="#1f1f1f")
        self.bg_frame.pack(fill="both", expand=True)
        self.player_vars = [ctk.StringVar(value=PLACEHOLDER) for _ in range(10)]
        self.points_vars = [ctk.StringVar(value="5") for _ in range(10)]
        self.update_status_var = ctk.StringVar(value=f"Version {APP_VERSION}")
        self.webhook_url = ""
        self.update_manifest_url = ""
        self.auto_check_updates = True
        self.player_db = {}
        self.player_entries = []
        self.dropdown_window = None
        self.is_updating = False
        self.is_checking_updates = False
        self.is_installing_update = False
        self.load_config()
        self.load_player_db()
        self.setup_ui()
        for i in range(10): self.player_vars[i].trace_add("write", lambda *args, idx=i: self.on_type_search(idx))
        self.bg_frame.bind("<Button-1>", self.start_move)
        self.bg_frame.bind("<B1-Motion>", self.do_move)
        self.after(AUTO_UPDATE_DELAY_MS, self.schedule_auto_update_check)

    def start_move(self, event): self.x, self.y = event.x, event.y
    def do_move(self, event): self.geometry(f"+{self.winfo_x() + event.x - self.x}+{self.winfo_y() + event.y - self.y}")
    def find_player_db_key(self, name):
        target = name.strip().casefold()
        if not target:
            return None
        for existing_name in self.player_db:
            if existing_name.casefold() == target:
                return existing_name
        return None

    def get_selected_names(self, exclude_idx=None):
        names = []
        for i, var in enumerate(self.player_vars):
            if i == exclude_idx:
                continue
            value = var.get().strip()
            if value and value != PLACEHOLDER:
                names.append(value)
        return names

    def close_dropdown(self):
        if self.dropdown_window and self.dropdown_window.winfo_exists():
            self.dropdown_window.destroy()
        self.dropdown_window = None

    def sync_dropdown(self, idx, search_term="", take_focus=False):
        selected_names = self.get_selected_names(exclude_idx=idx)
        should_rebuild = (
            not self.dropdown_window
            or not self.dropdown_window.winfo_exists()
            or self.dropdown_window.slot_idx != idx
        )

        if should_rebuild:
            self.close_dropdown()
            self.dropdown_window = PlayerDropdown(
                self,
                idx,
                list(self.player_db.keys()),
                selected_names,
                self.on_player_chosen,
                take_focus=take_focus,
            )
        else:
            self.dropdown_window.update_context(idx, list(self.player_db.keys()), selected_names)

        self.dropdown_window.refresh_list(search_term, take_focus=take_focus)

    def load_config(self):
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                loaded = read_json(CONFIG_PATH)
                if isinstance(loaded, dict):
                    config.update(loaded)
            except Exception:
                pass

        self.webhook_url = str(config.get("webhook_url", "")).strip()
        self.update_manifest_url = str(config.get("update_manifest_url", "")).strip()
        self.auto_check_updates = coerce_bool(config.get("auto_check_updates", True), True)

    def load_player_db(self, path=None):
        target = path if path else PLAYER_DB_PATH
        if os.path.exists(target):
            try:
                self.player_db = normalize_player_db(read_json(target))
                return True
            except Exception:
                if path is None:
                    self.player_db = {}
                return False
        if path is None:
            self.player_db = {}
        return False

    def save_player_db(self, path=None):
        target = path if path else PLAYER_DB_PATH
        try:
            write_json(target, self.player_db)
            return True
        except Exception:
            return False

    def setup_ui(self):
        self.top_section = ctk.CTkFrame(self.bg_frame, fg_color="transparent", height=60)
        self.top_section.pack(side="top", fill="x", padx=30, pady=(20, 0))
        
        # Load and display logo icon
        icon_png_path = os.path.join(BASE_DIR, "icon.png")
        if not os.path.exists(icon_png_path):
             icon_png_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        
        if os.path.exists(icon_png_path):
            try:
                from PIL import Image
                self.logo_img = ctk.CTkImage(light_image=Image.open(icon_png_path), size=(35, 35))
                # Add spacer to center logo
                ctk.CTkLabel(self.top_section, text="").pack(side="left", expand=True)
                self.logo_label = ctk.CTkLabel(self.top_section, image=self.logo_img, text="")
                self.logo_label.pack(side="left")
                ctk.CTkLabel(self.top_section, text="").pack(side="left", expand=True)
            except Exception as e:
                print(f"Icon error: {e}")

        ctk.CTkButton(self.top_section, text="✕", width=40, height=40, corner_radius=10, fg_color="#1a1a1a", text_color="gray", hover_color="#e74c3c", command=self.quit).pack(side="right")
        self.nav_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent")
        self.nav_frame.pack(pady=10)
        self.tab_buttons = {}
        for code, label in [("generator", "Team Generator"), ("database", "Player Database"), ("settings", "Settings")]:
            btn = ctk.CTkButton(self.nav_frame, text=label, width=180, height=40, corner_radius=12, fg_color="#1a1a1a", text_color="#aaaaaa", font=ctk.CTkFont(size=13, weight="bold"), command=lambda c=code: self.show_frame(c))
            btn.pack(side="left", padx=12); self.tab_buttons[code] = btn
        self.content_frame = ctk.CTkFrame(self.bg_frame, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=30, pady=(0, 30))
        self.frames = {}
        self.create_generator_ui(); self.create_database_ui(); self.create_settings_ui()
        self.show_frame("generator")

    def show_frame(self, name):
        self.close_dropdown()
        for f_name, frame in self.frames.items():
            frame.pack_forget()
            btn = self.tab_buttons.get(f_name)
            if btn: btn.configure(fg_color="#1f538d" if f_name == name else "#1a1a1a", text_color="white" if f_name == name else "#aaaaaa")
        self.frames[name].pack(fill="both", expand=True, padx=20, pady=20)
        if name == "database":
            self.refresh_db_list()

    def create_generator_ui(self):
        frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.frames["generator"] = frame
        roster_row = ctk.CTkFrame(frame, fg_color="transparent")
        roster_row.pack(fill="x", pady=(0, 15))
        roster_inner = ctk.CTkFrame(roster_row, fg_color="transparent")
        roster_inner.pack(expand=True)
        self.roster_combo = ctk.CTkComboBox(roster_inner, values=self.get_saved_rosters(), width=380, height=38, fg_color="#151515", border_color="#2a2a2a", corner_radius=10); self.roster_combo.set("Select Roster..."); self.roster_combo.pack(side="left", padx=8)
        ctk.CTkButton(roster_inner, text="LOAD", width=90, height=38, fg_color="#1f538d", corner_radius=10, command=self.load_roster_action).pack(side="left", padx=5)
        ctk.CTkButton(roster_inner, text="SAVE ROSTER", width=130, height=38, fg_color="#2a2a2a", corner_radius=10, command=self.save_roster_action).pack(side="left", padx=5)
        names_row = ctk.CTkFrame(frame, fg_color="transparent")
        names_row.pack(fill="x", pady=5)
        self.t1_name_entry = ctk.CTkEntry(names_row, placeholder_text="Team 1 Name", height=40, fg_color="#121212", border_color="#252525", corner_radius=10); self.t1_name_entry.pack(side="left", expand=True, fill="x", padx=(0, 10))
        self.t2_name_entry = ctk.CTkEntry(names_row, placeholder_text="Team 2 Name", height=40, fg_color="#121212", border_color="#252525", corner_radius=10); self.t2_name_entry.pack(side="left", expand=True, fill="x", padx=(10, 0))
        self.t1_name_entry.bind("<KeyRelease>", lambda _event: self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper()))
        self.t2_name_entry.bind("<KeyRelease>", lambda _event: self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper()))
        players_grid = ctk.CTkFrame(frame, fg_color="transparent")
        players_grid.pack(fill="both", expand=True, pady=5)
        self.player_entries = []
        for i in range(10):
            row = ctk.CTkFrame(players_grid, fg_color="transparent"); row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=str(i+1), width=35, text_color="#555555", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=5)
            entry = ctk.CTkEntry(row, textvariable=self.player_vars[i], height=35, fg_color="#111111", border_color="#222222", corner_radius=8); entry.pack(side="left", expand=True, fill="x", padx=(10, 0)); self.player_entries.append(entry)
            ctk.CTkButton(row, text="▼", width=35, height=35, corner_radius=8, fg_color="#1a1a1a", border_width=1, border_color="#222222", hover_color="#252525", command=lambda idx=i: self.toggle_dropdown(idx)).pack(side="left", padx=(5, 10))
            entry.bind("<Button-1>", lambda e, idx=i: self.handle_entry_click(e, idx))
            ctk.CTkComboBox(row, values=[str(x) for x in range(1, 11)], variable=self.points_vars[i], width=90, height=35, fg_color="#111111", border_color="#222222", corner_radius=8, command=lambda val, idx=i: self.check_player_locks(val, idx)).pack(side="right", padx=5)
        act_row = ctk.CTkFrame(frame, fg_color="transparent"); act_row.pack(pady=10, fill="x")
        act_inner = ctk.CTkFrame(act_row, fg_color="transparent"); act_inner.pack(expand=True)
        ctk.CTkButton(act_inner, text="GENERATE TEAMS", font=ctk.CTkFont(size=16, weight="bold"), width=250, height=55, corner_radius=15, fg_color="#1f538d", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(act_inner, text="REFRESH", width=120, height=55, corner_radius=15, fg_color="#2a2a2a", command=self.generate_teams).pack(side="left", padx=10)
        ctk.CTkButton(act_inner, text="DELETE TEAMS", width=120, height=55, corner_radius=15, fg_color="#c0392b", command=self.delete_teams).pack(side="left", padx=10)
        ctk.CTkButton(act_inner, text="DISCORD", width=120, height=55, corner_radius=15, fg_color="#5865F2", command=self.send_to_discord).pack(side="left", padx=10)
        self.result_container = ctk.CTkFrame(frame, fg_color="#050505", corner_radius=30, border_width=1, border_color="#1f1f1f", height=420); self.result_container.pack(fill="x", pady=(5, 0)); self.result_container.pack_propagate(False)
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
        val = self.player_vars[idx].get().strip()
        
        # Case-insensitive match for auto-fill recognition
        db_match = self.find_player_db_key(val)
        
        if db_match:
            self.player_entries[idx].configure(text_color="#2ecc71")
            self.points_vars[idx].set(self.player_db[db_match])
        else:
            self.player_entries[idx].configure(text_color="white")
        
        if val == PLACEHOLDER or val == "": 
            if self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx:
                self.close_dropdown()
            return
            
        # Show suggestions while typing (WITHOUT focus theft)
        self.sync_dropdown(idx, val, take_focus=False)

    def handle_entry_click(self, event, idx):
        width = self.player_entries[idx].winfo_width()
        # "half right from middle" and "left from middle" 
        # Logic: Click anywhere except the very center 10% opens dropdown
        is_center = (width * 0.45 < event.x < width * 0.55)
        
        if self.player_vars[idx].get() == PLACEHOLDER: 
            self.player_vars[idx].set("")
            self.player_entries[idx].configure(text_color="white")
        
        # If click is on the sides, open dropdown suggestions
        if not is_center:
            current_val = self.player_vars[idx].get().strip()
            self.sync_dropdown(idx, "" if current_val == PLACEHOLDER else current_val, take_focus=False)

    def toggle_dropdown(self, idx, take_focus=True):
        same_dropdown = self.dropdown_window and self.dropdown_window.winfo_exists() and self.dropdown_window.slot_idx == idx
        if same_dropdown:
            self.close_dropdown()
        else:
            current_val = self.player_vars[idx].get().strip()
            self.sync_dropdown(idx, "" if current_val == PLACEHOLDER else current_val, take_focus=take_focus)

    def on_player_chosen(self, name, idx):
        # Prevent duplicates
        for i, var in enumerate(self.player_vars):
            if i != idx and var.get().strip().casefold() == name.casefold():
                CustomWarning(self, "SYSTEM ERROR", f"{name} is already chosen!", "DISMISS THREAT")
                return
        
        self.is_updating = True
        self.player_vars[idx].set(name)
        self.player_entries[idx].configure(text_color="#2ecc71")
        if name in self.player_db:
            self.points_vars[idx].set(self.player_db[name])
        self.is_updating = False
        self.close_dropdown()

    def delete_teams(self):
        self.t1_list.configure(text=""); self.t2_list.configure(text="")
        self.t1_total_label.configure(text=""); self.t2_total_label.configure(text="")

    def check_player_locks(self, val, idx):
        name = self.player_vars[idx].get().strip()
        db_match = self.find_player_db_key(name)
        if name and name != PLACEHOLDER and db_match:
            self.player_db[db_match] = val
            self.save_player_db()


    def create_database_ui(self):
        frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.frames["database"] = frame
        add_frame = ctk.CTkFrame(frame, fg_color="#121212", corner_radius=15, border_width=1, border_color="#1f1f1f"); add_frame.pack(fill="x", pady=15, padx=10)
        ctk.CTkLabel(add_frame, text="NAME:").pack(side="left", padx=15); self.db_name_input = ctk.CTkEntry(add_frame, width=320, height=35, fg_color="#0a0a0a", border_color="#252525"); self.db_name_input.pack(side="left", padx=5, pady=15)
        ctk.CTkLabel(add_frame, text="POINTS:").pack(side="left", padx=15); self.db_pts_input = ctk.CTkComboBox(add_frame, values=[str(x) for x in range(1, 11)], width=90, height=35, fg_color="#0a0a0a"); self.db_pts_input.pack(side="left", padx=5)
        ctk.CTkButton(add_frame, text="ADD / UPDATE", width=140, height=35, corner_radius=8, fg_color="#1f538d", command=self.db_add_player).pack(side="right", padx=15)
        manage_row = ctk.CTkFrame(frame, fg_color="transparent"); manage_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(manage_row, text="LOAD DATABASE", width=150, fg_color="#2ecc71", text_color="black", font=ctk.CTkFont(weight="bold"), command=self.load_external_db).pack(side="left", padx=5)
        ctk.CTkButton(manage_row, text="SAVE DATABASE AS", width=150, fg_color="#3498db", text_color="black", font=ctk.CTkFont(weight="bold"), command=self.save_db_as).pack(side="left", padx=5)
        ctk.CTkButton(manage_row, text="NEW DATABASE", width=150, fg_color="#333333", command=self.new_database).pack(side="left", padx=5)
        ctk.CTkButton(manage_row, text="DELETE ACTIVE", width=150, fg_color="#c0392b", command=self.delete_database).pack(side="left", padx=5)
        self.db_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent"); self.db_scroll.pack(fill="both", expand=True, pady=10); self.refresh_db_list()

    def load_external_db(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            if self.load_player_db(path):
                self.save_player_db()
                self.refresh_db_list()
                CustomInfo(self, "Database Loaded Successfully", "#2ecc71")
            else:
                CustomWarning(self, "LOAD FAILED", "That database file could not be read.", "DISMISS THREAT")

    def save_db_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path: self.save_player_db(path); CustomInfo(self, "Database Saved Successfully", "#3498db")

    def new_database(self):
        if messagebox.askyesno("NEW", "Create fresh empty list?"): self.player_db = {}; self.save_player_db(); self.refresh_db_list()

    def delete_database(self):
        if messagebox.askyesno("CONFIRM", "Proceed?"): self.player_db = {}; self.save_player_db(); self.refresh_db_list()

    def db_add_player(self):
        name, pts = self.db_name_input.get().strip(), self.db_pts_input.get()
        if name:
            existing_name = self.find_player_db_key(name)
            if existing_name and existing_name != name:
                del self.player_db[existing_name]
            self.player_db[name] = pts
            self.save_player_db()
            self.refresh_db_list()
            self.db_name_input.delete(0, 'end')

    def refresh_db_list(self):
        for widget in self.db_scroll.winfo_children(): widget.destroy()
        for name, pts in sorted(self.player_db.items(), key=lambda item: item[0].casefold()):
            row = ctk.CTkFrame(self.db_scroll, fg_color="#121212", corner_radius=10); row.pack(fill="x", pady=4, padx=5)
            lbl = ctk.CTkLabel(row, text=name, width=250, anchor="w", text_color="#ecf0f1", font=ctk.CTkFont(size=14, weight="bold")); lbl.pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(row, text=f"Power: {pts}", width=120, text_color="#888888").pack(side="left")
            ctk.CTkButton(row, text="DELETE", width=80, height=30, fg_color="#c0392b", command=lambda n=name: self.delete_player(n)).pack(side="right", padx=15)

    def delete_player(self, name):
        if messagebox.askyesno("Confirm", f"Remove {name}?"):
            if name in self.player_db:
                del self.player_db[name]; self.save_player_db(); self.refresh_db_list()

    def create_settings_ui(self):
        frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.frames["settings"] = frame
        ctk.CTkLabel(frame, text="App Settings", font=ctk.CTkFont(size=20, weight="bold"), text_color="#ecf0f1").pack(pady=(30, 12))
        ctk.CTkLabel(frame, text=f"Current version: {APP_VERSION}", font=ctk.CTkFont(size=14), text_color="#8a8a8a").pack(pady=(0, 20))
        ctk.CTkLabel(frame, text="Discord Webhook URL", font=ctk.CTkFont(size=15, weight="bold"), text_color="#5865F2").pack(pady=(0, 8))

        self.hook_input = ctk.CTkEntry(frame, width=700, height=40, placeholder_text="Paste Webhook URL...")
        self.hook_input.pack(pady=(0, 20))
        if self.webhook_url:
            self.hook_input.insert(0, self.webhook_url)

        self.auto_update_var = ctk.StringVar(value="on" if self.auto_check_updates else "off")
        ctk.CTkCheckBox(
            frame,
            text="Check for updates automatically on startup",
            variable=self.auto_update_var,
            onvalue="on",
            offvalue="off",
        ).pack(pady=(0, 18))

        ctk.CTkLabel(frame, textvariable=self.update_status_var, font=ctk.CTkFont(size=14, weight="bold"), text_color="#f1c40f").pack(pady=(0, 25))

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.pack(pady=10)
        ctk.CTkButton(button_row, text="SAVE CONFIG", width=220, height=45, corner_radius=10, fg_color="#1f538d", command=self.save_settings).pack(side="left", padx=8)
        ctk.CTkButton(button_row, text="CHECK FOR UPDATES", width=220, height=45, corner_radius=10, fg_color="#2ecc71", text_color="black", command=lambda: self.check_for_updates(silent=False)).pack(side="left", padx=8)

    def save_settings(self):
        self.webhook_url = self.hook_input.get().strip()
        self.auto_check_updates = self.auto_update_var.get() == "on"

        try:
            write_json(
                CONFIG_PATH,
                {
                    "webhook_url": self.webhook_url,
                    "update_manifest_url": self.update_manifest_url,
                    "auto_check_updates": self.auto_check_updates,
                },
            )
            self.update_status_var.set(f"Version {APP_VERSION}")
            CustomInfo(self, "Settings Saved Successfully", "#3498db")
        except Exception:
            CustomWarning(self, "SAVE FAILED", "Could not save config.json.", "DISMISS THREAT")

    def schedule_auto_update_check(self):
        if self.auto_check_updates and self.get_manifest_source():
            self.check_for_updates(silent=True)

    def get_manifest_source(self):
        return self.update_manifest_url

    def set_update_status(self, message):
        self.update_status_var.set(message)

    def check_for_updates(self, silent=False):
        if self.is_checking_updates or self.is_installing_update:
            return

        manifest_source = self.get_manifest_source()
        if not manifest_source:
            self.set_update_status(f"Version {APP_VERSION}")
            if not silent:
                CustomWarning(self, "UPDATE CONFIG", "Add an update manifest URL first.", "DISMISS THREAT")
            return

        self.is_checking_updates = True
        self.set_update_status("Checking for updates...")
        threading.Thread(
            target=self._check_for_updates_worker,
            args=(manifest_source, silent),
            daemon=True,
        ).start()

    def _check_for_updates_worker(self, manifest_source, silent):
        try:
            manifest = self.load_update_manifest(manifest_source)
            latest_version = manifest["version"]
            if not is_newer_version(latest_version, APP_VERSION):
                self.after(0, lambda: self.finish_update_check(f"Already up to date ({APP_VERSION}).", silent, is_error=False))
                return
            self.after(0, lambda: self.handle_available_update(manifest, silent))
        except Exception as exc:
            self.after(0, lambda: self.finish_update_check(f"Update check failed: {exc}", silent, is_error=True))

    def finish_update_check(self, message, silent, is_error=False):
        self.is_checking_updates = False
        self.set_update_status(message)
        if silent:
            return
        if is_error:
            CustomWarning(self, "UPDATE ERROR", message, "DISMISS THREAT")
        else:
            CustomInfo(self, message, "#2ecc71")

    def load_update_manifest(self, manifest_source):
        source = manifest_source.strip()
        if is_remote_url(source):
            response = requests.get(source, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        else:
            manifest_path = source
            if not os.path.isabs(manifest_path):
                manifest_path = os.path.join(BASE_DIR, manifest_path)
            data = read_json(manifest_path)
            source = manifest_path

        if not isinstance(data, dict):
            raise ValueError("Update manifest must be a JSON object.")

        version = str(data.get("version", "")).strip()
        download_url = str(data.get("url", "")).strip()
        notes = str(data.get("notes", "")).strip()
        if not version or not download_url:
            raise ValueError("Update manifest must include version and url.")

        return {
            "version": version,
            "url": download_url,
            "notes": notes,
            "source": source,
        }

    def resolve_update_asset_source(self, manifest):
        asset_source = manifest["url"]
        manifest_source = manifest["source"]
        if is_remote_url(asset_source) or os.path.isabs(asset_source):
            return asset_source
        if is_remote_url(manifest_source):
            return urljoin(manifest_source, asset_source)
        return os.path.join(os.path.dirname(manifest_source), asset_source)

    def handle_available_update(self, manifest, silent):
        self.is_checking_updates = False
        version = manifest["version"]
        notes = manifest.get("notes", "")

        if not getattr(sys, "frozen", False):
            message = (
                f"Update {version} is available.\n\n"
                "Automatic install works from TeamGenerator.exe builds.\n"
                "Run the packaged app to test the full updater."
            )
            self.set_update_status(f"Update {version} is available.")
            if not silent:
                CustomInfo(self, message, "#2ecc71")
            return

        message = f"Version {version} is available."
        if notes:
            message = f"{message}\n\nRelease notes:\n{notes}"
        message = f"{message}\n\nDownload and install now?"

        self.set_update_status(f"Update {version} is available.")
        if messagebox.askyesno("Update Available", message):
            self.install_update(manifest)

    def install_update(self, manifest):
        if self.is_installing_update:
            return

        self.is_installing_update = True
        self.set_update_status(f"Downloading update {manifest['version']}...")
        threading.Thread(
            target=self._install_update_worker,
            args=(manifest,),
            daemon=True,
        ).start()

    def _install_update_worker(self, manifest):
        work_dir = tempfile.mkdtemp(prefix="teamgenerator_update_")
        try:
            asset_source = self.resolve_update_asset_source(manifest)
            downloaded_exe = self.download_update_asset(asset_source, work_dir)
            script_path = self.create_update_script(downloaded_exe, work_dir)
            self.after(0, lambda: self.launch_update_script(script_path, manifest["version"]))
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            self.after(0, lambda: self.fail_update_install(str(exc)))

    def download_update_asset(self, asset_source, work_dir):
        if is_remote_url(asset_source):
            parsed = urlparse(asset_source)
            file_name = os.path.basename(parsed.path) or "TeamGenerator.exe"
            target_path = os.path.join(work_dir, file_name)
            with requests.get(asset_source, stream=True, timeout=REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                with open(target_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file.write(chunk)
            return target_path

        source_path = asset_source
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Update file not found: {source_path}")

        file_name = os.path.basename(source_path) or "TeamGenerator.exe"
        target_path = os.path.join(work_dir, file_name)
        shutil.copy2(source_path, target_path)
        return target_path

    def create_update_script(self, downloaded_exe, work_dir):
        script_path = os.path.join(tempfile.gettempdir(), f"teamgenerator_apply_update_{os.getpid()}.bat")
        script = (
            "@echo off\n"
            "setlocal enableextensions\n"
            f'set "SOURCE={downloaded_exe}"\n'
            f'set "TARGET={sys.executable}"\n'
            ":retry\n"
            'copy /Y "%SOURCE%" "%TARGET%" >nul 2>&1\n'
            "if errorlevel 1 (\n"
            "  timeout /t 1 /nobreak >nul\n"
            "  goto retry\n"
            ")\n"
            'start "" "%TARGET%"\n'
            f'rmdir /S /Q "{work_dir}" >nul 2>&1\n'
            'del "%~f0"\n'
        )
        with open(script_path, "w", encoding="utf-8", newline="\r\n") as file:
            file.write(script)
        return script_path

    def launch_update_script(self, script_path, version):
        try:
            subprocess.Popen(
                ["cmd", "/c", script_path],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self.fail_update_install(str(exc))
            return

        self.set_update_status(f"Installing update {version}...")
        messagebox.showinfo("Installing Update", f"The app will close to install version {version}.")
        self.destroy()

    def fail_update_install(self, message):
        self.is_installing_update = False
        self.set_update_status(f"Update install failed: {message}")
        CustomWarning(self, "UPDATE FAILED", message, "DISMISS THREAT")

    def generate_teams(self):
        try:
            players = []
            seen_names = set()
            for i in range(10):
                name = self.player_vars[i].get().strip()
                if not name or name == PLACEHOLDER:
                    continue

                name_key = name.casefold()
                if name_key in seen_names:
                    raise ValueError(f"{name} is entered more than once.")
                seen_names.add(name_key)
                players.append({"name": name, "points": int(self.points_vars[i].get())})

            if len(players) < 2:
                CustomWarning(self, "NOT ENOUGH PLAYERS", "Add at least two players first.", "DISMISS THREAT")
                return

            best_diff, best_split = float('inf'), ([], [])
            random_players = players[:]
            random.shuffle(random_players)
            for combo in itertools.combinations(random_players, len(players)//2):
                t1, t2 = list(combo), [p for p in random_players if p not in combo]
                diff = abs(sum(p['points'] for p in t1) - sum(p['points'] for p in t2))
                if diff < best_diff:
                    best_diff, best_split = diff, (t1, t2)
                if diff == 0:
                    break

            self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper())
            self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper())
            self.t1_list.configure(text="\n".join([p['name'] for p in best_split[0]]))
            self.t2_list.configure(text="\n".join([p['name'] for p in best_split[1]]))
            self.t1_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[0])}")
            self.t2_total_label.configure(text=f"Total Points: {sum(p['points'] for p in best_split[1])}")
        except Exception as e:
            CustomWarning(self, "SYSTEM ERROR", str(e), "DISMISS THREAT")

    def get_roster_path(self, roster_name):
        clean_name = roster_name.strip()
        if not clean_name:
            raise ValueError("Roster name cannot be empty.")
        if not clean_name.lower().endswith(".json"):
            clean_name = f"{clean_name}.json"
        return os.path.join(SAVES_DIR, os.path.basename(clean_name))

    def save_roster_action(self):
        name = filedialog.asksaveasfilename(initialdir=SAVES_DIR, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if name:
            target = self.get_roster_path(os.path.basename(name))
            data = {
                "team_names": {
                    "team_1": self.t1_name_entry.get().strip(),
                    "team_2": self.t2_name_entry.get().strip(),
                },
                "players": [
                    {
                        "name": self.player_vars[i].get().strip() if self.player_vars[i].get().strip() != PLACEHOLDER else "",
                        "pts": self.points_vars[i].get(),
                    }
                    for i in range(10)
                ],
            }
            try:
                write_json(target, data)
                self.roster_combo.configure(values=self.get_saved_rosters())
                self.roster_combo.set(os.path.splitext(os.path.basename(target))[0])
                CustomInfo(self, "Roster Saved Successfully", "#2ecc71")
            except Exception:
                CustomWarning(self, "SAVE FAILED", "Could not save that roster.", "DISMISS THREAT")

    def load_roster_action(self):
        r_name = self.roster_combo.get()
        if not r_name or r_name == "Select Roster...": return
        path = self.get_roster_path(r_name)
        if os.path.exists(path):
            self.is_updating = True
            try:
                loaded = read_json(path)
            except Exception:
                self.is_updating = False
                CustomWarning(self, "LOAD FAILED", "That roster file is not valid JSON.", "DISMISS THREAT")
                return
            if isinstance(loaded, list):
                players = loaded
                team_names = {}
            else:
                players = loaded.get("players", [])
                team_names = loaded.get("team_names", {})

            for i in range(10):
                row = players[i] if i < len(players) else {}
                n = str(row.get("name", "")).strip()
                pts = str(row.get("pts", "5")).strip() or "5"
                self.player_vars[i].set(n if n else PLACEHOLDER)
                self.points_vars[i].set(pts)
                self.player_entries[i].configure(text_color="#2ecc71" if n else "white")

            self.is_updating = False

            self.t1_name_entry.delete(0, 'end')
            self.t2_name_entry.delete(0, 'end')
            if str(team_names.get("team_1", "")).strip():
                self.t1_name_entry.insert(0, str(team_names.get("team_1", "")).strip())
            if str(team_names.get("team_2", "")).strip():
                self.t2_name_entry.insert(0, str(team_names.get("team_2", "")).strip())
            self.t1_title.configure(text=(self.t1_name_entry.get().strip() or "TEAM 1").upper())
            self.t2_title.configure(text=(self.t2_name_entry.get().strip() or "TEAM 2").upper())
            CustomInfo(self, "Roster Loaded Successfully", "#3498db")

    def get_saved_rosters(self):
        if not os.path.exists(SAVES_DIR):
            return []
        return sorted([f.replace(".json", "") for f in os.listdir(SAVES_DIR) if f.endswith(".json")], key=str.casefold)

    def send_to_discord(self):
        if not self.webhook_url:
            CustomWarning(self, "CONFIG MISSING", "No Webhook!", "DISMISS THREAT")
            return
        if not self.t1_list.cget("text") and not self.t2_list.cget("text"):
            CustomWarning(self, "NO TEAMS", "Generate teams before sharing them!", "DISMISS THREAT")
            return
        try:
            self.update()
            img = ImageGrab.grab(
                bbox=(
                    self.result_container.winfo_rootx(),
                    self.result_container.winfo_rooty(),
                    self.result_container.winfo_rootx() + self.result_container.winfo_width(),
                    self.result_container.winfo_rooty() + self.result_container.winfo_height(),
                )
            )
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            response = requests.post(
                self.webhook_url,
                files={"file": ("teams.png", buf, "image/png")},
                data={"content": "**Balanced Teams**"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            CustomInfo(self, "Teams shared to Discord!", "#5865F2")
        except Exception as exc:
            CustomWarning(self, "DISCORD FAILED", str(exc), "DISMISS THREAT")

if __name__ == "__main__":
    try: app = TeamGeneratorApp(); app.mainloop()
    except Exception:
        with open(CRASH_LOG_PATH, "w", encoding="utf-8") as f: f.write(traceback.format_exc())
