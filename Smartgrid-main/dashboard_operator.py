# Import statements: Loads UI library (Tkinter + themed widgets), HTTP requests library, 
# threading/queue/time utilities, and date/time helpers.

import tkinter as tk
from tkinter import ttk, scrolledtext
from tkinter import font as tkfont
import requests
import threading
import queue
import time
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict,Any, Optional
from requests import Session, RequestException
from json import JSONDecodeError
from cybersecurity_algorithm import detect_grid_anomaly

# --- Configuration ---
FIREBASE_URL = "https://smartgrid-harshi-default-rtdb.asia-southeast1.firebasedatabase.app/" # Firebase url
COMMAND_ENDPOINT = FIREBASE_URL + "command.json" # Adds command.json to the end of firebase url
STATUS_ENDPOINT = FIREBASE_URL + ".json" # Adds status.json to the end of firebase url

# DEFENSES
# Small dict mapping three defense names to a label and emoji icon.
# This part of code is displayed in Defense toggle
DEFENSE_INFO = {
    "authentication": {"title": "Authentication Gateway", "icon": "🔑"},
    "firewall": {"title": "Temporal Firewall", "icon": "⏳"},
    "anomaly": {"title": "Anomaly Detection", "icon": "📈"}
}

class OperatorDashboardApp:
    def __init__(self, root):
        # Saves root (Tk window), sets title/size/background.
        self.root = root
        self.root.title("OPERATOR DASHBOARD [SECURE TERMINAL]")
        #self.root.geometry("1200x820")
        self.root.configure(bg="#2c3e50")
        self.root.minsize(950,650)

        # Creates request_queue (priority queue) for outbound commands and 
        # response_queue for inbound data from network thread.
        self.request_queue = queue.PriorityQueue()
        self.response_queue = queue.Queue()
        # is_running controls the background thread.
        self.is_running = True
        # auth_token is the token placed into outgoing payloads.
        self.auth_token = "SECURE_TOKEN_123"

        # Active blackouts: stores meterID -> expiry datetime
        self.active_blackouts = {}
        self.active_blackouts_lock = threading.Lock()    # new: protect access
        self.blackout_cleanup_interval_ms = 1000         # run interval (ms), configurable
        self._cleanup_after_id = None                    # store after() id so we can cancel/reschedule
        self.blackout_default_duration = 20.0  # seconds (need to change to take input from user)

        # AI memory (used for anomaly detection)
        self.prev_load = 0
        self.prev_generation = 0
        self.displayed_loads = {}

        # NEW response queue controller settings
        self.response_poll_interval_ms = getattr(self, "response_poll_interval_ms", 100)      # normal interval
        self.response_max_items_per_tick = getattr(self, "response_max_items_per_tick", 8)    # max items to handle per tick
        self.response_short_backlog_ms = getattr(self, "response_short_backlog_ms", 20)       # re-run quickly when backlog
        self._response_after_id = None   # will hold after() id so we can cancel on shutdown

        # how old (seconds) a status snapshot can be before considered stale/offline
        self.status_stale_threshold = getattr(self, "status_stale_threshold", 8.0)  # seconds

        # track last successful status timestamp (epoch seconds) for diagnostics
        self._last_status_timestamp_epoch: Optional[float] = None


        # NEW: Logging system defaults
        self.attack_console_max_lines = 2000
        self.attack_log_file = None

        # Calls styling and widget creation function
        self._setup_styles()
        self.create_widgets()

        # Start AI simulation loop
        self.root.after(3000, self.simulate_ai_event)

        # Network thread
        # Starts a background network_thread (daemon) to handle HTTP I/O.
        self.network_thread = threading.Thread(target=self.network_worker, daemon=True)
        self.network_thread.start()

        # process responses and cleanup loops
        self.process_response_queue() # Starts loop (runs every 100ms) to handle responses
        self.root.after(1000, self._cleanup_blackouts_loop) # Expires blackout

        # used to close tkinter window by clicking X(close) button
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Ensure endpoints exist as instance attributes (network_worker expects these)
        self.COMMAND_ENDPOINT = COMMAND_ENDPOINT
        self.STATUS_ENDPOINT = STATUS_ENDPOINT

        # compatibility alias used by _setup_styles
        self._lighten = self._lighten_color

        # thread-safety for active_blackouts
        # self.active_blackouts_lock = threading.Lock() not used because duplicate (remove)

        # maximum number of simultaneous blackout entries to keep in memory/UI
        self.max_active_blackouts = getattr(self, "max_active_blackouts", 200)




    # ---------------------------
    # Payload and network
    # ---------------------------
    # Creates JSON payload to send to Firebase
    def _create_payload(self, command: str, targetID: str="", value: float | int =0.0, include_epoch: bool = True) -> Dict[str, Any]: # Defines a method
        if not isinstance(command, str) or not command: # Check if command is valid string
            raise ValueError("command must be a non-empty string")

        try:
            value_f = float(value) # Convert value to float
        except (TypeError, ValueError):
            raise ValueError("value must be convertible to float")

        now = datetime.now(timezone.utc) # Get current time with timezone
        payload = { # Creates dictionary
            "command": command,
            "targetID": targetID,
            "value": value_f,
            "authToken": getattr(self, "auth_token", None),
            "timestamp_iso": now.isoformat(),          # readable and timezone-aware
            "fromOperator": True,
            "hash": "DISABLED"
        }
        if include_epoch: # Adds epoch timestamp if needed
            payload["timestamp_epoch"] = now.timestamp()

        return payload

    def network_worker(self): # Function runs in background
        # Configurable parameters with same defaults
        poll_interval = getattr(self, "net_poll_interval", 0.5)       # seconds between polls
        send_timeout = getattr(self, "send_timeout", 3.0)             # timeout for PUT
        status_timeout = getattr(self, "status_timeout", 2.0)         # timeout for GET status
        max_send_retries = getattr(self, "max_send_retries", 2)       # retries for sending
        queue_get_timeout = getattr(self, "queue_get_timeout", 0.2)   # short blocking wait
        retry_base_delay = getattr(self, "retry_base_delay", 0.25)    # base backoff seconds
        requeue_on_fail = getattr(self, "requeue_on_fail", True)     # whether to requeue failed payloads

        last_poll_time = 0.0
        session = Session()  # connection pooling

        try:
            while getattr(self, "is_running", False):
                # allow external stop_event if provided (faster shutdown)
                stop_event = getattr(self, "stop_event", None)
                if stop_event is not None and stop_event.is_set():
                    break

                # 1) Send one queued command (non-blocking-ish)
                try:
                    # small timeout so we can periodically check is_running/polling
                    item = self.request_queue.get(timeout=queue_get_timeout)
                except queue.Empty:
                    item = None

                if item is not None:
                    try:
                        # If using a PriorityQueue it will be (priority, payload)
                        if isinstance(item, tuple) and len(item) >= 2:
                            _, payload = item[0], item[1]  # tolerate priority or (prio, payload)
                        # if queue.item is (prio,payload) but sometimes user enqueued differently:
                            if len(item) >= 2:
                                payload = item[1]
                        else:
                            payload = item  # fallback: item itself
                    except Exception:
                        payload = item  # be forgiving

                    # send with limited retries + exponential backoff
                    success = False
                    attempt = 0
                    while attempt <= max_send_retries and not success and getattr(self, "is_running", False):
                        try:
                            attempt += 1
                            session.put(getattr(self, "COMMAND_ENDPOINT"), json=payload, timeout=send_timeout)
                            success = True
                        except RequestException as e:
                            # network/transient error
                            self.log_attack_action(f"Send Error (attempt {attempt}): {e}")
                            if attempt <= max_send_retries:
                                # exponential backoff
                                delay = retry_base_delay * (2 ** (attempt - 1))
                                time.sleep(delay)
                            else:
                                # exhausted retries
                                if requeue_on_fail:
                                    try:
                                        # requeue at end (no priority)
                                        self.request_queue.put((9999, payload))
                                    except Exception:
                                        # if requeue fails, log and drop
                                        self.log_attack_action("Failed to requeue payload after retries")
                                # not raising here — continue main loop

                    # if using task_done pattern (producer used join()), call task_done
                    try:
                        self.request_queue.task_done()
                    except Exception:
                        pass

                # 2) Poll status endpoint at configured interval
                now = time.monotonic()
                if now - last_poll_time >= poll_interval:
                    last_poll_time = now
                    try:
                        resp = session.get(getattr(self, "STATUS_ENDPOINT"), timeout=status_timeout)
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                                try:
                                    ts = None
                                    if isinstance(data, dict):
                                        # prefer explicit epoch
                                        if "timestamp_epoch" in data:
                                            try:
                                                ts = float(data.get("timestamp_epoch"))
                                            except Exception:
                                                ts = None
                                        elif "timestamp_iso" in data:
                                            try:
                                                # fromisoformat may raise; keep it guarded
                                                ts = datetime.fromisoformat(data.get("timestamp_iso")).timestamp()
                                            except Exception:
                                                ts = None
                                    if ts is not None:
                                        try:
                                            self._last_status_timestamp_epoch = ts
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                # push to response queue without blocking indefinitely
                                try:
                                    self.response_queue.put_nowait(data)
                                except queue.Full:
                                    # if response queue is full, drop and log (or block briefly if you prefer)
                                    self.log_attack_action("Response queue full — dropping status update")
                            except JSONDecodeError:
                                self.log_attack_action("Status response JSON decode error")
                        else:
                            # non-200 response: optionally log
                            self.log_attack_action(f"Status poll returned code {resp.status_code}")
                    except RequestException as e:
                        # network error while polling: log at debug/info level
                        # avoid noisy repeated logs; consider tracking consecutive failures to throttle
                        self.log_attack_action(f"Status poll error: {e}")

                # 3) Sleep a short time to yield CPU (avoid 100% busy loop)
                # We already used blocking queue.get(timeout=...) which will sleep,
                # but adding a small sleep here reduces tight loop in case of many iterations.
                time.sleep(0.02)

        except Exception as ex:
            # Last-resort safety — log the exception and exit the thread loop after a short pause.
            try:
                self.log_attack_action(f"Network worker unhandled exception: {ex}")
            except Exception:
                pass
            # small sleep before stopping to avoid crash-loop
            time.sleep(1)
        finally:
            # cleanup session
            try:
                session.close()
            except Exception:
                pass

    # ---------------------------
    # UI creation (single tab)
    # ---------------------------
    def _setup_styles(self) -> Dict[str, object]:
        # ---- style & theme ----
        self.style = ttk.Style()

        # prefer "clam" but fall back to a safe available theme
        preferred = "clam"
        available = self.style.theme_names()
        if preferred in available:
            try:
                self.style.theme_use(preferred)
            except Exception:
                # some platforms/themes may raise — fall back to default
                self.style.theme_use(self.style.theme_use())
        else:
            # choose a safe theme (first available)
            self.style.theme_use(available[0])

        # ---- colors ----
        self.bg_color =      "#1e1e1e"               #"#ecf0f1" white       # main background
        self.accent_color =  "#4ea1ff"               #"#2980b9" blue  # accent / value color
        self.fg_color =      "#ffffff"               #"#333333"  grey  # default foreground for labels

        # ---- fonts (use system-appropriate fallbacks) ----
        if sys.platform.startswith("win"):
            ui_font_family = "Segoe UI"
        elif sys.platform == "darwin":
            ui_font_family = "Helvetica"   # San Francisco isn't always exposed directly
        else:
            ui_font_family = "DejaVu Sans"  # common Linux fallback

        # create Font objects (lets Tk handle DPI scaling)
        self.font_ui = tkfont.Font(family=ui_font_family, size=10)
        self.font_ui_bold = tkfont.Font(family=ui_font_family, size=10, weight="bold")
        self.font_mono = tkfont.Font(family="Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono", size=14, weight="bold")

        # ---- base widget styles (explicit classes) ----
        # Frame background
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("TLabelframe", background=self.bg_color)
        self.style.configure("TLabelframe.Label", background=self.bg_color, foreground=self.fg_color)

        # Labels
        self.style.configure("TLabel",
                            background=self.bg_color,
                            foreground=self.fg_color,
                            font=self.font_ui)

        # Buttons
        self.style.configure("TButton",
                            font=self.font_ui_bold,
                            padding=(6, 4),  # give a bit of padding
                            background = "#2c2c2c",
                            foreground = "#ffffff"
                            )  
        

        # Button visual feedback (hover/active) - map uses theme element states
        try:
            self.style.map("TButton",
                        foreground=[("active", "#ffffff"), ("!disabled", "#ffffff"), ("disabled", "#888")])
                        #background=[("active", "!disabled", self._lighten(self.bg_color, 0.03)),
                                    #("pressed", "!disabled", self._lighten(self.bg_color, -0.03))])
        except Exception:
            # Some themes restrict background mapping, so ignore failures
            pass

        # Entry
        self.style.configure("TEntry",
                            fieldbackground= "#2c2c2c",  #"#ffffff" white
                            background= "#2c2c2c",   #"#ffffff" white
                            foreground = "#ffffff",
                            font=self.font_ui)

        # Treeview (if used)
        self.style.configure("Treeview",
                            background=   "#2c2c2c",       #"#ffffff"  white
                            fieldbackground= "#2c2c2c",    #"#ffffff"  white
                            foreground = "#ffffff",
                            font=self.font_ui)
        self.style.configure("Treeview.Heading", font=self.font_ui_bold)

        # Custom "Value" label style for big numeric values
        self.style.configure("Value.TLabel",
                            background=self.bg_color,
                            font=self.font_mono,
                            foreground=self.accent_color)

        # Optional: set default padding for labels to make layout consistent
        self.style.configure("TLabel", padding=(2, 2))

        # Return commonly used constants for tests or for other parts of app
        constants = {
            "style": self.style,
            "bg_color": self.bg_color,
            "accent_color": self.accent_color,
            "fg_color": self.fg_color,
            "font_ui": self.font_ui,
            "font_ui_bold": self.font_ui_bold,
            "font_mono": self.font_mono
        }
        return constants

    # Helper: small color adjuster (very tiny dependency, placed here for convenience)
    @staticmethod
    def _hex_to_rgb(hexc: str):
        hexc = hexc.lstrip("#")
        return tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _clamp(self, v, a=0, b=255):
        return max(a, min(b, int(v)))

    def _lighten_color(self, hexc: str, amount: float):
        """
        Lighten or darken hex color by a small amount (-0.5..0.5)
        amount > 0 -> lighter, amount < 0 -> darker
        """
        hexc = hexc.lstrip("#")
        r = int(hexc[0:2], 16)
        g = int(hexc[2:4], 16)
        b = int(hexc[4:6], 16)
        r = self._clamp(r + (255 - r) * amount)
        g = self._clamp(g + (255 - g) * amount)
        b = self._clamp(b + (255 - b) * amount)
        return "#{:02x}{:02x}{:02x}".format(r, g, b)

