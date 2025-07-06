# --- START OF FILE app.py ---

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, font as tkFont
import serial
import serial.tools.list_ports
import threading
import time
import pyautogui
import json
import os
import random
import math
from collections import deque

pyautogui.FAILSAFE = False
PROFILES_DIR = "input_profiles"

DEFAULT_SETTINGS = {
    # Common
    "HST": -200, "NMIN": -100, "NMAX": 25, "SPT": 100, "HPT": 200,
    "SAD": 150,
    # Joystick General
    "JDZ": 20, "JMT": 10,
    # Mouse Specific
    "CSP": 10, "OSK_ENABLED": 0,
    # NEW: Sensitivity Scaling
    "SIP_SENS": 100, "PUFF_SENS": 100,
}

# Default keybinds for keyboard mode sectors (now supports two keys via space)
DEFAULT_SECTOR_KEYS = ['d', 'd s', 's', 'a s', 'a', 'a w', 'w', 'w d']
DEFAULT_PRESSURE_KEYS = {'HPT': 'f', 'SPT': 'r', 'HST': 'e', 'SST': 'q'}


class IntegratedHybridApp:
    # Special keys mapping for Keyboard mode
    SPECIAL_KEYS = {
        'enter': 0xB0, 'esc': 0xB1, 'backspace': 0xB2, 'tab': 0xB3, 'space': 32,
        'insert': 0xD1, 'delete': 0xD4, 'right': 0xD7, 'left': 0xD8, 'down': 0xD9, 'up': 0xDA,
        'pageup': 0xD3, 'pagedown': 0xD6, 'home': 0xD2, 'end': 0xD5, 'capslock': 0xC1,
        'f1': 0xC2, 'f2': 0xC3, 'f3': 0xC4, 'f4': 0xC5, 'f5': 0xC6, 'f6': 0xC7,
        'f7': 0xC8, 'f8': 0xC9, 'f9': 0xCA, 'f10': 0xCB, 'f11': 0xCC, 'f12': 0xCD,
        'shift': 0x81, 'ctrl': 0x80, 'alt': 0x82, 'win': 0x83, # Mapped to left versions
        'lshift': 0x81, 'lctrl': 0x80, 'lalt': 0x82, 'lwin': 0x83,
        'rshift': 0x85, 'rctrl': 0x84, 'ralt': 0x86, 'rwin': 0x87,
    }

    def __init__(self, root_window):
        self.root = root_window
        self.root.geometry("1150x850") # Wider for mode selector

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        base_font_family = "Segoe UI"
        try: tkFont.Font(family=base_font_family, size=10).actual()
        except tk.TclError: base_font_family = "Arial"

        self.font_normal = ctk.CTkFont(family=base_font_family, size=12)
        self.font_small = ctk.CTkFont(family=base_font_family, size=10)
        self.font_bold = ctk.CTkFont(family=base_font_family, size=12, weight="bold")
        self.font_header = ctk.CTkFont(family=base_font_family, size=14, weight="bold")
        self.font_pressure = ctk.CTkFont(family=base_font_family, size=20, weight="bold")
        self.font_log = ctk.CTkFont(family="Courier New", size=10)
        self.font_labelframe_title = ctk.CTkFont(family=base_font_family, size=12, weight="bold")
        self.font_canvas_threshold_text = tkFont.Font(family="Arial", size=9)
        
        self.current_mode_str = "Mouse" # Python-level state tracker for mode
        self.current_mode = tk.StringVar(value=self.current_mode_str)

        self.ser = None; self.is_connected = False; self.stop_read_thread = threading.Event()
        
        self.params_tkvars = {}
        self.param_labels = {} 
        self.param_sliders = {} 
        self.param_entries = {}
        self.param_desc_labels = {}
        
        self.num_sectors_tkvar = tk.StringVar(value="8")
        self.sector_key_tkvars = [tk.StringVar(value=k) for k in DEFAULT_SECTOR_KEYS]
        self.pressure_key_tkvars = {k: tk.StringVar(value=v) for k, v in DEFAULT_PRESSURE_KEYS.items()}

        self.keyboard_sector_widgets = {}
        self.keyboard_pressure_key_widgets = {}
        
        self.osk_toggle_enabled_tkvar = tk.BooleanVar(value=False)

        for key, value in DEFAULT_SETTINGS.items():
            if key == "OSK_ENABLED":
                self.osk_toggle_enabled_tkvar.set(bool(value))
            else:
                self.params_tkvars[key] = tk.IntVar(value=value)
        
        self.current_pressure_tkvar = tk.StringVar(value="Pressure: N/A")
        self.current_profile_name = tk.StringVar(value="<Default Settings>")

        try: self.screen_width,self.screen_height=pyautogui.size()
        except Exception: self.screen_width,self.screen_height=1920,1080
        
        self.in_osk_corner = False
        self.last_osk_toggle_time = 0

        self.trainer_score_display_var=tk.StringVar(value="Score: 0"); self.trainer_score_value=0
        self.trainer_target_hits=0; self.trainer_target_misses=0; self.trainer_target_active=False
        self.trainer_target_coords=None; self.trainer_target_id=None; self.trainer_click_target_id=None
        self.trainer_click_target_text_id=None; self.trainer_click_target_button_type_expected=None
        self.trainer_scroll_font=ctk.CTkFont(family=base_font_family,size=12)
        self.trainer_content_host_frame=None
        self.trainer_active_tk_canvas = None
        self.is_target_hit_and_waiting_for_respawn=False
        self.trainer_game_mode = None
        self._trainer_loop_job_id = None
        self.TRAINER_UPDATE_INTERVAL_MS = 33
        
        self.mouse_trail_points = deque(maxlen=20) 
        self.mouse_trail_ids = []

        self.calibrating_action_name=tk.StringVar(value=""); self.calibration_samples=[]
        self.calibration_current_value_tkvar=tk.StringVar(value="Raw Pressure: ---")
        self.is_calibrating_arduino_mode=False; self.collected_calibration_data={}; self._calibration_collect_job=None
        self.pressure_history = []
        self.pressure_canvas_min_width = 450 
        self.pressure_canvas_min_height = 450 

        self.PRESSURE_VIS_MIN = -512
        self.PRESSURE_VIS_MAX = 511
        
        self.pressure_label_area_width = 70 
        self._calculate_pressure_label_area_width() 

        self.max_history_points = self.pressure_canvas_min_width - self.pressure_label_area_width 
        if self.max_history_points <=0: self.max_history_points = 1 
        
        self.joystick_x_centered_tkvar = tk.IntVar(value=0); self.joystick_y_centered_tkvar = tk.IntVar(value=0)
        self.joystick_canvas_min_width = 200; self.joystick_canvas_min_height = 200
        
        if not os.path.exists(PROFILES_DIR):
            try: os.makedirs(PROFILES_DIR)
            except OSError as e: print(f"Error creating profiles directory {PROFILES_DIR}: {e}")

        self.create_main_layout()
        self.populate_ports(); self.populate_profiles_dropdown()
        self.update_gui_for_mode()
        self.set_status("Disconnected. Select port and connect.")
        self.root.bind("<Configure>", self._on_window_resize)
        
        self._app_update_loop()


    def _calculate_pressure_label_area_width(self):
        if not hasattr(self, 'font_canvas_threshold_text') or not self.font_canvas_threshold_text:
            self.font_canvas_threshold_text = tkFont.Font(family="Arial", size=9)
        max_measured_w = 0; font_to_measure = self.font_canvas_threshold_text
        label_sample_text = f"{self.PRESSURE_VIS_MIN}"
        max_measured_w = font_to_measure.measure(label_sample_text)
        gap_to_graph_line = 5; padding_left_of_text = 3
        calculated_width = max_measured_w + gap_to_graph_line + padding_left_of_text
        self.pressure_label_area_width = max(70, int(calculated_width))

    def _on_window_resize(self, event=None):
        if hasattr(self, 'tab_view') and self.tab_view.winfo_exists():
            current_tab = self.tab_view.get()
            if current_tab == "Calibrate Sensor" and self.is_calibrating_arduino_mode:
                if hasattr(self, 'pressure_visualizer_canvas') and self.pressure_visualizer_canvas.winfo_exists():
                    w = self.pressure_visualizer_canvas.winfo_width()
                    if w > 1 : 
                        label_area_width = self.pressure_label_area_width 
                        graph_area_width = w - label_area_width
                        if graph_area_width <=0 : graph_area_width = 1 
                        if abs(self.max_history_points - graph_area_width) > 5: 
                           self.max_history_points = graph_area_width
                           if self.max_history_points <=0: self.max_history_points = 1
                    self._update_pressure_visualizer() 
            elif current_tab == "Stick Control":
                if hasattr(self, 'joystick_canvas') and self.joystick_canvas.winfo_exists():
                    self._update_joystick_visualizer()

    def _get_themed_canvas_bg(self):
        appearance_mode = ctk.get_appearance_mode()
        if appearance_mode == "Dark":
            try: return ctk.ThemeManager.theme["CTkFrame"]["fg_color"][1]
            except: return "#2B2B2B"
        else:
            try: return ctk.ThemeManager.theme["CTkFrame"]["fg_color"][0]
            except: return "#DBDBDB"

    def create_main_layout(self):
        top_bar_frame = ctk.CTkFrame(self.root, fg_color="transparent"); top_bar_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10,5))
        
        self.create_mode_switcher_widget(top_bar_frame) 
        self.create_connection_widgets(top_bar_frame)

        self.status_var = tk.StringVar()
        self.status_bar = ctk.CTkLabel(self.root, textvariable=self.status_var, font=self.font_normal, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        self.tab_view = ctk.CTkTabview(self.root, command=self.on_tab_change)
        self.tab_view.pack(expand=True, fill='both', padx=10, pady=(5,10))
        self.tab_view.add("Tuner & Profiles")
        self.tab_view.add("Trainer")
        self.tab_view.add("Calibrate Sensor")
        self.tab_view.add("Stick Control")
        
        self.create_tuner_widgets(self.tab_view.tab("Tuner & Profiles"))
        self.create_calibration_widgets(self.tab_view.tab("Calibrate Sensor"))
        self.create_joystick_control_widgets(self.tab_view.tab("Stick Control"))
        
        self.tab_view.set("Tuner & Profiles")

    def _create_labeled_frame(self, parent, title_text, **kwargs):
        fg_color_main = kwargs.pop("fg_color", None); outer_frame = ctk.CTkFrame(parent, border_width=1, fg_color=fg_color_main, **kwargs)
        title_label = ctk.CTkLabel(outer_frame, text=title_text, font=self.font_labelframe_title, anchor="w"); title_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5,2))
        content_frame = ctk.CTkFrame(outer_frame, fg_color="transparent"); content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        return outer_frame, content_frame

    def create_mode_switcher_widget(self, parent_frame):
        mode_lf_outer, mode_frame = self._create_labeled_frame(parent_frame, "Operating Mode")
        mode_lf_outer.pack(side=tk.LEFT, padx=(0,10), pady=5, fill=tk.Y) 

        self.mode_combo = ctk.CTkComboBox(mode_frame, values=["Mouse", "Keyboard"],
                                          variable=self.current_mode,
                                          command=self.on_mode_change_ui, 
                                          state="readonly", font=self.font_normal, width=120)
        self.mode_combo.pack(pady=5, padx=5, anchor="center")

    def create_connection_widgets(self, parent_frame):
        conn_lf_outer, conn_frame = self._create_labeled_frame(parent_frame, "Serial Connection")
        conn_lf_outer.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X)
        ctk.CTkLabel(conn_frame, text="Port:", font=self.font_normal).pack(side=tk.LEFT, padx=(5,0), pady=5)
        self.port_combo = ctk.CTkComboBox(conn_frame, width=180, state="readonly", font=self.font_normal); self.port_combo.pack(side=tk.LEFT, padx=5, pady=5)
        self.connect_button = ctk.CTkButton(conn_frame, text="Connect", command=self.toggle_connect, font=self.font_bold, width=100); self.connect_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.refresh_button = ctk.CTkButton(conn_frame, text="Refresh Ports", command=self.populate_ports, font=self.font_bold, width=120); self.refresh_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        pressure_lf_outer, pressure_display_frame = self._create_labeled_frame(parent_frame, "Live Pressure (Avg)")
        pressure_lf_outer.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.X, expand=True)
        self.pressure_label = ctk.CTkLabel(pressure_display_frame, textvariable=self.current_pressure_tkvar, font=self.font_pressure); self.pressure_label.pack(padx=10, pady=(3,6))

    def create_tuner_widgets(self, parent_tab):
        main_tuner_pane = ctk.CTkFrame(parent_tab, fg_color="transparent"); main_tuner_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tuner_params_lf_outer, params_content_frame = self._create_labeled_frame(main_tuner_pane, "Parameters")
        self.tuner_params_lf_outer.pack(padx=5, pady=5, fill=tk.X, side=tk.TOP)
        
        col1_frame = ctk.CTkFrame(params_content_frame, fg_color="transparent")
        col1_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        col2_frame = ctk.CTkFrame(params_content_frame, fg_color="transparent")
        col2_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        params_content_frame.columnconfigure(0, weight=1); params_content_frame.columnconfigure(1, weight=1)
        
        row_idx_col1 = 0
        self.pressure_thresholds_main_label = ctk.CTkLabel(col1_frame, text="Pressure Thresholds:", font=self.font_bold)
        self.pressure_thresholds_main_label.grid(row=row_idx_col1, column=0, columnspan=3, pady=(5,2), sticky="w", padx=5)
        
        row_idx_col1=self.create_param_slider_widget(col1_frame, "Hard Sip (HST):", self.params_tkvars["HST"], "HST", -512, 0, row_idx_col1)
        row_idx_col1=self.create_param_slider_widget(col1_frame, "Soft Sip / Neutral Min (NMIN):", self.params_tkvars["NMIN"], "NMIN", -512, 0, row_idx_col1)
        row_idx_col1=self.create_param_slider_widget(col1_frame, "Neutral Max (NMAX):", self.params_tkvars["NMAX"], "NMAX", 0, 511, row_idx_col1)
        row_idx_col1=self.create_param_slider_widget(col1_frame, "Soft Puff (SPT):", self.params_tkvars["SPT"], "SPT", 0, 511, row_idx_col1)
        row_idx_col1=self.create_param_slider_widget(col1_frame, "Hard Puff (HPT):", self.params_tkvars["HPT"], "HPT", 0, 511, row_idx_col1)
        
        row_idx_col2 = 0
        self.tuner_general_settings_label = ctk.CTkLabel(col2_frame, text="Sensitivity & General Settings:", font=self.font_bold)
        self.tuner_general_settings_label.grid(row=row_idx_col2, column=0, columnspan=3, pady=(5,2), sticky="w", padx=5)

        row_idx_col2=self.create_param_slider_widget(col2_frame, "Sip Sensitivity (%):", self.params_tkvars["SIP_SENS"], "SIP_SENS", 10, 200, row_idx_col2, desc_text_str="Lower to make sips less sensitive.")
        row_idx_col2=self.create_param_slider_widget(col2_frame, "Puff Sensitivity (%):", self.params_tkvars["PUFF_SENS"], "PUFF_SENS", 10, 200, row_idx_col2, desc_text_str="Lower to make puffs less sensitive.")
        
        ctk.CTkFrame(col2_frame, height=2, border_width=1).grid(row=row_idx_col2+1, column=0, columnspan=3, pady=10, sticky="ew")
        row_idx_col2 += 1

        row_idx_col2=self.create_param_slider_widget(col2_frame, "Soft Action Delay ms (SAD):", self.params_tkvars["SAD"], "SAD", 0, 1000, row_idx_col2, key_for_desc="SAD_TUNER_DESC")
        
        col1_frame.columnconfigure(1, weight=1); col2_frame.columnconfigure(1, weight=1)
        self.apply_button = ctk.CTkButton(params_content_frame, text="Apply All Settings to Arduino", command=self.apply_all_settings, state=tk.DISABLED, font=self.font_bold)
        self.apply_button.grid(row=max(row_idx_col1, row_idx_col2)+1, column=0, columnspan=2, pady=20, padx=5, sticky="ew") 
        
        profile_lf_outer, profile_content_frame = self._create_labeled_frame(main_tuner_pane, "Profiles")
        profile_lf_outer.pack(padx=5, pady=10, fill=tk.X, side=tk.TOP)
        self.create_profile_widgets_content(profile_content_frame)

    def create_param_slider_widget(self, parent, label_text_str, tk_var, param_key, from_, to_, row_idx, desc_text_str="", key_for_desc=None):
        self.param_labels[param_key] = ctk.CTkLabel(parent, text=label_text_str, font=self.font_normal)
        self.param_labels[param_key].grid(row=row_idx+1, column=0, padx=5, pady=(5,0), sticky="w")
        
        slider_cmd = lambda val, v=tk_var, k=param_key: self._slider_update_wrapper(val, v, k)
        
        self.param_sliders[param_key] = ctk.CTkSlider(parent, from_=from_, to=to_, variable=tk_var, width=180, command=slider_cmd)
        self.param_sliders[param_key].grid(row=row_idx+1, column=1, padx=5, pady=(5,0), sticky="ew")
        
        self.param_entries[param_key] = ctk.CTkEntry(parent, textvariable=tk_var, width=50, font=self.font_normal)
        self.param_entries[param_key].grid(row=row_idx+1, column=2, padx=5, pady=(5,0))

        current_row = row_idx + 1 
        if desc_text_str or key_for_desc:
            current_row +=1 
            try: wrap_len = parent.winfo_width() - 20 if parent.winfo_exists() and parent.winfo_width() > 20 else 200
            except: wrap_len = 200
            
            desc_label_widget = ctk.CTkLabel(parent, text=desc_text_str, font=self.font_small, text_color=("gray30", "gray70"), wraplength=wrap_len, justify=tk.LEFT, anchor="w")
            desc_label_widget.grid(row=current_row, column=0, columnspan=3, padx=15, pady=(0,5), sticky="w")
            if key_for_desc:
                 self.param_desc_labels[key_for_desc] = desc_label_widget
            
        parent.columnconfigure(1, weight=1)
        return current_row 

    def _slider_update_wrapper(self, value, tk_var_ref, param_key_ref):
        tk_var_ref.set(int(value))
        if param_key_ref in ["JDZ", "JMT", "HST", "NMIN", "NMAX", "SPT", "HPT", "SIP_SENS", "PUFF_SENS"]: 
            if hasattr(self, 'tab_view') and self.tab_view.winfo_exists():
                current_tab = self.tab_view.get()
                if current_tab == "Stick Control" and param_key_ref in ["JDZ", "JMT"]:
                    self._update_joystick_visualizer()
                elif current_tab == "Calibrate Sensor":
                    if self.is_calibrating_arduino_mode: 
                         self._update_pressure_visualizer()

    def create_profile_widgets_content(self, profile_frame):
        ctk.CTkLabel(profile_frame, text="Profile:", font=self.font_normal).grid(row=0, column=0, padx=5, pady=(5,3), sticky="w")
        self.profile_combo = ctk.CTkComboBox(profile_frame, variable=self.current_profile_name, width=250, state="readonly", font=self.font_normal)
        self.profile_combo.grid(row=0, column=1, padx=5, pady=(5,3), sticky="ew")
        profile_action_buttons_frame = ctk.CTkFrame(profile_frame, fg_color="transparent"); profile_action_buttons_frame.grid(row=0, column=2, rowspan=2, padx=(10,5), pady=3, sticky="ns")
        self.load_profile_button = ctk.CTkButton(profile_action_buttons_frame, text="Load Selected", command=self.load_selected_profile, font=self.font_bold); self.load_profile_button.pack(pady=(0,3), fill=tk.X)
        self.delete_profile_button = ctk.CTkButton(profile_action_buttons_frame, text="Delete Selected", command=self.delete_selected_profile, font=self.font_bold); self.delete_profile_button.pack(pady=3, fill=tk.X)
        save_buttons_frame = ctk.CTkFrame(profile_frame, fg_color="transparent"); save_buttons_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=(3,5), sticky="ew")
        self.save_profile_button = ctk.CTkButton(save_buttons_frame, text="Save to Selected", command=self.save_current_profile, font=self.font_bold); self.save_profile_button.pack(side=tk.LEFT, padx=(0,5), expand=True, fill=tk.X)
        self.save_as_button = ctk.CTkButton(save_buttons_frame, text="Save As New...", command=self.save_profile_as, font=self.font_bold); self.save_as_button.pack(side=tk.LEFT, padx=(5,0), expand=True, fill=tk.X)
        self.load_defaults_button = ctk.CTkButton(profile_frame, text="Load Default Settings", command=self.load_default_settings, font=self.font_bold)
        self.load_defaults_button.grid(row=2, column=0, columnspan=3, padx=5, pady=(10,5), sticky="ew")
        profile_frame.columnconfigure(1, weight=1)

    def on_mode_change_ui(self, selected_mode_str):
        previous_mode_str = self.current_mode_str

        if selected_mode_str == "Keyboard" and previous_mode_str == "Mouse":
            warning_text = ("WARNING: Switching to Keyboard Mode will disable mouse cursor control from this device. "
                           "Ensure you have another way to control your mouse (e.g., a standard mouse) before proceeding.\n\n"
                           "Are you sure you want to switch?")
            if not messagebox.askyesno("Switch to Keyboard Mode?", warning_text, parent=self.root, icon='warning'):
                self.current_mode.set(previous_mode_str) 
                return

        self.current_mode_str = selected_mode_str
        
        if self.is_connected:
            if selected_mode_str == "Mouse": 
                self.send_command("SET_MODE_MOUSE\n")
            elif selected_mode_str == "Keyboard": 
                self.send_command("SET_MODE_KEYBOARD\n")

        self.update_gui_for_mode()

    def update_gui_for_mode(self):
        mode = self.current_mode.get()
        is_mouse_mode = (mode == "Mouse")
        self.root.title(f"Hybrid Input Controller (Mode: {mode})")

        if hasattr(self, 'tuner_params_lf_outer'):
             self.tuner_params_lf_outer.winfo_children()[0].configure(text="Pressure & General Parameters")
        if hasattr(self, 'pressure_thresholds_main_label'):
            self.pressure_thresholds_main_label.configure(text="Pressure Thresholds (Mouse Actions):" if is_mouse_mode else "Pressure Thresholds (Key Actions):")
        
        if hasattr(self, 'tuner_general_settings_label'):
            self.tuner_general_settings_label.configure(text="Sensitivity & General Settings")

        for p_key, mouse_text, kbd_text in [
            ("HST", "Hard Sip (HST - Right Click):", "Hard Sip Threshold (HST):"),
            ("NMIN", "Soft Sip / Neutral Min (NMIN - Scroll Down):", "Soft Sip Threshold (SST/NMIN):"),
            ("SPT", "Soft Puff (SPT - Scroll Up):", "Soft Puff Threshold (SPT):"),
            ("HPT", "Hard Puff (HPT - Left Click):", "Hard Puff Threshold (HPT):")]:
            if p_key in self.param_labels: self.param_labels[p_key].configure(text=mouse_text if is_mouse_mode else kbd_text)

        if "SAD_TUNER_DESC" in self.param_desc_labels: self.param_desc_labels["SAD_TUNER_DESC"].configure(text="Delay for soft mouse actions (unused)." if is_mouse_mode else "Delay for soft key holds (unused).")
        
        if hasattr(self, 'stick_params_content_frame'): 
            self._rebuild_stick_control_params(mode)

        if hasattr(self, 'joystick_canvas_lf_outer'): self.joystick_canvas_lf_outer.winfo_children()[0].configure(text="Joystick Position (Cursor)" if is_mouse_mode else "Joystick Position (Key Sectors)")
        if hasattr(self, 'calib_actions_lf_outer'): self.calib_actions_lf_outer.winfo_children()[0].configure(text="Calibration Actions (Mouse Triggers)" if is_mouse_mode else "Calibration Actions (Key Triggers)")
        
        trainer_tab = self.tab_view.tab("Trainer")
        self._trainer_clear_canvas_content()
        for widget in trainer_tab.winfo_children(): widget.destroy()

        if is_mouse_mode: 
            self.create_trainer_widgets(trainer_tab)
        else:
            ctk.CTkLabel(trainer_tab, text="Trainer is only available in Mouse Mode.", font=self.font_header).pack(expand=True, padx=20, pady=20)
            if self.tab_view.get() == "Trainer": 
                self.tab_view.set("Tuner & Profiles")
        
        self.on_tab_change()
        self._update_joystick_visualizer()
        self.root.update_idletasks()

    def on_tab_change(self, selected_tab_name=None):
        if selected_tab_name is None and hasattr(self, 'tab_view') and self.tab_view.winfo_exists():
             selected_tab_name = self.tab_view.get()
        elif not hasattr(self, 'tab_view') or not self.tab_view.winfo_exists():
            return 
        
        if selected_tab_name != 'Trainer' and self._trainer_loop_job_id:
            self.root.after_cancel(self._trainer_loop_job_id); self._trainer_loop_job_id = None
        elif selected_tab_name == 'Trainer' and self.trainer_target_active and self.trainer_game_mode == 'hover':
            if self._trainer_loop_job_id: self.root.after_cancel(self._trainer_loop_job_id)
            self._trainer_loop_job_id = self.root.after(self.TRAINER_UPDATE_INTERVAL_MS, self._trainer_main_loop)

        if selected_tab_name != 'Calibrate Sensor' and self.is_calibrating_arduino_mode: self.stop_arduino_calibration_mode()
        
        if selected_tab_name == 'Calibrate Sensor':
             if hasattr(self,'calibration_instructions_label'):
                 initial_calib_text = "Click 'Start Sensor Stream'..." if not self.is_calibrating_arduino_mode else "Sensor stream active..."
                 self.calibration_instructions_label.configure(text=initial_calib_text)
                 if self.is_calibrating_arduino_mode: self._update_pressure_visualizer()
        elif selected_tab_name == 'Stick Control':
            if hasattr(self, 'joystick_canvas') and self.joystick_canvas.winfo_exists(): self._update_joystick_visualizer()

    def create_trainer_widgets(self, parent_tab):
        trainer_controls_frame=ctk.CTkFrame(parent_tab, fg_color="transparent"); trainer_controls_frame.pack(pady=10,fill=tk.X, padx=5)
        self.target_practice_btn = ctk.CTkButton(trainer_controls_frame,text="Target Practice",command=self.start_target_practice, font=self.font_bold)
        self.target_practice_btn.pack(side=tk.LEFT,padx=5)
        self.click_accuracy_btn = ctk.CTkButton(trainer_controls_frame,text="Click Accuracy",command=self.start_click_accuracy, font=self.font_bold)
        self.click_accuracy_btn.pack(side=tk.LEFT,padx=5)
        self.scroll_practice_btn = ctk.CTkButton(trainer_controls_frame,text="Scroll Practice",command=self.start_scroll_practice, font=self.font_bold)
        self.scroll_practice_btn.pack(side=tk.LEFT,padx=5)
        self.trainer_score_label=ctk.CTkLabel(trainer_controls_frame,textvariable=self.trainer_score_display_var,font=self.font_header)
        self.trainer_score_display_var.set("Score: 0"); self.trainer_score_label.pack(side=tk.LEFT,padx=20)
        self.instructions_label_trainer=ctk.CTkLabel(parent_tab,text="Select a training mode.",justify=tk.CENTER,font=self.font_bold)
        self.instructions_label_trainer.pack(fill=tk.X,pady=5, padx=10)
        self.trainer_canvas_area_host=ctk.CTkFrame(parent_tab, border_width=1)
        self.trainer_canvas_area_host.pack(fill=tk.BOTH,expand=True,padx=10,pady=5)

    def create_calibration_widgets(self, parent_tab):
        calib_main_frame = ctk.CTkFrame(parent_tab, fg_color="transparent"); calib_main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        calib_main_frame.columnconfigure(0, weight=1); calib_main_frame.rowconfigure(0, weight=0); calib_main_frame.rowconfigure(1, weight=3); calib_main_frame.rowconfigure(2, weight=1); calib_main_frame.rowconfigure(3, weight=0)
        top_section_frame = ctk.CTkFrame(calib_main_frame, fg_color="transparent"); top_section_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.calibration_instructions_label=ctk.CTkLabel(top_section_frame,text="Click 'Start Sensor Stream' then select an action.",justify=tk.CENTER,font=self.font_bold); self.calibration_instructions_label.pack(pady=5, fill=tk.X, padx=5)
        live_pressure_label_calib=ctk.CTkLabel(top_section_frame,textvariable=self.calibration_current_value_tkvar,font=self.font_pressure); live_pressure_label_calib.pack(pady=10)
        arduino_mode_frame=ctk.CTkFrame(top_section_frame, fg_color="transparent"); arduino_mode_frame.pack(pady=5)
        self.start_arduino_calib_button=ctk.CTkButton(arduino_mode_frame,text="Start Sensor Stream",command=self.start_arduino_calibration_mode,width=180, font=self.font_bold); self.start_arduino_calib_button.pack(side=tk.LEFT,padx=5)
        self.stop_arduino_calib_button=ctk.CTkButton(arduino_mode_frame,text="Stop Sensor Stream",command=self.stop_arduino_calibration_mode,state=tk.DISABLED,width=180, font=self.font_bold); self.stop_arduino_calib_button.pack(side=tk.LEFT,padx=5)
        viz_lf_outer, viz_content_frame = self._create_labeled_frame(calib_main_frame, "Live Pressure Visualizer"); viz_lf_outer.grid(row=1, column=0, sticky="nsew", pady=(0, 10), padx=5)
        canvas_bg = self._get_themed_canvas_bg(); self.pressure_visualizer_canvas = tk.Canvas(viz_content_frame, width=self.pressure_canvas_min_width, height=self.pressure_canvas_min_height, bg=canvas_bg, highlightthickness=0); self.pressure_visualizer_canvas.pack(pady=5, padx=5, expand=True, fill=tk.BOTH, anchor=tk.CENTER)
        actions_and_log_frame = ctk.CTkFrame(calib_main_frame, fg_color="transparent"); actions_and_log_frame.grid(row=2, column=0, sticky="nsew", pady=(0,5), padx=0)
        
        self.calib_actions_lf_outer, actions_content_frame = self._create_labeled_frame(actions_and_log_frame, "Calibration Actions")
        self.calib_actions_lf_outer.pack(fill=tk.X, pady=5, padx=5) 
        self.calibration_actions = ["Neutral", "Soft Sip", "Hard Sip", "Soft Puff", "Hard Puff"]; self.action_buttons = {}
        for i, action_name in enumerate(self.calibration_actions):
            btn = ctk.CTkButton(actions_content_frame, text=f"Record {action_name}", command=lambda name=action_name: self.start_collecting_samples(name), state=tk.DISABLED, font=self.font_bold)
            btn.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="ew"); self.action_buttons[action_name] = btn
        actions_content_frame.columnconfigure((0, 1, 2), weight=1)
        log_lf_outer, log_content_frame = self._create_labeled_frame(actions_and_log_frame, "Calibration Log & Results"); log_lf_outer.pack(fill=tk.X, pady=5, padx=5)
        self.calib_log_text = ctk.CTkTextbox(log_content_frame, height=100, wrap=tk.WORD, font=self.font_log, activate_scrollbars=True); self.calib_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.calib_log_text.insert(tk.END, "Calibration Log:\n"); self.calib_log_text.configure(state=tk.DISABLED)
        self.analyze_button = ctk.CTkButton(calib_main_frame, text="Analyze Data & Suggest Thresholds", command=self.analyze_calibration_data, state=tk.DISABLED, font=self.font_bold); self.analyze_button.grid(row=3, column=0, pady=(5,10), padx=5, sticky="ew")

    def create_joystick_control_widgets(self, parent_tab):
        main_frame = ctk.CTkFrame(parent_tab, fg_color="transparent"); main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        main_frame.columnconfigure(0, weight=3); main_frame.columnconfigure(1, weight=1); main_frame.rowconfigure(0, weight=1)    
        
        self.joystick_canvas_lf_outer, canvas_content_frame = self._create_labeled_frame(main_frame, "Joystick Position") 
        self.joystick_canvas_lf_outer.grid(row=0, column=0, padx=(5,10), pady=5, sticky="nsew")
        canvas_bg = self._get_themed_canvas_bg()
        self.joystick_canvas = tk.Canvas(canvas_content_frame, width=self.joystick_canvas_min_width, height=self.joystick_canvas_min_height, bg=canvas_bg, relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.joystick_canvas.pack(padx=10, pady=10, expand=True, fill=tk.BOTH, anchor=tk.CENTER)
        
        self.stick_params_lf_outer, self.stick_params_content_frame = self._create_labeled_frame(main_frame, "Stick Parameters") 
        self.stick_params_lf_outer.grid(row=0, column=1, padx=(0,5), pady=5, sticky="nsew") 

    def _rebuild_stick_control_params(self, mode):
        for widget in self.stick_params_content_frame.winfo_children():
            widget.destroy()
    
        self.stick_params_content_frame.columnconfigure(0, weight=1) # Ensure single column widgets expand
        self.stick_params_content_frame.columnconfigure(1, weight=1) # For two-column layout
    
        is_mouse_mode = (mode == "Mouse")
        self.stick_params_lf_outer.winfo_children()[0].configure(text="Stick Mouse Parameters" if is_mouse_mode else "Stick Keyboard Parameters")
    
        if is_mouse_mode:
            row_idx = 0
            row_idx = self.create_param_slider_widget(self.stick_params_content_frame, "Joystick Deadzone (JDZ%):", self.params_tkvars["JDZ"], "JDZ", 0, 100, row_idx, desc_text_str="Area where stick movement is ignored.")
            row_idx = self.create_param_slider_widget(self.stick_params_content_frame, "Move Threshold (JMT%):", self.params_tkvars["JMT"], "JMT", 0, 100, row_idx, desc_text_str="Min movement to start moving cursor.")
            row_idx = self.create_param_slider_widget(self.stick_params_content_frame, "Cursor Speed (CSP):", self.params_tkvars["CSP"], "CSP", 1, 50, row_idx, desc_text_str="Max speed of the mouse cursor.")
            
            ctk.CTkFrame(self.stick_params_content_frame, height=2, border_width=1).grid(row=row_idx+1, column=0, columnspan=3, pady=10, sticky="ew")
            self.osk_toggle_checkbox = ctk.CTkCheckBox(self.stick_params_content_frame, text="Enable OSK Toggle (Bottom-Left Corner)",
                                                       variable=self.osk_toggle_enabled_tkvar, onvalue=True, offvalue=False,
                                                       font=self.font_normal)
            self.osk_toggle_checkbox.grid(row=row_idx+2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
    
        else: # Keyboard Mode
            current_row = 0
            jmt_frame = ctk.CTkFrame(self.stick_params_content_frame, fg_color="transparent")
            jmt_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            current_row = self.create_param_slider_widget(jmt_frame, "Move Threshold (JMT%):", self.params_tkvars["JMT"], "JMT", 0, 50, 0, desc_text_str="How far to move stick to activate a key.")

            # Container frame for the two-column layout
            keybinds_container = ctk.CTkFrame(self.stick_params_content_frame, fg_color="transparent")
            keybinds_container.grid(row=current_row + 1, column=0, columnspan=2, sticky="nsew")
            keybinds_container.columnconfigure(0, weight=1, minsize=200)
            keybinds_container.columnconfigure(1, weight=1, minsize=200)
    
            # --- Column 1: Pressure Keybinds ---
            pressure_keys_lf, pressure_keys_frame = self._create_labeled_frame(keybinds_container, "Pressure Keybinds")
            pressure_keys_lf.grid(row=0, column=0, padx=(0, 5), sticky="nsew")
            pressure_keys_frame.columnconfigure(1, weight=1)
    
            key_map = [("Hard Puff Key (HPT):", "HPT"), ("Soft Puff Key (SPT):", "SPT"), ("Hard Sip Key (HST):", "HST"), ("Soft Sip Key (SST):", "SST")]
            self.keyboard_pressure_key_widgets.clear()
            for i, (label_text, key) in enumerate(key_map):
                lbl = ctk.CTkLabel(pressure_keys_frame, text=label_text, font=self.font_normal)
                lbl.grid(row=i, column=0, padx=5, pady=2, sticky="w")
                entry = ctk.CTkEntry(pressure_keys_frame, textvariable=self.pressure_key_tkvars[key], width=60)
                entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
                self.keyboard_pressure_key_widgets[key] = {'label': lbl, 'entry': entry}
    
            # --- Column 2: Joystick Sector Keybinds ---
            sector_keys_lf, sector_keys_frame = self._create_labeled_frame(keybinds_container, "Joystick Sector Keybinds")
            sector_keys_lf.grid(row=0, column=1, padx=(5, 0), sticky="nsew")
            sector_keys_frame.columnconfigure(1, weight=1)
    
            ctk.CTkLabel(sector_keys_frame, text="Sectors:", font=self.font_normal).grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
            self.sector_count_combo = ctk.CTkComboBox(sector_keys_frame, values=[str(i) for i in range(2, 9)], variable=self.num_sectors_tkvar, command=self._rebuild_sector_key_widgets, state="readonly")
            self.sector_count_combo.grid(row=0, column=1, padx=5, pady=(5,0), sticky="ew")
            
            self.keyboard_sector_widgets_frame = ctk.CTkFrame(sector_keys_frame, fg_color="transparent")
            self.keyboard_sector_widgets_frame.grid(row=1, column=0, columnspan=2, pady=(5,0), sticky="ew")
            self.keyboard_sector_widgets_frame.columnconfigure(1, weight=1)
            self._rebuild_sector_key_widgets()
    
            # --- Row below the columns ---
            keys_info_lf, keys_info_frame = self._create_labeled_frame(self.stick_params_content_frame, "Special Key Names Helper")
            keys_info_lf.grid(row=current_row + 2, column=0, columnspan=2, pady=(15, 5), sticky="ew")
            
            info_text = ("• Single Keys: Type the character (e.g., w).\n"
                         "• Special Keys: Type the name (e.g., shift, enter).\n"
                         "• Joystick Combos: Use a space (e.g., w shift).\n\n"
                         "Available Names:\n"
                         "  Modifiers: shift, ctrl, alt, win\n"
                         "  Actions: enter, esc, backspace, tab, space\n"
                         "  Navigation: left, right, up, down, home, end\n"
                         "  Function: f1, f2, ..., f12")

            info_label = ctk.CTkLabel(keys_info_frame, 
                                      text=info_text, 
                                      font=self.font_small, 
                                      justify=tk.LEFT, 
                                      anchor="w")
            info_label.pack(padx=10, pady=5, fill="x", expand=True)

            self.apply_keyboard_keys_button = ctk.CTkButton(self.stick_params_content_frame, text="Apply Keyboard Keys to Arduino", command=self.apply_keyboard_settings, font=self.font_bold)
            self.apply_keyboard_keys_button.grid(row=current_row + 3, column=0, columnspan=2, pady=(15,5), padx=5, sticky="ew")


    def _rebuild_sector_key_widgets(self, event=None):
        if not hasattr(self, 'keyboard_sector_widgets_frame') or not self.keyboard_sector_widgets_frame.winfo_exists(): return
            
        for widget in self.keyboard_sector_widgets_frame.winfo_children(): widget.destroy()
        self.keyboard_sector_widgets.clear()
        
        num_sectors = int(self.num_sectors_tkvar.get())
        
        for i in range(num_sectors):
            label = ctk.CTkLabel(self.keyboard_sector_widgets_frame, text=f"Sector {i+1} Key(s):", font=self.font_normal)
            label.grid(row=i, column=0, padx=5, pady=2, sticky="w")

            entry = ctk.CTkEntry(self.keyboard_sector_widgets_frame, textvariable=self.sector_key_tkvars[i], width=60)
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            
            self.keyboard_sector_widgets[i] = {'label': label, 'entry': entry}
        self._update_joystick_visualizer()


    def _update_joystick_visualizer(self):
        if not hasattr(self, 'joystick_canvas') or not self.joystick_canvas.winfo_exists(): return
        canvas = self.joystick_canvas
        canvas_bg = self._get_themed_canvas_bg()
        canvas.configure(bg=canvas_bg)
        
        try:
            w = canvas.winfo_width()
            h = canvas.winfo_height()
        except tk.TclError:
            return

        if w <= 1 or h <= 1:
            self.root.after(50, self._update_joystick_visualizer)
            return

        canvas.delete("all")
        cx, cy = w / 2, h / 2
        max_stick_deflection = 512.0
        
        canvas_radius = (min(w, h) / 2) - 25 
        if canvas_radius < 10: canvas_radius = 10
        
        joy_x = self.joystick_x_centered_tkvar.get()
        joy_y = self.joystick_y_centered_tkvar.get()

        if self.current_mode_str == "Keyboard":
            jmt_percent = self.params_tkvars["JMT"].get() / 100.0
            jmt_radius_pixels = jmt_percent * canvas_radius
            canvas.create_oval(cx - jmt_radius_pixels, cy - jmt_radius_pixels, cx + jmt_radius_pixels, cy + jmt_radius_pixels, 
                                outline="orange", dash=(2, 2), tags="jmt_circle")
            canvas.create_text(cx + jmt_radius_pixels + 5, cy, text="JMT", fill="orange", anchor="w", font=self.font_small)

            num_sectors = int(self.num_sectors_tkvar.get())
            slice_angle_deg = 360.0 / num_sectors
            key_font = ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            text_color = "white" if ctk.get_appearance_mode() == "Dark" else "black"
            
            active_sector = -1
            magnitude_percent = (math.sqrt(joy_x**2 + joy_y**2) / max_stick_deflection) * 100.0
            if magnitude_percent > self.params_tkvars["JMT"].get():
                angle_deg = math.degrees(math.atan2(-joy_y, joy_x))
                angle_deg += slice_angle_deg / 2.0
                if angle_deg < 0: angle_deg += 360
                active_sector = int(angle_deg / slice_angle_deg)

            for i in range(num_sectors):
                angle_rad = math.radians(i * slice_angle_deg - (slice_angle_deg / 2.0))
                line_end_x = cx + canvas_radius * math.cos(angle_rad)
                line_end_y = cy + canvas_radius * math.sin(angle_rad)
                canvas.create_line(cx, cy, line_end_x, line_end_y, fill="gray50", dash=(1,3))

                text_angle_rad = math.radians(i * slice_angle_deg)
                text_radius = canvas_radius * 0.7
                text_x = cx + text_radius * math.cos(text_angle_rad)
                text_y = cy + text_radius * math.sin(text_angle_rad)
                key_char = self.sector_key_tkvars[i].get().upper().replace(" ", "+")[:5]
                
                fill_color = "cyan" if i == active_sector else text_color
                canvas.create_text(text_x, text_y, text=key_char, font=key_font, fill=fill_color)

        else: # Mouse Mode
            jmt_percent = self.params_tkvars["JMT"].get() / 100.0
            jmt_radius_pixels = jmt_percent * canvas_radius
            canvas.create_oval(cx - jmt_radius_pixels, cy - jmt_radius_pixels, cx + jmt_radius_pixels, cy + jmt_radius_pixels, 
                                outline="orange", dash=(2, 2), tags="jmt_circle")
            canvas.create_text(cx, cy + jmt_radius_pixels + 5, text="JMT", fill="orange", anchor="n", font=self.font_small)

            deadzone_percent = self.params_tkvars["JDZ"].get() / 100.0
            deadzone_radius_pixels = deadzone_percent * canvas_radius
            canvas.create_oval(cx - deadzone_radius_pixels, cy - deadzone_radius_pixels, cx + deadzone_radius_pixels, cy + deadzone_radius_pixels, 
                                outline="skyblue", dash=(3, 3), tags="jdz_circle")
            canvas.create_text(cx + deadzone_radius_pixels + 5, cy, text="JDZ", fill="skyblue", anchor="w", font=self.font_small)

        joy_x_clamped = max(-max_stick_deflection, min(max_stick_deflection, joy_x))
        joy_y_clamped = max(-max_stick_deflection, min(max_stick_deflection, joy_y))
        
        indicator_x = cx + (joy_x_clamped / max_stick_deflection) * canvas_radius
        indicator_y = cy - (joy_y_clamped / max_stick_deflection) * canvas_radius

        ind_r = 4
        canvas.create_oval(indicator_x - ind_r, indicator_y - ind_r, indicator_x + ind_r, indicator_y + ind_r, 
                            fill="red", outline="white", tags="indicator")

    def populate_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]; self.port_combo.configure(values=ports)
        if ports: self.port_combo.set(ports[0])
        else: self.port_combo.set("")

    def toggle_connect(self):
        if not self.is_connected:
            port = self.port_combo.get()
            if not port:
                messagebox.showerror("Error", "No serial port selected.", parent=self.root); return
            try:
                self.ser = serial.Serial(port, 115200, timeout=0.1)
                time.sleep(1.8)
                self.is_connected = True
                self.connect_button.configure(text="Disconnect")
                self.apply_button.configure(state=tk.NORMAL)
                if hasattr(self, 'apply_keyboard_keys_button'): self.apply_keyboard_keys_button.configure(state=tk.NORMAL)

                self.mode_combo.configure(state="readonly")
                
                self.set_status(f"Connected to {port}")
                self.stop_read_thread.clear()
                self.read_thread = threading.Thread(target=self.read_from_arduino, daemon=True)
                self.read_thread.start()
                
                current_gui_mode = self.current_mode.get()
                if current_gui_mode == "Mouse": self.send_command("SET_MODE_MOUSE\n")
                elif current_gui_mode == "Keyboard": self.send_command("SET_MODE_KEYBOARD\n")
                
                self.root.after(100, self.apply_all_settings) 

            except serial.SerialException as e:
                messagebox.showerror("Connection Error", str(e), parent=self.root)
                self.ser = None; self.is_connected = False
                self.mode_combo.configure(state="readonly")
        else:
            if self.is_calibrating_arduino_mode: self.stop_arduino_calibration_mode(silent=True)
            self.is_connected = False; self.stop_read_thread.set()
            if hasattr(self, 'read_thread') and self.read_thread.is_alive(): self.read_thread.join(timeout=0.5)
            if self.ser and self.ser.is_open: self.ser.close()
            self.ser = None; self.connect_button.configure(text="Connect")
            self.apply_button.configure(state=tk.DISABLED)
            if hasattr(self, 'apply_keyboard_keys_button'): self.apply_keyboard_keys_button.configure(state=tk.DISABLED)
            self.mode_combo.configure(state="readonly")
            self.set_status("Disconnected"); self.current_pressure_tkvar.set("Pressure: N/A")
            self.joystick_x_centered_tkvar.set(0); self.joystick_y_centered_tkvar.set(0)
            if hasattr(self, 'joystick_canvas') and self.joystick_canvas.winfo_exists(): self._update_joystick_visualizer()

    def send_command(self, command):
        if self.ser and self.ser.is_open:
            try:
                if not command.endswith('\n'): command += '\n'
                self.ser.write(command.encode('utf-8'))
            except serial.SerialException as e:
                self.set_status(f"Send Error: {e}")
                self.handle_serial_error_disconnect()
    
    def _get_key_code(self, key_string):
        if key_string == ' ':
            return 32

        s = key_string.lower().strip()
        if not s:
            return None
        if s in self.SPECIAL_KEYS:
            return self.SPECIAL_KEYS[s]
        if len(s) == 1:
            return ord(s)
        return None

    def apply_keyboard_settings(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to Arduino first.", parent=self.root); return
        if self.current_mode_str != "Keyboard":
             messagebox.showinfo("Info", "This feature is only for Keyboard Mode.", parent=self.root); return

        self.set_status("Applying keyboard key settings...")
        
        for key_code, tk_var in self.pressure_key_tkvars.items():
            key_string = tk_var.get()
            ascii_val = self._get_key_code(key_string)
            if ascii_val is None:
                messagebox.showerror("Invalid Key", f"Pressure key '{key_string}' for {key_code} is not a valid key.", parent=self.root)
                return
            self.send_command(f"SET_KEY_{key_code}:{ascii_val}")
            time.sleep(0.02)

        num_sectors = int(self.num_sectors_tkvar.get())
        self.send_command(f"SET_NUM_SECTORS:{num_sectors}")
        time.sleep(0.02)

        for i in range(num_sectors):
            key_input_str = self.sector_key_tkvars[i].get()
            if not key_input_str:
                messagebox.showerror("Invalid Key", f"Sector {i+1} key cannot be empty.", parent=self.root)
                return
            
            key_parts = key_input_str.strip().lower().split(maxsplit=1)
            key1_str = key_parts[0]
            key2_str = key_parts[1] if len(key_parts) > 1 else ' ' 
            
            ascii_val1 = self._get_key_code(key1_str)
            ascii_val2 = self._get_key_code(key2_str)

            if ascii_val1 is None:
                messagebox.showerror("Invalid Key", f"Sector {i+1} key '{key1_str}' is invalid.", parent=self.root)
                return
            if ascii_val2 is None:
                messagebox.showerror("Invalid Key", f"Sector {i+1} key '{key2_str}' is invalid.", parent=self.root)
                return

            self.send_command(f"SET_JOY_KEY:{i},{ascii_val1},{ascii_val2}")
            time.sleep(0.02)
        
        self.set_status("Keyboard key settings applied.")


    def apply_all_settings(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect to Arduino first.", parent=self.root); return
        self.set_status(f"Applying all settings to Arduino (Mode: {self.current_mode.get()})...")
        for key, tk_var in self.params_tkvars.items():
            value_to_send = int(tk_var.get())
            self.send_param_update(key, value_to_send)
            time.sleep(0.02)
        
        if self.current_mode.get() == "Keyboard":
            self.apply_keyboard_settings()

        self.set_status("All settings applied to Arduino.")
        if self.is_calibrating_arduino_mode and hasattr(self, 'pressure_visualizer_canvas'): self._update_pressure_visualizer()
        if hasattr(self, 'joystick_canvas') and self.tab_view.winfo_exists() and self.tab_view.get() == "Stick Control": self._update_joystick_visualizer()

    def send_param_update(self, param_key, value):
        self.send_command(f"SET_{param_key}:{value}\n")

    def read_from_arduino(self):
        while not self.stop_read_thread.is_set():
            if not self.ser or not self.ser.is_open:
                break
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        self.root.after(0, self._process_serial_line_on_main_thread, line)
            except serial.SerialException:
                self.root.after(0, self.handle_serial_error_disconnect)
                break
            except Exception as e:
                if not self.stop_read_thread.is_set():
                    print(f"Read thread error: {e}")
            time.sleep(0.001)

    def _process_serial_line_on_main_thread(self, line):
        try:
            if self.is_calibrating_arduino_mode and line.startswith("CALIB_P:"):
                value = int(line.split(":")[1])
                self.calibration_current_value_tkvar.set(f"Pressure: {value}")
                self.pressure_history.append(value)
                if len(self.pressure_history) > self.max_history_points:
                    self.pressure_history.pop(0)
                self._update_pressure_visualizer()
                if self.calibrating_action_name.get():
                    self.calibration_samples.append(value)

            elif line.startswith("P:"):
                if not self.is_calibrating_arduino_mode:
                    self.current_pressure_tkvar.set(f"Pressure: {line.split(':')[1]}")

            elif line.startswith("JOY:"):
                parts = line.split(':')[1].split(',')
                self.joystick_x_centered_tkvar.set(int(parts[0]))
                self.joystick_y_centered_tkvar.set(int(parts[1]))
                if hasattr(self, 'tab_view') and self.tab_view.winfo_exists() and self.tab_view.get() == "Stick Control":
                    self._update_joystick_visualizer()

            elif line.startswith("ACK:") or line.startswith("ERR:") or line.startswith("INFO:"):
                self.set_status(f"Arduino: {line}")
        
        except (IndexError, ValueError, tk.TclError) as e:
            pass

    def handle_serial_error_disconnect(self):
        if self.is_connected: self.toggle_connect()

    def get_current_settings_dict(self): 
        settings = {key:tk_var.get() for key,tk_var in self.params_tkvars.items()}
        settings['osk_toggle_enabled'] = int(self.osk_toggle_enabled_tkvar.get())
        settings['num_sectors'] = self.num_sectors_tkvar.get()
        settings['sector_keys'] = [var.get() for var in self.sector_key_tkvars]
        settings['pressure_keys'] = {key: var.get() for key, var in self.pressure_key_tkvars.items()}
        return settings

    def apply_settings_from_dict(self,settings_dict,profile_name="<Loaded Profile>"):
        actual_settings = settings_dict.get("settings", settings_dict)

        for key,value in actual_settings.items():
            if key in self.params_tkvars:
                self.params_tkvars[key].set(int(value))
        
        self.osk_toggle_enabled_tkvar.set(bool(actual_settings.get('osk_toggle_enabled', False)))

        if 'num_sectors' in actual_settings: self.num_sectors_tkvar.set(str(actual_settings['num_sectors']))
        if 'sector_keys' in actual_settings:
            keys = actual_settings['sector_keys']
            for i in range(len(self.sector_key_tkvars)):
                if i < len(keys): self.sector_key_tkvars[i].set(keys[i])
                else: self.sector_key_tkvars[i].set("")
        if 'pressure_keys' in actual_settings:
            for key, value in actual_settings['pressure_keys'].items():
                if key in self.pressure_key_tkvars:
                    self.pressure_key_tkvars[key].set(value)

        self.current_profile_name.set(profile_name)
        self.set_status(f"Settings from '{profile_name}' loaded into GUI.")
        self.update_gui_for_mode()
        if self.is_connected: self.apply_all_settings()

    def populate_profiles_dropdown(self):
        try:
            profile_files=[f for f in os.listdir(PROFILES_DIR) if f.endswith(".json")]
            profile_names=[os.path.splitext(f)[0] for f in profile_files]
            current_selection = self.current_profile_name.get()
            self.profile_combo.configure(values=profile_names)
            if profile_names:
                if current_selection in profile_names and current_selection != "<Default Settings Applied>":
                    self.profile_combo.set(current_selection)
                else: self.profile_combo.set(profile_names[0]); self.current_profile_name.set(profile_names[0])
            else: self.profile_combo.set(""); self.current_profile_name.set("<Default Settings>")
        except Exception as e:self.set_status(f"Err listing profiles: {e}")

    def load_selected_profile(self):
        profile_name=self.profile_combo.get()
        if not profile_name or profile_name=="<Default Settings>": messagebox.showwarning("Load Profile","No profile selected.",parent=self.root);return
        self._load_profile_by_name(profile_name)

    def _load_profile_by_name(self,profile_name_to_load):
        filepath=os.path.join(PROFILES_DIR,f"{profile_name_to_load}.json")
        try:
            with open(filepath,'r') as f:settings_data=json.load(f)
            self.apply_settings_from_dict(settings_data,profile_name_to_load); 
            self.current_profile_name.set(profile_name_to_load)
        except FileNotFoundError:messagebox.showerror("Load Error",f"Profile '{profile_name_to_load}' not found.",parent=self.root)
        except Exception as e:messagebox.showerror("Load Error",f"Failed to load '{profile_name_to_load}': {e}",parent=self.root)

    def load_default_settings(self):
        if messagebox.askyesno("Load Defaults","Reset all settings to factory defaults?",parent=self.root):
            for key, value in DEFAULT_SETTINGS.items():
                if key == "OSK_ENABLED":
                    self.osk_toggle_enabled_tkvar.set(bool(value))
                elif key in self.params_tkvars:
                    self.params_tkvars[key].set(int(value))
            
            self.num_sectors_tkvar.set("8")
            for i, key in enumerate(DEFAULT_SECTOR_KEYS):
                self.sector_key_tkvars[i].set(key)
            for key, value in DEFAULT_PRESSURE_KEYS.items():
                self.pressure_key_tkvars[key].set(value)

            self.current_profile_name.set("<Default Settings Applied>")
            self.set_status(f"Default settings loaded into GUI.")
            self.update_gui_for_mode()
            if self.is_connected:self.apply_all_settings()

    def _save_profile_to_file(self,profile_name,settings_dict): 
        if not profile_name.strip() or profile_name=="<Default Settings>": messagebox.showerror("Save Profile","Invalid profile name.",parent=self.root);return False
        
        data_to_save={"profile_name_meta":profile_name,"settings":settings_dict}
        filepath=os.path.join(PROFILES_DIR,f"{profile_name}.json")
        try:
            with open(filepath,'w') as f:json.dump(data_to_save,f,indent=2)
            self.set_status(f"Profile '{profile_name}' saved.");self.populate_profiles_dropdown()
            self.profile_combo.set(profile_name);self.current_profile_name.set(profile_name); return True
        except Exception as e:messagebox.showerror("Save Error",f"Could not save profile: {e}",parent=self.root);return False

    def save_current_profile(self):
        name=self.profile_combo.get()
        if not name or name=="<Default Settings>" or name=="<Default Settings Applied>":self.save_profile_as();return
        if messagebox.askyesno("Overwrite Profile",f"Overwrite existing profile '{name}'?",parent=self.root): self._save_profile_to_file(name, self.get_current_settings_dict())

    def save_profile_as(self):
        settings = self.get_current_settings_dict()
        dialog = ctk.CTkInputDialog(text="Enter new profile name:", title="Save As New Profile")
        name = dialog.get_input() 
        if name: self._save_profile_to_file(name, settings)

    def delete_selected_profile(self):
        name=self.profile_combo.get()
        if not name or name=="<Default Settings>" or name=="<Default Settings Applied>": messagebox.showwarning("Delete Profile","No saved profile selected.",parent=self.root);return
        if messagebox.askyesno("Confirm Delete",f"Delete profile '{name}'? This cannot be undone.",parent=self.root):
            try:
                os.remove(os.path.join(PROFILES_DIR,f"{name}.json")); self.set_status(f"Profile '{name}' deleted.")
                self.current_profile_name.set("<Default Settings>"); self.populate_profiles_dropdown()
            except Exception as e:messagebox.showerror("Delete Error",f"Failed to delete '{name}': {e}",parent=self.root)

    def _trainer_clear_canvas_content(self):
        self.trainer_target_active = False
        self.trainer_game_mode = None
        if self._trainer_loop_job_id:
            self.root.after_cancel(self._trainer_loop_job_id); self._trainer_loop_job_id = None
        if hasattr(self, 'trainer_content_host_frame') and self.trainer_content_host_frame and self.trainer_content_host_frame.winfo_exists():
            for widget in self.trainer_content_host_frame.winfo_children(): widget.destroy()
        self.trainer_active_tk_canvas = None
        self.mouse_trail_points.clear(); self.mouse_trail_ids = []
        if hasattr(self, 'trainer_score_display_var'): self.trainer_score_display_var.set("Score: 0")
        self.trainer_target_id, self.trainer_target_coords, self.is_target_hit_and_waiting_for_respawn = None, None, False

    def _setup_trainer_content_host(self):
        if hasattr(self, 'trainer_canvas_area_host') and self.trainer_canvas_area_host.winfo_exists():
            for widget in self.trainer_canvas_area_host.winfo_children(): widget.destroy()
            self.trainer_content_host_frame = ctk.CTkFrame(self.trainer_canvas_area_host, fg_color="transparent")
            self.trainer_content_host_frame.pack(fill=tk.BOTH, expand=True)
            return self.trainer_content_host_frame
        return None

    def start_target_practice(self):
        if self.current_mode.get() != "Mouse": return
        self._trainer_clear_canvas_content()
        self.trainer_target_active = True
        self.trainer_game_mode = 'hover'
        if hasattr(self, 'instructions_label_trainer'): self.instructions_label_trainer.configure(text="Move cursor over the red target!")
        self.trainer_score_value=0; self.trainer_score_display_var.set(f"Score: {self.trainer_score_value}")
        host = self._setup_trainer_content_host()
        if not host: return
        canvas_bg = self._get_themed_canvas_bg()
        self.trainer_active_tk_canvas = tk.Canvas(host, bg=canvas_bg, highlightthickness=0)
        self.trainer_active_tk_canvas.pack(fill=tk.BOTH, expand=True)
        self.trainer_target_size=30
        self.is_target_hit_and_waiting_for_respawn=False
        self.mouse_trail_points.clear(); self.mouse_trail_ids = []
        self.trainer_active_tk_canvas.after(100, self._trainer_spawn_hover_target)
        if self._trainer_loop_job_id: self.root.after_cancel(self._trainer_loop_job_id)
        self._trainer_loop_job_id = self.root.after(self.TRAINER_UPDATE_INTERVAL_MS, self._trainer_main_loop)

    def _trainer_main_loop(self):
        if not self.trainer_target_active or self.trainer_game_mode != 'hover' or \
           self.current_mode.get() != 'Mouse' or not hasattr(self, 'trainer_active_tk_canvas') or \
           not self.trainer_active_tk_canvas or not self.trainer_active_tk_canvas.winfo_exists():
            self._trainer_loop_job_id = None
            return

        canvas = self.trainer_active_tk_canvas
        try:
            mx_g, my_g = pyautogui.position()
            crx, cry = canvas.winfo_rootx(), canvas.winfo_rooty()
            rel_mx, rel_my = mx_g - crx, my_g - cry

            if 0 <= rel_mx <= canvas.winfo_width() and 0 <= rel_my <= canvas.winfo_height():
                self.mouse_trail_points.append((rel_mx, rel_my))
            self._draw_mouse_trail()

            if not self.is_target_hit_and_waiting_for_respawn and self.trainer_target_id and self.trainer_target_coords:
                if canvas.coords(self.trainer_target_id) and \
                   self.trainer_target_coords[0] < rel_mx < self.trainer_target_coords[2] and \
                   self.trainer_target_coords[1] < rel_my < self.trainer_target_coords[3]:
                    self.trainer_score_value += 1
                    self.trainer_score_display_var.set(f"Score: {self.trainer_score_value}")
                    canvas.itemconfig(self.trainer_target_id, fill="lightgreen")
                    self.is_target_hit_and_waiting_for_respawn = True
                    hit_target_id = self.trainer_target_id
                    self.trainer_target_id, self.trainer_target_coords = None, None
                    
                    def delayed_respawn():
                        if canvas.winfo_exists():
                            try:
                                if hit_target_id in canvas.find_all(): canvas.delete(hit_target_id)
                            except tk.TclError: pass
                        if self.trainer_target_active and self.trainer_game_mode == 'hover':
                            self._trainer_spawn_hover_target()
                    self.root.after(400, delayed_respawn)
        except (tk.TclError, Exception):
            self._trainer_loop_job_id = None; return
        
        self._trainer_loop_job_id = self.root.after(self.TRAINER_UPDATE_INTERVAL_MS, self._trainer_main_loop)

    def _trainer_spawn_hover_target(self):
        if self.current_mode.get() != "Mouse" or not self.trainer_target_active or not hasattr(self,'trainer_active_tk_canvas') or not self.trainer_active_tk_canvas or not self.trainer_active_tk_canvas.winfo_exists():return
        canvas = self.trainer_active_tk_canvas
        if self.trainer_target_id:
            try: canvas.delete(self.trainer_target_id)
            except tk.TclError:pass
        canvas.update_idletasks() 
        w,h = canvas.winfo_width(), canvas.winfo_height()
        if w <= self.trainer_target_size or h <= self.trainer_target_size :
            if self.trainer_target_active: canvas.after(100,self._trainer_spawn_hover_target);return
        x1,y1=random.randint(0,max(0, w-self.trainer_target_size)),random.randint(0,max(0,h-self.trainer_target_size))
        self.trainer_target_coords=(x1,y1,x1+self.trainer_target_size,y1+self.trainer_target_size)
        self.trainer_target_id=canvas.create_oval(x1,y1,x1+self.trainer_target_size,y1+self.trainer_target_size,fill="red",outline="black", tags="target")
        self.is_target_hit_and_waiting_for_respawn=False

    def _draw_mouse_trail(self):
        if self.current_mode.get() != "Mouse" or not hasattr(self, 'trainer_active_tk_canvas') or not self.trainer_active_tk_canvas or not self.trainer_active_tk_canvas.winfo_exists(): return
        canvas = self.trainer_active_tk_canvas
        for trail_id in self.mouse_trail_ids:
            try: canvas.delete(trail_id)
            except tk.TclError: pass
        self.mouse_trail_ids.clear()
        if len(self.mouse_trail_points) > 1:
            trail_color = "lightgrey" if ctk.get_appearance_mode() == "Dark" else "darkgrey"
            line_coords = []; [line_coords.extend(point) for point in self.mouse_trail_points]
            if line_coords:
                line_id = canvas.create_line(line_coords, fill=trail_color, width=2, tags="trail", smooth=True, splinesteps=5)
                self.mouse_trail_ids.append(line_id)

    def start_click_accuracy(self):
        if self.current_mode.get() != "Mouse": return
        self._trainer_clear_canvas_content()
        self.trainer_target_active = True
        self.trainer_game_mode = 'click'
        if hasattr(self, 'instructions_label_trainer'): self.instructions_label_trainer.configure(text="Click target with correct button (LC/RC)!")
        self.trainer_target_hits,self.trainer_target_misses=0,0
        self.trainer_score_display_var.set(f"Hits: {self.trainer_target_hits} Misses: {self.trainer_target_misses}")
        host = self._setup_trainer_content_host()
        if not host: return
        canvas_bg = self._get_themed_canvas_bg()
        self.trainer_active_tk_canvas = tk.Canvas(host, bg=canvas_bg, highlightthickness=0)
        self.trainer_active_tk_canvas.pack(fill=tk.BOTH, expand=True)
        self.trainer_click_target_id,self.trainer_click_target_text_id=None,None
        self.trainer_active_tk_canvas.after(50,self._trainer_spawn_click_target)
        self.trainer_active_tk_canvas.bind("<Button-1>",lambda e:self._trainer_on_canvas_click(e,"left"))
        self.trainer_active_tk_canvas.bind("<Button-3>",lambda e:self._trainer_on_canvas_click(e,"right"))

    def _trainer_spawn_click_target(self):
        if self.current_mode.get() != "Mouse" or not self.trainer_target_active or not hasattr(self,'trainer_active_tk_canvas') or \
           not self.trainer_active_tk_canvas or not self.trainer_active_tk_canvas.winfo_exists(): return
        canvas = self.trainer_active_tk_canvas
        if self.trainer_click_target_id: 
            try: canvas.delete(self.trainer_click_target_id)
            except tk.TclError: pass
        if self.trainer_click_target_text_id: 
            try: canvas.delete(self.trainer_click_target_text_id)
            except tk.TclError: pass
        canvas.update_idletasks();w,h=canvas.winfo_width(),canvas.winfo_height()
        if w<=60 or h<=60:
            if self.trainer_target_active: canvas.after(100,self._trainer_spawn_click_target);return
        rad=30;x,y=random.randint(rad,max(rad, w-rad)),random.randint(rad,max(rad, h-rad))
        self.trainer_click_target_button_type_expected=random.choice(["left","right"])
        clr="dodgerblue" if self.trainer_click_target_button_type_expected=="left" else "mediumpurple"
        txt="LC" if self.trainer_click_target_button_type_expected=="left" else "RC"
        self.trainer_click_target_id=canvas.create_oval(x-rad,y-rad,x+rad,y+rad,fill=clr,outline="black", tags="target")
        self.trainer_click_target_text_id=canvas.create_text(x,y,text=txt,fill="white",font=("Arial",16,"bold"), tags="target_text")

    def _trainer_on_canvas_click(self,event,clicked_button_type):
        if self.current_mode.get() != "Mouse" or not self.trainer_target_active or not self.trainer_click_target_id or \
           not hasattr(self,'trainer_active_tk_canvas') or not self.trainer_active_tk_canvas or \
           not self.trainer_active_tk_canvas.winfo_exists(): return
        canvas = self.trainer_active_tk_canvas
        try: coords=canvas.coords(self.trainer_click_target_id)
        except tk.TclError: return 
        if not coords:return 

        if coords[0]<event.x<coords[2] and coords[1]<event.y<coords[3]: 
            upd_id_closure,upd_txt_id_closure=self.trainer_click_target_id,self.trainer_click_target_text_id
            self.trainer_click_target_id,self.trainer_click_target_text_id=None,None 
            
            if clicked_button_type==self.trainer_click_target_button_type_expected:
                self.trainer_target_hits+=1; 
                if canvas.winfo_exists() and upd_id_closure in canvas.find_all(): canvas.itemconfig(upd_id_closure,fill="lightgreen")
            else:
                self.trainer_target_misses+=1; 
                if canvas.winfo_exists() and upd_id_closure in canvas.find_all(): canvas.itemconfig(upd_id_closure,fill="orangered")
            
            self.trainer_score_display_var.set(f"Hits: {self.trainer_target_hits} Misses: {self.trainer_target_misses}")
            canvas_ref = canvas 
            def d_respawn_click():
                if canvas_ref.winfo_exists():
                    try:
                        if upd_id_closure in canvas_ref.find_all():canvas_ref.delete(upd_id_closure)
                        if upd_txt_id_closure and upd_txt_id_closure in canvas_ref.find_all():canvas_ref.delete(upd_txt_id_closure)
                    except tk.TclError:pass
                if self.trainer_target_active:self._trainer_spawn_click_target()
            self.root.after(600,d_respawn_click)

    def start_scroll_practice(self):
        self._trainer_clear_canvas_content();self.trainer_target_active=True
        if hasattr(self, 'instructions_label_trainer'): self.instructions_label_trainer.configure(text="Scroll text using your device.")
        self.trainer_score_display_var.set("Scroll Test Active")
        host = self._setup_trainer_content_host()
        if not host: return
        scroll_text_widget=ctk.CTkTextbox(host, wrap=tk.WORD, height=200, font=self.trainer_scroll_font, spacing1=5,spacing2=2,spacing3=10, border_width=1, activate_scrollbars=True)
        scroll_text_widget.pack(side=tk.LEFT,fill=tk.BOTH,expand=True, padx=2, pady=2)
        content="Scroll Practice Area\n\n"+"Scroll using soft sips/puffs.\n\n"+"\n".join([f"Section {i}:\nThis is a sample paragraph...\n" for i in range(1,31)])
        scroll_text_widget.insert(tk.END,content);scroll_text_widget.configure(state=tk.DISABLED)
        self.trainer_active_tk_canvas = None 

    def _add_to_calib_log(self, message):
        if hasattr(self, 'calib_log_text') and self.calib_log_text.winfo_exists():
            self.calib_log_text.configure(state=tk.NORMAL)
            self.calib_log_text.insert(tk.END, message + "\n")
            self.calib_log_text.see(tk.END)
            self.calib_log_text.configure(state=tk.DISABLED)

    def _update_pressure_visualizer(self):
        if not hasattr(self, 'pressure_visualizer_canvas') or not self.pressure_visualizer_canvas.winfo_exists() or not self.is_calibrating_arduino_mode: return
        canvas = self.pressure_visualizer_canvas; canvas_bg = self._get_themed_canvas_bg(); canvas.configure(bg=canvas_bg)
        w = canvas.winfo_width(); h = canvas.winfo_height()
        if w <=1 or h <=1: self.root.after(50, self._update_pressure_visualizer); return
        
        label_area_width = self.pressure_label_area_width; graph_area_x_start = label_area_width 
        graph_area_width = w - label_area_width
        if graph_area_width <=0 : graph_area_width = 1 
        if abs(self.max_history_points - graph_area_width) > 5 or self.max_history_points <= 1 :
           self.max_history_points = graph_area_width
           if self.max_history_points <=0: self.max_history_points = 1
           
        canvas.delete("all"); y_padding = 15
        
        def pressure_to_y(pressure_val):
            graph_height = h - (2 * y_padding)
            if graph_height <= 0: graph_height = 1
            total_range = self.PRESSURE_VIS_MAX - self.PRESSURE_VIS_MIN
            if total_range == 0: total_range = 1
            clamped_val = max(self.PRESSURE_VIS_MIN, min(self.PRESSURE_VIS_MAX, pressure_val))
            normalized_val = (clamped_val - self.PRESSURE_VIS_MIN) / total_range
            return (h - y_padding) - (normalized_val * graph_height)

        text_color = "white" if ctk.get_appearance_mode() == "Dark" else "black"
        current_font = self.font_canvas_threshold_text
        gap_between_text_and_graph = 5

        threshold_params = {
            "HPT": ("red", self.params_tkvars["HPT"].get()),
            "SPT": ("orange", self.params_tkvars["SPT"].get()),
            "NMAX": ("gray60", self.params_tkvars["NMAX"].get()),
            "NMIN": ("gray60", self.params_tkvars["NMIN"].get()),
            "HST": ("deep sky blue", self.params_tkvars["HST"].get())
        }
        for name, (color, value) in threshold_params.items():
            y = pressure_to_y(value)
            canvas.create_line(graph_area_x_start, y, w, y, fill=color, width=1, dash=(6, 3), tags="threshold_line")
            canvas.create_text(graph_area_x_start - gap_between_text_and_graph, y,
                                text=name, fill=color, anchor="e", font=current_font)

        if self.pressure_history:
            points = []
            current_max_history = max(1, int(self.max_history_points))
            step_x = graph_area_width / current_max_history if current_max_history > 0 else 0
            
            drawable_history = self.pressure_history[-current_max_history:]
            for i, pressure_val in enumerate(drawable_history):
                points.extend([graph_area_x_start + (i * step_x), pressure_to_y(pressure_val)])
            
            if len(points) >= 4:
                canvas.create_line(points, fill="cyan", width=2, tags="pressure_line")

    def start_arduino_calibration_mode(self):
        if not self.is_connected: messagebox.showwarning("Not Connected", "Connect to Arduino first.", parent=self.root); return
        self.send_command("START_CALIBRATION\n"); self.is_calibrating_arduino_mode = True
        self.start_arduino_calib_button.configure(state=tk.DISABLED); self.stop_arduino_calib_button.configure(state=tk.NORMAL)
        for btn_key in self.action_buttons: self.action_buttons[btn_key].configure(state=tk.NORMAL)
        self._add_to_calib_log("Arduino calibration stream started."); self.calibration_instructions_label.configure(text="Sensor stream active. Select an action.")
        self.pressure_history = [] ; self._update_pressure_visualizer() 

    def stop_arduino_calibration_mode(self, silent=False):
        if not self.is_connected and not silent : return 
        if self.is_calibrating_arduino_mode or silent: self.send_command("STOP_CALIBRATION\n")
        self.is_calibrating_arduino_mode = False
        if hasattr(self, 'start_arduino_calib_button'): 
            self.start_arduino_calib_button.configure(state=tk.NORMAL); self.stop_arduino_calib_button.configure(state=tk.DISABLED)
            if hasattr(self, 'action_buttons'): 
                for btn_key in self.action_buttons: self.action_buttons[btn_key].configure(state=tk.DISABLED)
            self.calibration_current_value_tkvar.set("Raw Pressure: ---")
            if not silent: self._add_to_calib_log("Arduino calibration stream stopped.")
            if hasattr(self,'calibration_instructions_label'): self.calibration_instructions_label.configure(text="Click 'Start Sensor Stream'.")
        if hasattr(self, 'pressure_visualizer_canvas') and self.pressure_visualizer_canvas.winfo_exists():
             self.pressure_visualizer_canvas.delete("all") 
        self.pressure_history = []

    def start_collecting_samples(self, action_name):
        if not self.is_calibrating_arduino_mode: messagebox.showinfo("Info", "Start Arduino stream first.", parent=self.root); return
        self.calibrating_action_name.set(action_name); self.calibration_samples = []
        self.calibration_instructions_label.configure(text=f"PERFORMING: {action_name.upper()}. Hold pressure for ~3s..."); self._add_to_calib_log(f"--- Recording for {action_name} ---")
        for btn in self.action_buttons.values(): btn.configure(state=tk.DISABLED)
        self.stop_arduino_calib_button.configure(state=tk.DISABLED)
        COLLECTION_DURATION_MS = 3000
        if self._calibration_collect_job: self.root.after_cancel(self._calibration_collect_job)
        self._calibration_collect_job = self.root.after(COLLECTION_DURATION_MS, self.finish_collecting_samples)

    def finish_collecting_samples(self):
        self._calibration_collect_job = None 
        action_name = self.calibrating_action_name.get()
        if action_name:
            self.collected_calibration_data[action_name] = list(self.calibration_samples)
            self._add_to_calib_log(f"Collected {len(self.calibration_samples)} samples for {action_name}.")
            self.calibrating_action_name.set("")
        if self.is_calibrating_arduino_mode: 
            for btn_key in self.action_buttons: self.action_buttons[btn_key].configure(state=tk.NORMAL)
            self.stop_arduino_calib_button.configure(state=tk.NORMAL)
            self.calibration_instructions_label.configure(text="Sensor stream active. Select an action or Stop Stream.")
        else: 
            if hasattr(self, 'calibration_instructions_label'): self.calibration_instructions_label.configure(text="Stream stopped. Start stream to record.")
        if self.collected_calibration_data and hasattr(self, 'analyze_button'): self.analyze_button.configure(state=tk.NORMAL)

    def analyze_calibration_data(self):
        if not self.collected_calibration_data: self._add_to_calib_log("No data collected."); return
        self._add_to_calib_log("\n--- Analysis Results ---")
        stats = {}
        for action, samples in self.collected_calibration_data.items():
            if samples: 
                samples.sort()
                stable_samples = samples[int(len(samples)*0.1) : int(len(samples)*0.9)]
                if not stable_samples: stable_samples = samples
                avg = sum(stable_samples) // len(stable_samples)
                m_min, m_max = min(samples), max(samples)
            else: 
                avg, m_min, m_max = 0,0,0
            stats[action] = {"avg": avg, "min": m_min, "max": m_max, "count": len(samples)}
            self._add_to_calib_log(f"'{action}': Avg={avg}, Min={m_min}, Max={m_max} (Count:{len(samples)})")
        
        try:
            neutral_avg = stats.get("Neutral", {}).get("avg", 0)
            hard_sip_avg = stats.get("Hard Sip", {}).get("avg", DEFAULT_SETTINGS["HST"])
            soft_sip_avg = stats.get("Soft Sip", {}).get("avg", DEFAULT_SETTINGS["NMIN"])
            soft_puff_avg = stats.get("Soft Puff", {}).get("avg", DEFAULT_SETTINGS["SPT"])
            hard_puff_avg = stats.get("Hard Puff", {}).get("avg", DEFAULT_SETTINGS["HPT"])

            new_nmin = neutral_avg - 15
            new_nmax = neutral_avg + 15
            
            new_sst = min(soft_sip_avg, new_nmin - 5)
            new_hst = min(hard_sip_avg, new_sst - 10)
            new_spt = max(soft_puff_avg, new_nmax + 5)
            new_hpt = max(hard_puff_avg, new_spt + 10)

            suggestions = {"HST": new_hst, "NMIN": new_sst, "NMAX": new_nmax, "SPT": new_spt, "HPT": new_hpt}
            
            self._add_to_calib_log("\n--- Suggested Values ---")
            self._add_to_calib_log(f"These are suggestions. Manually fine-tune in 'Tuner' tab.")
            for key, val in suggestions.items():
                 self._add_to_calib_log(f"{key}: {val}")
            
            if messagebox.askyesno("Apply Suggestions?", "Do you want to apply suggested values to the Tuner?\n(NMIN will be set to the Soft Sip Threshold)", parent=self.root):
                for key, val in suggestions.items():
                    if key in self.params_tkvars:
                        self.params_tkvars[key].set(val)
                self._add_to_calib_log("Values applied. Go to Tuner and 'Apply to Arduino'.")
                self._update_pressure_visualizer()
        except Exception as e:
            self._add_to_calib_log(f"Could not generate suggestions. Error: {e}")

    def _app_update_loop(self):
        self._check_osk_toggle_corner()
        self.root.after(200, self._app_update_loop)

    def _check_osk_toggle_corner(self):
        if not self.osk_toggle_enabled_tkvar.get() or self.current_mode_str != "Mouse":
            return
        
        try:
            cooldown_ms = 2000 
            if (time.time() * 1000) - self.last_osk_toggle_time < cooldown_ms:
                return

            mx, my = pyautogui.position()
            hotzone_size = 10 
            is_in_corner = (mx < hotzone_size and my > self.screen_height - hotzone_size)

            if is_in_corner and not self.in_osk_corner:
                self.in_osk_corner = True
                self.last_osk_toggle_time = time.time() * 1000
                pyautogui.hotkey('ctrl', 'win', 'o')
                self.set_status("OSK Toggled via corner hotzone.")
            elif not is_in_corner and self.in_osk_corner:
                self.in_osk_corner = False 

        except Exception:
            pass
            
    def set_status(self, message):
        if hasattr(self, 'status_var'): self.status_var.set(message)

    def on_closing(self):
        if self._trainer_loop_job_id:
            self.root.after_cancel(self._trainer_loop_job_id); self._trainer_loop_job_id = None
        if self._calibration_collect_job: 
            self.root.after_cancel(self._calibration_collect_job); self._calibration_collect_job = None
        if self.is_calibrating_arduino_mode: self.stop_arduino_calibration_mode(silent=True)
        self.trainer_target_active = False
        self.stop_read_thread.set()
        if self.is_connected: self.toggle_connect() 
        self.root.destroy()

if __name__ == "__main__":
    root = ctk.CTk()
    app = IntegratedHybridApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()