# Attach helper to the module-level so _setup_styles can call it (or bind to self if you prefer)
# If you place this method inside a class, implement self._lighten delegating to _lighten_color().

    def create_widgets(self):
        PAD_X = 12
        PAD_Y = 8
        SMALL_PAD = 6
        LABEL_WIDTH = 24
        STATUS_WIDTH = 10
        BTN_WIDTH = 10

        # container
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # top area
        top = ttk.Frame(container)
        top.pack(fill="both", expand=False)

        left = ttk.Frame(top)
        left.pack(side="left", fill="y", padx=(0,10))

        right = ttk.Frame(top)
        right.pack(side="left", fill="both", expand=True)

        # -------------------------
        # Left: Master Controls + Defense Buttons
        # -------------------------
        master_frame = ttk.LabelFrame(left, text="Master Lighting & Defenses", padding=12)
        master_frame.pack(fill="y", expand=False)

        # Lighting controls
        lc = ttk.LabelFrame(master_frame, text="Master Lighting Control", padding=8)
        lc.pack(fill="x", pady=(0,8))

        # on indicator
        self.cv_on = tk.Canvas(lc, width=28, height=28, bg=self.bg_color, highlightthickness=0)
        self.cv_on.pack(side="left", padx=(6,8))
        self._draw_light_indicator(self.cv_on, "#bdc3c7")

        ttk.Button(lc,
                text="LIGHTS ON",
                width=18,
                command=lambda: self.send_command("SET_LIGHTS", value=1.0)).pack(side="left", padx=6, pady=4)

        # off indicator
        self.cv_off = tk.Canvas(lc, width=28, height=28, bg=self.bg_color, highlightthickness=0)
        self.cv_off.pack(side="left", padx=(6,8))
        self._draw_light_indicator(self.cv_off, "#bdc3c7")

        ttk.Button(lc,
                text="LIGHTS OFF",
                width=18,
                command=lambda: self.send_command("SET_LIGHTS", value=0.0)).pack(side="left", padx=6, pady=4)

        # ------------------------
        # Grid Generation Control
        # ------------------------
        grid_frame = ttk.LabelFrame(master_frame, text="Grid Generation Control", padding= 8)
        grid_frame.pack(fill="x", pady=(6,8))

        self.cv_grid_on = tk.Canvas(grid_frame, width=28, height=28, bg= self.bg_color, highlightthickness=0)
        self.cv_grid_on.pack(side="left", padx=(6,8))
        self._draw_light_indicator(self.cv_grid_on, "#bdc3c7")

        ttk.Button(
            grid_frame,
            text="GRID ON",
            width=18,
            command= lambda: self.send_command("GRID_ON")
        ).pack(side="left", padx=6, pady=4)

        self.cv_grid_off = tk.Canvas(grid_frame, width=28, height=28, bg=self.bg_color, highlightthickness=0)
        self.cv_grid_off.pack(side="left", padx=(10,8))
        self._draw_light_indicator(self.cv_grid_off, "#bdc3c7")

        ttk.Button(
            grid_frame,
            text= "GRID OFF",
            width=18,
            command= lambda: self.send_command("GRID_OFF")
        ).pack(side="left", padx=6, pady=4)

        # Defense buttons
        def_frame = ttk.LabelFrame(master_frame, text="Defense Toggles", padding=8)
        def_frame.pack(fill="x", pady=(6,8))

        self.def_buttons = {}
        self.def_labels = {}

        for key in ["authentication", "firewall", "anomaly"]:
            sub = ttk.Frame(def_frame)
            sub.pack(fill="x", pady=4)

            lbl_icon = ttk.Label(sub, text=f"{DEFENSE_INFO[key]['icon']} {DEFENSE_INFO[key]['title']}", width=LABEL_WIDTH, anchor="w")
            lbl_icon.pack(side="left")

            st = ttk.Label(sub, text="UNKNOWN", width=STATUS_WIDTH)
            st.pack(side="left", padx=(6,6))
            self.def_labels[key] = st

            btn = ttk.Button(sub, text="Toggle", width=BTN_WIDTH, command=lambda k=key: self.send_command("SET_DEFENSE", targetID=k))
            btn.pack(side="right")
            self.def_buttons[key] = btn

        # -------------------------
        # AI Monitoring Panel
        # -------------------------
        ai_frame = ttk.LabelFrame(master_frame, text="AI Monitoring", padding= 8)
        ai_frame.pack(fill="x",pady=(10,0))
        ai_frame.configure(height=120)

        # AI status summary
        self.ai_mode_label = ttk.Label(ai_frame, text="Mode: Monitoring")
        self.ai_mode_label.pack(anchor="w", pady=(2,0))

        self.ai_threat_label = ttk.Label(ai_frame, text="Threat Level: SAFE")
        self.ai_threat_label.pack(anchor="w", pady=(2,0))

        self.ai_last_detection_label = ttk.Label(ai_frame, text="Last Detection: None")
        self.ai_last_detection_label.pack(anchor="w", pady=(2,0))

        self.ai_last_action_label = ttk.Label(ai_frame, text="Last Action: None")
        self.ai_last_action_label.pack(anchor="w", pady=(2,0))

        # AI Confidence Bar
        self.ai_confidence_label = ttk.Label(ai_frame, text="Anomaly Risk: 0%")
        self.ai_confidence_label.pack(anchor="w", pady=(6,0))

        self.ai_confidence_bar = ttk.Progressbar(
            ai_frame,
            orient="horizontal",
            length=200,
            mode="determinate"
        )
        self.ai_confidence_bar.pack(fill="x", pady=(2,4))
        self.ai_confidence_bar["value"] = 0

        # AI Activity Feed
        self.ai_feed_label = ttk.Label(ai_frame, text="AI Activity: ")
        self.ai_feed_label.pack(anchor="w", pady=(6,0))

        self.ai_feed = tk.Text(
            ai_frame,
            height=4,
            width=50,
            wrap="word",
            bg="#000000",
            fg="#00ffcc",
            font=self.font_mono,
            borderwidth=0
        )
        self.ai_feed.pack(fill="x", pady=(2,4))
    
        # -------------------------
        # Right: Meters table + Attack console
        # -------------------------
        meters_frame = ttk.LabelFrame(right, text="Meters & Grid Status", padding=8)
        meters_frame.pack(fill="both", expand=True)

        # top metrics row
        metrics = ttk.Frame(meters_frame)
        metrics.pack(fill="x", pady=(0,8))

        ttk.Label(metrics, text="Generation Output:").pack(side="left", padx=(4,6))
        self.lbl_gen = ttk.Label(metrics, text="0.00 kW", style="Value.TLabel")
        self.lbl_gen.pack(side="left", padx=(0,18))

        ttk.Label(metrics, text="Current Load:").pack(side="left", padx=(4,6))
        self.lbl_con = ttk.Label(metrics, text="0.00 kW", style="Value.TLabel")
        self.lbl_con.pack(side="left", padx=(0,18))

        ttk.Label(metrics, text="System Status:").pack(side="left", padx=(4,6))
        self.lbl_status = ttk.Label(metrics, text="WAITING", font=("Segoe UI", 12, "bold"))
        self.lbl_status.pack(side="left", padx=(0,6))

        # ----- Reset Button -----
        self.btn_reset_trip = ttk.Button(
            metrics,
            text= "RESET TRIP",
            width= 12,
            command= lambda: self.send_command("RESET_TRIP")
        )
        self.btn_reset_trip.pack(side="left", padx=(10,0))

        # meters table
        cols = ("id", "loc", "val")
        self.tree = ttk.Treeview(meters_frame, columns=cols, show="headings", height=12)
        self.tree.heading("id", text="Meter ID"); self.tree.column("id", width=140)
        self.tree.heading("loc", text="Building"); self.tree.column("loc", width=120)
        self.tree.heading("val", text="Load (kW)"); self.tree.column("val", width=120)
        self.tree.pack(fill="both", expand=False, pady=(0,8))

        # bottom: attack console (no blackout panel)
        bottom = ttk.Frame(meters_frame)
        bottom.pack(fill="both", expand=True)

        # Blackout list panel (left side)
        blackout_frame = ttk.LabelFrame(bottom, text="Active Outages", padding=6)
        blackout_frame.pack(side="left", fill="y", padx=(8,0))

        self.blackout_listbox = tk.Listbox(
            blackout_frame,
            height=12,
            width=32,
            font=("Consolas", 10)
        )
        self.blackout_listbox.pack(fill="both", expand=False)

        # ------------------
        # Warning Lights
        # ------------------

        # ------ Capacity Warning ------

        warning_frame = ttk.LabelFrame(blackout_frame, text="Warning", padding=6)
        warning_frame.pack(fill="x", pady=(10,0))

        # container for warning indicators
        warning_row = ttk.Frame(warning_frame)
        warning_row.pack(anchor="w")

        # warning bulb
        self.cv_capacity_warning = tk.Canvas(
            warning_row,
            width=28,
            height=28,
            bg=self.bg_color,
            highlightthickness=0
        )
        self.cv_capacity_warning.pack(anchor="w")

        # draw default OFF state
        self._draw_light_indicator(self.cv_capacity_warning, "#000000")

        # small label under bulb
        ttk.Label(
            warning_row,
            text="Max \nGen",
            font=("Segoe UI", 8),
            justify= "center"
        ).pack(anchor="w", pady=(0,4))

        attack_pan = ttk.LabelFrame(bottom, text="Console", padding=6)
        attack_pan.pack(side="left", fill="both", expand=True)

        # Use instance color constants so dark-mode can update these later
        attack_bg = getattr(self, "attack_bg", "#000")
        attack_fg = getattr(self, "attack_fg", "#f39c12")
        self.attack_console = scrolledtext.ScrolledText(
            attack_pan,
            height=12,
            bg=attack_bg,
            fg=attack_fg,
            font=(self.font_mono.actual("family"), 10),
            wrap = "word",
            padx = 6, pady = 4,
            borderwidth = 0
        )
        self.attack_console.pack(fill="both", expand=True)
        
        # Apply non-ttk widget theming (useful for dark mode toggles)
        try:
            self._apply_non_ttk_theme()
        except Exception:
            pass
    def simulate_ai_event(self):

        # ---- Real GRID DATA based risk

        # Get current generation and load from UI labels
        try:
            generation = float(self.lbl_gen.cget("text").replace(" kW", ""))
            load = float(self.lbl_con.cget("text").replace(" kW", ""))
        except:
            generation = 0.0
            load = 0.0
        
        # Get defense states
        defenses = {
        "authGateway": self.def_labels["authentication"].cget("text") == "ACTIVE",
        "firewall": self.def_labels["firewall"].cget("text") == "ACTIVE",
        "anomalyDetection": self.def_labels["anomaly"].cget("text") == "ACTIVE"
        }

        # Call cybersecurity detection algorithm
        grid_state = self.lbl_status.cget("text")

        

        # Fix initial spike issue
        if self.prev_load == 0:
            self.prev_load = load
            self.prev_generation = generation
            # Schedule next cycle before exiting
            self.root.after(3000, self.simulate_ai_event)
            return

        risk, detection, action = detect_grid_anomaly(
            load,
            generation,
            self.prev_load,
            grid_state,
            defenses
        )
        
        # risk = 0

        # # Rule 1: Overload Conditon
        # if generation > 0:
        #     load_ratio = load / generation
        #     if load_ratio > 0.9:
        #         risk += 50
        #     elif load_ratio > 0.75:
        #         risk += 30

        # # Rule 2: System Offline
        # if self.lbl_status.cget("text") == "OFFLINE":
        #     risk += 40

        # # Rule 3: Active attack increases risk
        # if hasattr(self, "current_attack"):
        #     if self.current_attack.upper() == "OVERLOAD":
        #         risk +=40
        
        # # Rule 4: Defense disabled increases vulnerability
        # if self.def_labels["authentication"].cget("text") == "DISABLED":
        #     risk += 15

        # if self.def_labels["firewall"].cget("text") == "DISABLED":
        #     risk += 15

        # if self.def_labels["anomaly"].cget("text") == "DISABLED":
        #     risk += 10

        # # Rule 5: Load Spike detection
        # load_change = load - self.prev_load

        # if load_change > 80:
        #     risk += 40

        # # Rule 6: Grid overload detection
        # if generation > 0:
        #     load_ratio = load / generation

        #     if load_ratio > 1.1:
        #         risk += 50

        # Clamp risk to 100
        risk = min(risk, 100)

        # Determine threat level
        if risk <= 25:
            threat = "SAFE"
            color = "#2ecc71"

        elif risk <= 50:
            threat = "SUSPICIOUS"
            color = "#f1c40f"

        elif risk <= 75:
            threat = "HIGH RISK"
            color = "#e67e22"

        else:
            threat = "CRITICAL"
            color = "#e74c3c"

        # Update confidence bar
        self.ai_confidence_bar["value"] = risk
        self.ai_confidence_label.config(text=f"Anomaly Risk: {risk}%")

        self.ai_threat_label.config(
            text=f"Threat Level: {threat}",
            foreground=color
        )

        timestamp = datetime.now().strftime("%H:%M:%S")
        # detection = "Normal"
        # action = "Monitoring System"

        # self.ai_last_detection_label.config(text=f"Last Detection: {detection}")
        # self.ai_last_action_label.config(text=f"Last Action: {action}")

        # Detection priority: Attack first
        attack_label = "NONE"

        if hasattr(self, "current_attack"):
            attack_label = self.current_attack.upper()

        # --------------------------------
        # AI Decision Engine (Improved)
        # --------------------------------

        if risk < 20:
            ai_decision = "System Stable - No action required"

        elif 20 <= risk < 50:
            ai_decision = "Monitor system closely"

        elif 50 <= risk < 75:
            if "Instability" in detection:
                ai_decision = "Stabilize power generation"
            else:
                ai_decision = "Investigate abnormal behavior"

        elif 75 <= risk < 90:
            if "Overload" in detection:
                ai_decision = "Reduce load immediately"
            elif "Load Injection" in detection:
                ai_decision = "Enable firewall and inspect meters"
            else:
                ai_decision = "Activate partial defenses"

        else:  # risk >= 90
            ai_decision = "CRITICAL: Activate all defenses immediately"

        # Update Labels
        self.ai_last_detection_label.config(text=f"Detection: {detection} | Attack: {attack_label}")
        self.ai_last_action_label.config(text=f"Last Action: {action}")

        # Log AI to feed
        self.ai_feed.insert("end", f"[{timestamp}] Risk={risk}% | {detection} | {action} | AI Decision: {ai_decision}\n")
        self.ai_feed.see("end")

        self.prev_load = load
        self.prev_generation = generation

        self.root.after(3000, self.simulate_ai_event)



    # ---------------------------
    # UI helpers & logging
    # ---------------------------
    def _draw_light_indicator(self,
                          canvas: tk.Canvas,
                          color: str,
                          size: int = 28,
                          border: str = "#7f8c8d",
                          outline_width: int = 1,
                          glow: bool = False,
                          blink: bool = False,
                          blink_interval: int = 600):
        # Cancel any previous blink job stored on the canvas
        try:
            if hasattr(canvas, "_blink_job") and canvas._blink_job is not None:
                canvas.after_cancel(canvas._blink_job)
                canvas._blink_job = None
        except Exception:
            pass

        # Compute coordinates with a small padding
        padding = 2
        w = size
        h = size
        x0, y0 = padding, padding
        x1, y1 = padding + w, padding + h

        # Keep consistent tag names so we can update/replace only those items
        tag_outer = "indicator_outer"
        tag_inner = "indicator_inner"
        tag_glow = "indicator_glow"

        # Remove previous indicator drawings only (don't clear entire canvas)
        canvas.delete(tag_outer)
        canvas.delete(tag_inner)
        canvas.delete(tag_glow)

        # Outer ring (frame)
        canvas.create_oval(x0, y0, x1, y1, outline=border, width=outline_width, tags=(tag_outer,))

        # Inner filled circle with small inset
        inset = max(3, int(size * 0.18))
        canvas.create_oval(x0 + inset, y0 + inset, x1 - inset, y1 - inset,
                        fill=color, outline=color, tags=(tag_inner,))

        # Optional glow: draw a larger, low-opacity-like ring (Tk doesn't support alpha)
        # So we simulate a glow by drawing a slightly larger ring with a lighter color.
        if glow:
            try:
                glow_amount = 0.08  # small lightening factor
                lighter = self._lighten_color(color, glow_amount)  # assumes you have _lighten_color
            except Exception:
                lighter = color
            glow_padding = max(1, int(size * 0.08))
            canvas.create_oval(x0 - glow_padding, y0 - glow_padding,
                               x1 + glow_padding, y1 + glow_padding,
                               outline=lighter, width=max(1, outline_width), tags=(tag_glow,))

        # Resize the canvas to fit the indicator if necessary
        try:
            canvas.config(width=size + padding*2, height=size + padding*2)
        except Exception:
            pass

        # Blink animation (toggle inner circle visibility)
        if blink:
            # initial visible state
            canvas.itemconfigure(tag_inner, state="normal")

            def _toggle_blink():
                cur_state = canvas.itemcget(tag_inner, "state")
                new_state = "hidden" if cur_state == "normal" else "normal"
                try:
                    canvas.itemconfigure(tag_inner, state=new_state)
                except Exception:
                    pass
                # schedule next toggle and remember job id on canvas
                canvas._blink_job = canvas.after(blink_interval, _toggle_blink)

            # start toggling
            canvas._blink_job = canvas.after(blink_interval, _toggle_blink)
        else:
            # Ensure inner item is visible if not blinking
            try:
                canvas.itemconfigure(tag_inner, state="normal")
            except Exception:
                pass
            canvas._blink_job = None

        # Optional: return the tag names or the ids if caller wants them
        return {"outer_tag": tag_outer, "inner_tag": tag_inner, "glow_tag": tag_glow}

    def _append_attack_log(self, msg):
        """
        Deprecated helper kept for compatibility.
        Delegates to append_attack_log which is thread-safe.
        """
        self.append_attack_log(msg, level="INFO")
    
    def append_attack_log(self, msg: str, level: str = "INFO"):
        """
        Public, thread-safe method to append a log line to the attack console.
        Safe to call from background threads. level: "INFO","WARNING","ERROR","CRITICAL","DEFENSE".
        """
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"[{ts}] {msg}\n"

        try:
            # If already on GUI thread, insert directly (faster)
            if threading.current_thread() is threading.main_thread():
                self._insert_attack_text(text, level)
            else:
            # schedule insertion on GUI thread
                self.root.after(0, self._insert_attack_text, text, level)
        except Exception:
            # best effort fallback: try scheduling, otherwise print to stdout so logs aren't lost
            try:
                self.root.after(0, self._insert_attack_text, text, level)
            except Exception:
                print(text, end="")
    def _insert_attack_text(self, text: str, level: str):
        """
        Inserts text into the ScrolledText attack console.
        Must run on GUI thread. Handles tag setup, trimming and optional file write.
        """
        # lazy tag configuration
        if not getattr(self, "_attack_console_tags_configured", False):
            try:
                self.attack_console.tag_configure("INFO", foreground=getattr(self, "attack_fg", "#f39c12"))
                self.attack_console.tag_configure("DEFENSE", foreground="#9b59b6")
                self.attack_console.tag_configure("WARNING", foreground="#f39c12")
                # ERROR and CRITICAL get bolder font; font_mono should exist from _setup_styles
                self.attack_console.tag_configure(
                    "ERROR",
                    foreground="#e74c3c",
                    font=(self.font_mono.actual("family"), 10, "bold")
                )
                self.attack_console.tag_configure(
                    "CRITICAL",
                    foreground="#ffffff",
                    background="#c0392b",
                    font=(self.font_mono.actual("family"), 10, "bold")
                )
            except Exception:
                # tag config may fail in some headless/test environments; ignore
                pass
            self._attack_console_tags_configured = True

        # enable, insert, disable — keep the widget read-only for users
        try:
            self.attack_console.configure(state="normal")
        except Exception:
            pass

        tag = (level or "INFO").upper() if isinstance(level, str) else "INFO"
        if tag not in ("INFO", "DEFENSE", "WARNING", "ERROR", "CRITICAL"):
            tag = "INFO"

        try:
            # preferred: insert with tag (colored)
            self.attack_console.insert("end", text, tag)
            self.attack_console.see("end")
        except Exception:
            # fallback: try without tag
            try:
                self.attack_console.insert("end", text)
                self.attack_console.see("end")
            except Exception:
                # ultimate fallback: print to stdout
                print(text, end="")

        # trim old lines to keep the widget responsive
        try:
            max_lines = int(getattr(self, "attack_console_max_lines", 2000) or 2000)
            idx = self.attack_console.index("end-1c")
            if isinstance(idx, str) and "." in idx:
                num_lines = int(idx.split(".")[0])
            else:
                num_lines = 1
            if num_lines > max_lines:
                self.attack_console.delete("1.0", f"{num_lines - max_lines + 1}.0")
        except Exception:
            pass

        try:
            self.attack_console.configure(state="disabled")
        except Exception:
            pass

        # optional persistent logging
        logfile = getattr(self, "attack_log_file", None)
        if logfile:
            try:
                with open(logfile, "a", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass

    def log_attack_action(self, msg):
        """
        Route defense messages here as well.
        Uses the thread-safe append_attack_log so callers from background threads are safe.
        """
        # defense messages use a separate tag
        self.append_attack_log(msg, level="DEFENSE")

    # ---------------------------
    # Commands: send to firebase
    # ---------------------------
    def send_command(self, cmd: str, targetID: str = "", value: float = 0.0, priority: int = 1):

        try:
            if cmd == "SET_LIGHTS":
                requests.put(
                    FIREBASE_URL + "command.json",
                    json={
                        "command": "SET_LIGHTS",
                        "value": value
                    }
                )

                state = "ON" if value == 1.0 else "OFF"
                self.append_attack_log(f"Command Sent: LIGHTS {state}", "INFO")

            elif cmd == "BLACKOUT":
                requests.patch(
                    FIREBASE_URL + "grid.json",
                    json={"attack": "BLACKOUT"}
                )

            elif cmd == "CLEAR_ATTACK":
                requests.patch(
                    FIREBASE_URL + "grid.json",
                    json={"attack": "NONE"}
                )


            elif cmd == "SET_DEFENSE":
                requests.put(FIREBASE_URL + "command.json", json={"command": "SET_DEFENSE", "targetID": targetID})
                defense_name = DEFENSE_INFO.get(targetID, {}).get("title", targetID)

                self.append_attack_log(f"Command Sent: {defense_name}", "INFO")
            
            elif cmd == "GRID_ON":
                requests.put(
                    FIREBASE_URL + "command.json",
                    json={"command": "GRID_ON"}
                )
                self.append_attack_log("Command Sent: GRID ON", "INFO")

            elif cmd == "GRID_OFF":
                requests.put(
                    FIREBASE_URL + "command.json",
                    json={"command": "GRID_OFF"}
                )
                self.append_attack_log("Command Sent: GRID OFF", "INFO")

            elif cmd == "RESET_TRIP":
                requests.put(
                    FIREBASE_URL + "command.json",
                    json={"command": "RESET_TRIP"}
                )
                self.append_attack_log("Command Sent: RESET TRIP", "INFO")

        except Exception as e:
            self.append_attack_log(f"Send failed: {e}", "ERROR")


    # ---------------------------
    # Response processing
    # ---------------------------
    def process_response_queue(self):
        """
        Process a bounded number of items from response_queue on the GUI thread,
        then schedule the next run adaptively (short delay if backlog remains).
        """
        try:
            processed = 0
            max_items = getattr(self, "response_max_items_per_tick", 8)

            while processed < max_items:
                try:
                    data = self.response_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    if data:
                        # Safe update_dashboard
                        try:
                            self.update_dashboard(data)
                        except Exception as e:
                            try:
                                self.append_attack_log(f"update_dashboard failed: {e}", "ERROR")
                            except Exception:
                                pass

                        # Safe process_logs
                        try:
                            self.process_logs(data.get("log", ""))
                        except Exception as e:
                            try:
                                self.append_attack_log(f"process_logs failed: {e}", "ERROR")
                            except Exception:
                                pass

                finally:
                    try:
                        self.response_queue.task_done()
                    except Exception:
                        pass

                processed += 1

        finally:
            # If app running, schedule next tick
            if getattr(self, "is_running", False):
                try:
                    backlog = not self.response_queue.empty()
                except Exception:
                    backlog = False

                # adaptive delay
                if backlog:
                    next_delay = getattr(self, "response_short_backlog_ms", 20)
                else:
                    next_delay = getattr(self, "response_poll_interval_ms", 100)

                try:
                    self._response_after_id = self.root.after(next_delay, self.process_response_queue)
                except Exception:
                    # fallback to default
                    try:
                        self._response_after_id = self.root.after(100, self.process_response_queue)
                    except Exception:
                        self._response_after_id = None
            else:
                # no scheduling when not running
                try:
                    if self._response_after_id is not None:
                        self.root.after_cancel(self._response_after_id)
                except Exception:
                    pass
                self._response_after_id = None

    def process_logs(self, log_msg):
        """
        Parse a single log message from the backend and route it to the attack console,
        optionally adding targeted blackouts when detected.

        Improvements:
        - Accepts non-string values (converts to string or warns)
        - Uses a single uppercase copy for matching (efficient)
        - Avoids duplicate logging
        - Uses timezone-aware expiry datetimes (UTC)
        """

        # Quick validation & normalization
        if log_msg is None:
            return

        if not isinstance(log_msg, str):
            try:
                log_msg = str(log_msg)
            except Exception:
                # Could not turn it into a string — warn and skip
                self.append_attack_log("Received non-string log (unreadable).", "WARNING")
                return

        log_msg = log_msg.strip()
        if not log_msg:
            return

        # Prepare uppercase copy for case-insensitive checks
        lm = log_msg.upper()

        # Define keywords (uppercase for consistency)
        attack_keywords = ("CRITICAL", "BLACKOUT", "DDOS", "INSTABILITY", "TAMPER", "DDOS")  # ensure uppercase
        defense_marker = "[DEFENSE]"

        # Track whether we've already logged this message to avoid duplicates
        logged = False

        # 1) Defense marker (special tag)
        if defense_marker in lm:
            # Use defense-specific routing
            self.log_attack_action(log_msg)   # log_attack_action uses DEFENSE tag
            logged = True

        # 2) Attack keyword detection (case-insensitive)
        if any(k in lm for k in attack_keywords):
            # If it was not already logged as DEFENSE, log it now.
            if not logged:
                # Use DEFENSE routing for attack messages as well (you can change level here)
                self.log_attack_action(log_msg)
                logged = True

            # Try to extract targeted blackout meter information
            # Look for "METER:" then take the following token as meter id (tolerant to punctuation)
            if "METER:" in lm or "TARGETED BLACKOUT" in lm:
                # find METER: if present, else try to find a token after the phrase "TARGETED BLACKOUT"
                meter_id = None
                start = lm.find("METER:")
                if start != -1:
                    rest = log_msg[start + len("METER:"):].strip()
                    # first token usually meter id; strip common trailing punctuation
                    parts = rest.split()
                    if parts:
                        meter_id = parts[0].strip(").,;:\"'")
                else:
                    # fallback: try to find a token after "TARGETED BLACKOUT"
                    idx = lm.find("TARGETED BLACKOUT")
                    if idx != -1:
                        rest = log_msg[idx + len("TARGETED BLACKOUT"):].strip()
                        parts = rest.split()
                        if parts:
                            meter_id = parts[0].strip(").,;:\"'")

                if meter_id:
                    # Use timezone-aware expiry (UTC) to be consistent across the app
                    expiry = datetime.now(timezone.utc) + timedelta(seconds=self.blackout_default_duration)
                    self._add_active_blackout(meter_id, expiry)

        # 3) If nothing matched earlier, log as info (avoid double-logging)
        if not logged:
            # For general logs, use the standard append (INFO/DEFENSE as you prefer)
            self.log_attack_action(log_msg)

    # ---------------------------
    # Dashboard updater
    # ---------------------------
    def update_dashboard(self, data):
        """
        Safely update the UI from a backend status dict.

        Improvements:
        - Validates input
        - Skips update if snapshot identical (simple de-dup)
        - Incremental Treeview updates (update/insert/delete) to avoid full redraw
        - Robust error handling and logging
        """

        # Validate type quickly (do not crash GUI thread if backend sends wrong payload)
        if not isinstance(data, dict):
            try:
                # try to coerce common serializable types (e.g., JSON objects may be dict already)
                data = dict(data)
            except Exception:
                self.append_attack_log(f"update_dashboard: unexpected data type {type(data)}", "WARNING")
                return

        def safe_float(v, default=0.0):
            try:
                return float(v)
            except Exception:
                return default

        def do_update():
            try:
                # ----- freshness check: parse timestamp in payload -----
                now_utc = datetime.now(timezone.utc)
                stale_threshold = float(getattr(self, "status_stale_threshold", 8.0))
                # prefer epoch if present, else try iso parse
                ts_epoch = None
                if isinstance(data, dict):
                    if "timestamp_epoch" in data:
                        try:
                            ts_epoch = float(data.get("timestamp_epoch"))
                        except Exception:
                            ts_epoch = None
                    elif "timestamp_iso" in data:
                        try:
                            ts_epoch = datetime.fromisoformat(data.get("timestamp_iso")).timestamp()
                        except Exception:
                            ts_epoch = None
                is_stale = True
                if ts_epoch is not None:
                    try:
                        snapshot_time = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                        age = (now_utc - snapshot_time).total_seconds()
                        is_stale = age > stale_threshold
                    except Exception:
                        is_stale = True
                else:
                    # no timestamp in payload — treat as stale for safety
                    is_stale = True
                if is_stale:
                    # # Mark UI as offline/stale and avoid applying stale meter data
                    # try:
                    #     self.lbl_status.config(text="OFFLINE", foreground="#c0392b")
                    #     # dim indicators
                    #     try:
                    #         self._draw_light_indicator(self.cv_on, "#7f8c8d")
                    #         self._draw_light_indicator(self.cv_off, "#7f8c8d")
                    #     except Exception:
                    #         pass
                    #     # mark defense labels as stale
                    #     for key in ["authentication", "replay", "anomaly"]:
                    #         lbl = self.def_labels.get(key)
                    #         if lbl:
                    #             lbl.config(text="STALE", foreground="#7f8c8d")
                    # except Exception:
                    #     pass
                    # try:
                    #     self.append_attack_log(f"Status snapshot stale (>{stale_threshold}s) — showing OFFLINE.", "WARNING")
                    # except Exception:
                    #     pass
                    # # Do not apply stale meters/values; return early.
                    # return
                    pass
                try:
                    # --- basic numeric labels ---
                    grid = data.get("grid", {})
                    total_generation = safe_float(grid.get("totalGeneration", 0.0), 0.0)
                    self.lbl_gen.config(text=f"{total_generation:.2f} kW")

                    # --- build meter map from incoming data ---
                    devices_dict = data.get("devices", {}) or {}
                    incoming = {}

                    for key, devices_data in devices_dict.items():
                        if key.startswith("meter_"):
                            meter_id = key
                            loc = key #using meter id as zone
                            real_val = float(devices_data.get("power_consumption", 0.0))

                            # Get previous displayed value
                            prev_val = self.displayed_loads.get(meter_id, real_val)

                            # Apply LERP smoothing
                            smooth_val = prev_val + (real_val - prev_val) * 0.2

                            # Store for next frame
                            self.displayed_loads[meter_id] = smooth_val

                            val = smooth_val
                            incoming[meter_id] = (loc, val)

                    # --- incremental treeview update (avoid full clear) ---
                    # Build current tree mapping: meter_id -> item_id
                    existing = {}
                    for item in self.tree.get_children():
                        vals = self.tree.item(item, "values") or ()
                        if len(vals) >= 1:
                            existing_id = str(vals[0])
                            existing[existing_id] = item

                    # Update existing rows and mark seen
                    seen = set()
                    for meter_id, (loc, val) in incoming.items():
                        if meter_id in existing:
                            item_id = existing[meter_id]
                            # update only if values changed
                            cur_vals = self.tree.item(item_id, "values") or ()
                            cur_val_num = safe_float(cur_vals[2] if len(cur_vals) >= 3 else 0.0, 0.0)
                            if cur_val_num != val or (len(cur_vals) >= 2 and cur_vals[1] != loc):
                                self.tree.item(item_id, values=(meter_id, loc, f"{val:.2f}"))
                        else:
                            # new meter — insert
                            self.tree.insert("", "end", values=(meter_id, loc, f"{val:.2f}"))
                        seen.add(meter_id)

                    # Remove stale rows that are not in incoming
                    for existing_id, item_id in list(existing.items()):
                        if existing_id not in seen:
                            try:
                                self.tree.delete(item_id)
                            except Exception:
                                pass

                    # --- total load & status ---
                    total_load = float(grid.get("totalLoad", 0.0))
                    self.lbl_con.config(text=f"{total_load:.2f} kW")

                    status = str(grid.get("gridStatus", "UNKNOWN") or "UNKNOWN")
                    self.lbl_status.config(text=status, foreground="green" if status.upper() == "STABLE" else "red")

                    # Store attack state for AI
                    self.current_attack = str(grid.get("attack", "NONE"))

                    # ---- GRID WIDE BLACKOUT TIMER ----
                    remaining = float(grid.get("remainingBlackoutTime", 0.0))
                    
                    items = self.blackout_listbox.get(0, tk.END)

                    # Check if first entry is already grid-wide
                    has_grid_entry = items and "GRID-WIDE BLACKOUT" in items[0]

                    if remaining > 0:
                        text = f"GRID-WIDE BLACKOUT ({remaining:.1f}s remaining)"
    
                        if has_grid_entry:
                            # Update existing first row
                            self.blackout_listbox.delete(0)
                            self.blackout_listbox.insert(0, text)
                        else:
                            # Insert new entry at top
                            self.blackout_listbox.insert(0, text)

                    else:
                        # Remove grid-wide entry only if it exists
                        if has_grid_entry:
                            self.blackout_listbox.delete(0)

                    # --- indicators: only redraw if state changed (simple caching) ---
                    indicator_state = getattr(self, "_last_indicator_state", None)
                    generation = float(grid.get("totalGeneration", 0))
                    load = total_load
                    max_capacity = float(grid.get("maxGeneration", 600))

                    if load > 0:
                        new_on_color = "#2ecc71"
                        new_off_color = "#bdc3c7"
                    else:
                        new_on_color = "#bdc3c7"
                        new_off_color = "#e74c3c"
                    

                    if indicator_state != (new_on_color, new_off_color):
                        try:
                            self._draw_light_indicator(self.cv_on, new_on_color)
                            self._draw_light_indicator(self.cv_off, new_off_color)
                        except Exception:
                            pass
                        self._last_indicator_state = (new_on_color, new_off_color)

                    if generation > 0:
                        self._draw_light_indicator(self.cv_grid_on, "#2ecc71")
                        self._draw_light_indicator(self.cv_grid_off, "#bdc3c7" )
                    else:
                        self._draw_light_indicator(self.cv_grid_on, "#bdc3c7")
                        self._draw_light_indicator(self.cv_grid_off, "#e74c3c")

                    # --- Capacity warning Indicator ---
                    usage_ratio = generation / max_capacity if max_capacity > 0 else 0

                    if usage_ratio >=0.90:
                        # Critical(red)
                        self._draw_light_indicator(self.cv_capacity_warning, "#e74c3c", blink= True)
                    elif usage_ratio >= 0.80:
                        self._draw_light_indicator(self.cv_capacity_warning, "#f39c12")
                    else:
                        self._draw_light_indicator(self.cv_capacity_warning, "#000000")


                    # --- Update defense labels ---
                    defenses = data.get("grid", {}).get("defenses", {})

                    mapping = {
                        "authentication" : "authGateway",
                        "firewall" : "firewall",
                        "anomaly" : "anomalyDetection"
                    }
                    
                    for ui_key, firebase_key in mapping.items():
                        active = bool(defenses.get(firebase_key, False))

                        lbl = self.def_labels.get(ui_key)

                        if lbl:
                            lbl.config(
                                text = "ACTIVE" if active else "DISABLED",
                                foreground = "#27ae60" if active else "#c0392b"
                            )
                            
                            # button update
                            btn = self.def_buttons.get(ui_key)
                            if btn:
                                btn.config(
                                    text = "Disable" if active else "Enable"
                                )

                    # --- simple de-dup: avoid applying identical snapshots repeatedly ---
                    snapshot = {
                        "gen": round(total_generation, 3),
                        "load": round(total_load, 3),
                        "status": status,
                        "meters_hash": hash(tuple(sorted(incoming.items())))
                    }
                    last = getattr(self, "_last_dashboard_snapshot", None)
                    if last == snapshot:
                    # nothing meaningful changed; skip (we already applied UI updates above, but this avoids future extra work)
                        return
                    self._last_dashboard_snapshot = snapshot

                except Exception as e:
                    # Never let UI thread crash — log the error
                    try:
                        self.append_attack_log(f"update_dashboard error: {e}", "ERROR")
                    except Exception:
                        # ultimate fallback: print
                        print("update_dashboard error:", e)
            except Exception as outer_e:
                # catch-all for the outer freshness/parse code — log and continue
                try:
                    self.append_attack_log(f"update_dashboard outer error: {outer_e}", "ERROR")
                except Exception:
                    pass

            # schedule on the UI thread
        do_update()


    # ---------------------------
    # Active blackouts management
    # ---------------------------
    def _add_active_blackout(self, meter_id, expiry_dt):
        """
        Thread-safe, defensive add of an active blackout entry.

        - meter_id: str-like identifier for the meter (must be non-empty)
        - expiry_dt: datetime-like expiry (naive datetimes will be converted to UTC-aware)
        """
        # Basic validation & normalization
        if not meter_id:
            return

        # normalize meter id to string and strip whitespace
        try:
            meter_id = str(meter_id).strip()
        except Exception:
            return
        if not meter_id:
            return

        # Ensure expiry_dt is a datetime and timezone-aware (UTC)
        if not isinstance(expiry_dt, datetime):
            try:
                # attempt to coerce numeric epoch -> datetime
                expiry_dt = datetime.fromtimestamp(float(expiry_dt), tz=timezone.utc)
            except Exception:
                # invalid expiry passed — fallback to default duration from now
                expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=getattr(self, "blackout_default_duration", 20.0))
        else:
            # make timezone-aware in UTC if naive
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            else:
                # convert to UTC for consistent comparisons
                try:
                    expiry_dt = expiry_dt.astimezone(timezone.utc)
                except Exception:
                    expiry_dt = expiry_dt

        # Use lock to update shared structure safely
        try:
            with self.active_blackouts_lock:
                existing = self.active_blackouts.get(meter_id)
                # If existing expiry is later or equal, don't shorten it
                if existing and isinstance(existing, datetime):
                    # ensure existing is timezone aware for correct comparison
                    existing_dt = existing
                    if existing_dt.tzinfo is None:
                        existing_dt = existing_dt.replace(tzinfo=timezone.utc)
                    if existing_dt >= expiry_dt:
                        # nothing to do
                        return
                # Add/update
                self.active_blackouts[meter_id] = expiry_dt

                # enforce max entries (drop earliest expiry if exceeded)
                if getattr(self, "max_active_blackouts", None) is not None:
                    try:
                        maxn = int(self.max_active_blackouts)
                        if len(self.active_blackouts) > maxn:
                            # sort by expiry, drop the one with the earliest expiry (oldest)
                            items = sorted(self.active_blackouts.items(), key=lambda kv: kv[1])
                            while len(items) > maxn:
                                drop_id, _ = items.pop(0)
                                try:
                                    del self.active_blackouts[drop_id]
                                except KeyError:
                                    pass
                            # rebuild dict from remaining (preserve)
                            self.active_blackouts = dict(items)
                    except Exception:
                        # on any error, skip eviction to avoid data loss
                        pass

        except Exception:
            # best-effort: log and continue
            try:
                self.append_attack_log(f"Failed to add blackout for {meter_id}", "WARNING")
            except Exception:
                pass

        # Schedule UI update on main thread. Keep the UI callback lightweight.
        try:
            def _ui_add():
                # Refresh listbox if present; _refresh_blackout_listbox is already GUI-safe
                try:
                    if hasattr(self, "_refresh_blackout_listbox"):
                        self._refresh_blackout_listbox()
                except Exception:
                    # avoid raising in GUI thread
                    try:
                        self.append_attack_log(f"Error refreshing blackout list for {meter_id}", "WARNING")
                    except Exception:
                        pass

            # schedule
            if getattr(self, "root", None) is not None:
                try:
                    self.root.after(0, _ui_add)
                except Exception:
                    # fallback: call directly (best-effort)
                    try:
                        _ui_add()
                    except Exception:
                        pass
        except Exception:
            pass


    def _refresh_blackout_listbox(self):
        # Ensure widget exists
        if not hasattr(self, "blackout_listbox") or self.blackout_listbox is None:
            return

        # Build sorted list of (id, expiry)
        try:
            with self.active_blackouts_lock:
                items = sorted(self.active_blackouts.items(), key=lambda kv: kv[1])
        except Exception:
            items = list(self.active_blackouts.items())

        try:
            # clear and repopulate
            self.blackout_listbox.delete(0, tk.END)
            now = datetime.now(timezone.utc)
            for meter_id, expiry in items:
                try:
                    # ensure expiry is timezone-aware
                    if expiry is None:
                        secs = "?"
                    else:
                        if expiry.tzinfo is None:
                            expiry = expiry.replace(tzinfo=timezone.utc)
                        secs = int(max(0, (expiry - now).total_seconds()))
                    self.blackout_listbox.insert(tk.END, f"{meter_id}  (expires in {secs}s)")
                except Exception:
                    # skip problematic entry
                    continue
        except Exception:
            # swallow any UI errors to avoid crashing the GUI
            pass


    def _cleanup_blackouts_loop(self):
        """
        Runs periodically (default every blackout_cleanup_interval_ms) on the GUI thread.
        - Removes expired entries from self.active_blackouts (thread-safe).
        - Logs ended blackouts in a single batch message.
        - Refreshes the GUI listbox on the GUI thread (safe).
        - Reschedules itself using a single after() id to avoid duplicates.
        """
        try:
            # Use timezone-aware 'now' for safe comparisons
            now = datetime.now(timezone.utc)

            removed = []

            # Ensure we have a lock to protect access (fallback to no-lock if missing)
            lock = getattr(self, "active_blackouts_lock", None)

            # Copy keys under lock, then process removals
            if lock:
                with lock:
                    items = list(self.active_blackouts.items())
                    for meter_id, expiry in items:
                        try:
                            if expiry is None:
                                continue
                            # normalize expiry to UTC-aware datetime
                            if expiry.tzinfo is None:
                                expiry_dt = expiry.replace(tzinfo=timezone.utc)
                            else:
                                expiry_dt = expiry.astimezone(timezone.utc)
                            if expiry_dt <= now:
                                removed.append(meter_id)
                                try:
                                    del self.active_blackouts[meter_id]
                                except KeyError:
                                    pass
                        except Exception:
                            # skip problematic entry but don't crash the loop
                            continue
            else:
                # no lock available (older code); behave similarly but be defensive
                items = list(self.active_blackouts.items())
                for meter_id, expiry in items:
                    try:
                        if expiry is None:
                            continue
                        if expiry.tzinfo is None:
                            expiry_dt = expiry.replace(tzinfo=timezone.utc)
                        else:
                            expiry_dt = expiry.astimezone(timezone.utc)
                        if expiry_dt <= now:
                            removed.append(meter_id)
                            try:
                                del self.active_blackouts[meter_id]
                            except KeyError:
                                pass
                    except Exception:
                        continue

            # Batch log ended blackouts (single message to reduce spam)
            if removed:
                try:
                    # Use a single useful message; you can change to ERROR/INFO as needed
                    self.append_attack_log(f"Targeted blackout ended for: {', '.join(removed)}", "INFO")
                except Exception:
                    # best-effort: fall back to log_attack_action or print
                    try:
                        self.log_attack_action(f"Targeted blackout ended for: {', '.join(removed)}")
                    except Exception:
                        print("Targeted blackout ended for:", ", ".join(removed))

                # Refresh the UI listbox on GUI thread — schedule on GUI thread if not already
                try:
                    if getattr(self, "root", None) is not None:
                        # schedule a lightweight refresh (do not rebuild under lock)
                        self.root.after(0, lambda: getattr(self, "_refresh_blackout_listbox", lambda: None)())
                    else:
                        # no root available — try direct call (best-effort)
                        try:
                            self._refresh_blackout_listbox()
                        except Exception:
                            pass
                except Exception:
                    pass

        finally:
            # Reschedule next run: keep a single after id to avoid duplicate timers
            try:
                if getattr(self, "is_running", False):
                    # cancel previous if present (safe no-op if None)
                    try:
                        if getattr(self, "_cleanup_after_id", None) is not None:
                            self.root.after_cancel(self._cleanup_after_id)
                    except Exception:
                        pass

                    # schedule next
                    try:
                        interval = int(getattr(self, "blackout_cleanup_interval_ms", 1000))
                    except Exception:
                        interval = 1000
                    try:
                        self._cleanup_after_id = self.root.after(interval, self._cleanup_blackouts_loop)
                    except Exception:
                        # fallback: try scheduling with default 1000 ms, or set None
                        try:
                            self._cleanup_after_id = self.root.after(1000, self._cleanup_blackouts_loop)
                        except Exception:
                            self._cleanup_after_id = None
                else:
                    # If not running, try to cancel any pending callback and clear id
                    try:
                        if getattr(self, "_cleanup_after_id", None) is not None:
                            self.root.after_cancel(self._cleanup_after_id)
                    except Exception:
                        pass
                self._cleanup_after_id = None
            except Exception:
                # ensure we do not raise from the finally block
                try:
                    self._cleanup_after_id = None
                except Exception:
                    pass


    # ---------------------------
    # Finish / Close
    # ---------------------------
    def on_closing(self):
        # Stop background threads
        self.is_running = False
    
        # Cancel scheduled callbacks if any exist
        try:
            if hasattr(self, "_response_after_id") and self._response_after_id is not None:
                self.root.after_cancel(self._response_after_id)
        except Exception:
            pass

        try:
            if hasattr(self, "_cleanup_after_id") and self._cleanup_after_id is not None:
                self.root.after_cancel(self._cleanup_after_id)
        except Exception:
            pass
    
        # Close the window
        self.root.destroy()


# ---------------------------
# Run
# ---------------------------
def start_dashboard():
    root = tk.Tk()

    try:
        app = OperatorDashboardApp(root)
        root.mainloop()
    except Exception as e:
        print("Fatal error:", e)
    finally:
        # ensure background threads stop
        try:
            app.is_running = False
        except:
            pass

if __name__ == "__main__":
    start_dashboard()

