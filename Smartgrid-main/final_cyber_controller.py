import tkinter as tk
from tkinter import ttk, font, scrolledtext, messagebox
import socket
import json
import threading
import queue
import time
import hashlib
from datetime import datetime
import random

# --- Configuration ---
HOST = '127.0.0.1'
PORT = 8080
REFRESH_RATE_MS = 250

# --- Static Data for Info Popups ---
ATTACK_INFO = { "BLACKOUT": {"title": "20s Blackout Attack", "description": "Target: Availability\n\nThis attack aims to deny service by shutting down power distribution for a set duration."}, "INDUCE_INSTABILITY": {"title": "Grid Instability Attack", "description": "Target: Availability & Integrity\n\nThis attack targets power generation, causing wild fluctuations that can damage equipment and destabilize the grid."}, "SIMULATE_DDOS": {"title": "DDoS Flood Attack", "description": "Target: Availability\n\nA Denial-of-Service (DoS) attack floods the control server with requests, triggering an emergency blackout as a protective measure."} }
DEFENSE_INFO = { "authentication": {"title": "Authentication Gateway", "description": "Verifies all commands have a valid secret token. Blocks unauthorized commands from the 'Cyber Attacks' tab.", "icon": "🔑"}, "replay": {"title": "Temporal Firewall (Replay)", "description": "Checks command timestamps to block old, replayed commands, preventing attackers from reusing valid data.", "icon": "⏳"}, "anomaly": {"title": "Behavioral Analysis (Anomaly)", "description": "Monitors meter readings for unusual behavior (e.g., impossibly large changes) and blocks suspicious data.", "icon": "📈"}, "encryption": {"title": "Encryption (Integrity Check)", "description": "Simulates message integrity. If a Man-in-the-Middle attacker modifies a command, its hash becomes invalid, and the server rejects it.", "icon": "🔒"} }

class CyberGridSimulatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Grid Master Control & Cyber Simulation")
        self.root.geometry("1600x850") # Increased width for new panel
        self.root.minsize(1400, 700)

        self.request_queue = queue.PriorityQueue()
        self.response_queue = queue.Queue()
        self.is_running = True
        self.auth_token = "SECURE_TOKEN_123"
        self.captured_command = None
        self.attack_buttons = {}
        self.mitm_active = tk.BooleanVar(value=False)
        self.mitm_mode = tk.StringVar(value="passive")
        self.is_warning_flashing = False
        self.last_known_encryption_state = True
        self.tree_state = {}

        self._setup_styles()
        self.create_widgets()
        
        self.network_thread = threading.Thread(target=self.network_worker, daemon=True)
        self.network_thread.start()
        self.process_response_queue()
        self.auto_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _calculate_hash(self, payload):
        value_str = f"{payload.get('value', 0.0):.6f}"
        timestamp_str = f"{payload.get('timestamp', 0.0):.6f}"
        from_operator_str = str(payload.get('fromOperator', False)).lower()
        hash_string = f"{payload.get('command','')}-{payload.get('targetID','')}-{value_str}-{payload.get('authToken','')}-{timestamp_str}-{from_operator_str}"
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def _create_payload(self, command, targetID="", value=0.0, is_attack=False, is_from_operator_panel=False):
        token = "INVALID_TOKEN" if is_attack else self.auth_token
        
        payload = {
            "command": command, "targetID": targetID, "value": float(value), 
            "authToken": token, "timestamp": datetime.now().timestamp(),
            "fromOperator": is_from_operator_panel
        }
        
        payload["hash"] = self._calculate_hash(payload)

        if not is_from_operator_panel and self.mitm_active.get() and self.mitm_mode.get() == "active" and payload['command'] == "SET_LIGHTS":
            original_value = payload['value']
            if self.last_known_encryption_state:
                self.log_to_terminal("[MitM-INTERCEPT] Traffic is encrypted. Attempting to flip bits anyway...", "ATTACK")
            else:
                self.log_to_terminal(f"[MitM-INTERCEPT] Flipped SET_LIGHTS from {original_value} to {1.0 - original_value}", "ATTACK")
            payload['value'] = 1.0 - original_value
            if not self.last_known_encryption_state:
                payload["hash"] = self._calculate_hash(payload)

        if command not in ["GET_STATUS", "SET_DEFENSE", "DATA_BREACH", "RESET_TAMPERS"]:
            self.captured_command = payload
        return payload

    def network_worker(self):
        while self.is_running:
            try:
                _priority, payload = self.request_queue.get(timeout=1)
                log_payload_str = json.dumps(payload)

                if self.mitm_active.get() and self.mitm_mode.get() == "passive":
                    log_output = f"ENCRYPTED DATA - {hashlib.sha256(log_payload_str.encode()).hexdigest()}" if self.last_known_encryption_state else log_payload_str
                    self.response_queue.put({"type": "log", "level": "ATTACK", "message": f"[MitM] SENT: {log_output}"})

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3.0)
                    s.connect((HOST, PORT))
                    s.sendall(log_payload_str.encode('utf-8'))
                    response_data = s.recv(8192).decode('utf-8', errors='ignore')
                    
                    if self.mitm_active.get() and self.mitm_mode.get() == "passive":
                        log_output = f"ENCRYPTED DATA - {hashlib.sha256(response_data.encode()).hexdigest()}" if self.last_known_encryption_state else response_data
                        self.response_queue.put({"type": "log", "level": "ATTACK", "message": f"[MitM] RECV: {log_output}"})

                    self.response_queue.put(json.loads(response_data))

            except queue.Empty:
                continue
            except socket.timeout:
                self.response_queue.put({"error": "Connection timed out. Is the Unity Editor in Play mode?"})
            except ConnectionRefusedError:
                self.response_queue.put({"error": "Connection refused. Is the Unity server running and not blocked by a firewall?"})
            except Exception as e:
                self.response_queue.put({"error": f"Network Error: {type(e).__name__} - {e}"})

    def process_response_queue(self):
        try:
            while not self.response_queue.empty():
                message = self.response_queue.get_nowait()
                msg_type = message.get("type")

                if msg_type == "log": self.log_to_terminal(message["message"], message["level"])
                elif msg_type == "animation_start":
                    btn = self.attack_buttons.get(message["command"])
                    if btn: btn.config(state=tk.DISABLED, style="Red.TButton")
                    self.attack_status_label.config(text=f"{message['command']} in progress...")
                elif msg_type == "animation_progress": self.attack_progress["value"] = message["value"]
                elif msg_type == "animation_end":
                    btn = self.attack_buttons.get(message["command"])
                    if btn: btn.config(state=tk.NORMAL, style="TButton")
                    self.attack_status_label.config(text="Idle")
                    self.attack_progress["value"] = 0
                elif "error" in message:
                    self.log_to_terminal(message["error"], "ERROR")
                    self.status_value.config(text="DISCONNECTED", foreground="red")
                else:
                    self.update_dashboard(message)
                    log_msg = message.get("log")
                    if log_msg:
                        if "[CRITICAL]" in log_msg: messagebox.showwarning("Grid Alert", log_msg)
                        elif "[DATA_BREACH]" in log_msg:
                            try:
                                data = json.loads(log_msg.replace("[DATA_BREACH] ", ""))
                                self.log_to_terminal(f"SUCCESS! Exfiltrated Data:\n{json.dumps(data, indent=2)}", "ATTACK")
                            except json.JSONDecodeError: self.log_to_terminal("Failed to parse exfiltrated data.", "ERROR")
                        elif "[DEFENSE] Invalid auth token" in log_msg: self._log_defense_action("authentication", log_msg)
                        elif "[DEFENSE] Replay attack detected" in log_msg: self._log_defense_action("replay", log_msg)
                        elif "[DEFENSE] Anomaly detected" in log_msg: self._log_defense_action("anomaly", log_msg)
                        elif "[DEFENSE] Integrity check failed" in log_msg: self._log_defense_action("encryption", log_msg)
                        elif "[DEFENSE] Unauthorized: SET_LIGHTS" in log_msg: self._log_defense_action("authorization", log_msg)
                        else: self.log_to_terminal(log_msg, "RESPONSE")
        finally:
            if self.is_running:
                self.root.after(100, self.process_response_queue)
    
    def _log_defense_action(self, defense_type, original_log):
        visual_map = {
            "authentication": "Incoming Cmd -> [AUTH GATEWAY] -> TOKEN: INVALID\n             |\n           [ACCESS DENIED]",
            "replay":         "Incoming Cmd -> [TEMPORAL FW]  -> TIMESTAMP: OLD\n             |\n           [PACKET DROPPED]",
            "anomaly":        "Meter Data   -> [BEHAVIOR ANL] -> DEVIATION > THRESHOLD\n             |\n           [DATA REJECTED]",
            "encryption":     "Encrypted Pkt-> [INTEGRITY CHK]-> HASH MISMATCH\n             |\n           [PACKET DISCARDED]",
            "authorization":  "SET_LIGHTS Cmd -> [AUTHZ CHECK] -> Source: NOT OPERATOR\n             |\n           [ACCESS DENIED]"
        }
        keyword_map = { "authentication": "INVALID", "replay": "OLD", "anomaly": "DEVIATION > THRESHOLD", "encryption": "HASH MISMATCH", "authorization": "NOT OPERATOR" }
        self.log_to_defense_console(defense_type, visual_map.get(defense_type, original_log), keyword_map.get(defense_type))

    # --- All GUI and helper methods below are included for completeness ---
    
    def _setup_styles(self):
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self.style.configure("Info.TButton", font=("Helvetica", 9, "bold"))
        self.label_font = font.Font(family="Helvetica", size=10)
        self.value_font = font.Font(family="monospace", size=14, weight="bold")
        self.header_font = font.Font(family="Helvetica", size=11, weight="bold")
        self.defense_font = font.Font(family="Helvetica", size=12, weight="bold")
        self.desc_font = font.Font(family="Helvetica", size=9, slant="italic")
        self.style.configure('Value.TLabel', font=self.value_font, anchor='e')
        self.style.configure('Status.TLabel', font=self.value_font)
        self.style.configure('Treeview.Heading', font=("Helvetica", 10, "bold"))
        self.style.configure('Defense.TLabel', font=self.defense_font)
        self.style.configure("Red.TButton", background="#c0392b", foreground="white", font=("Helvetica", 10, "bold"))
        self.style.map("Red.TButton", background=[('active', '#e74c3c')])
        self.style.configure("TButton", font=("Helvetica", 10))
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        operator_tab = self._create_tab('Operator Dashboard')
        cyber_tab = self._create_tab('Cybersecurity Attacks')
        defense_tab = self._create_tab('Defense System')
        self._populate_operator_tab(operator_tab)
        self._populate_cyber_tab(cyber_tab)
        self._populate_defense_tab(defense_tab)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy Selected Rows", command=self.copy_selection_to_clipboard)
        self.context_menu.add_command(label="Copy Meter ID for Tampering", command=self.copy_meter_id_for_tamper)
        self.meter_tree.tag_configure('oddrow', background='#E8E8E8')
        self.meter_tree.tag_configure('evenrow', background='#FFFFFF')
        self.meter_tree.tag_configure('child_odd', background='#FAFAFA')
        self.meter_tree.tag_configure('child_even', background='#F0F0F0')
        self.meter_tree.tag_configure('parent', font=("Helvetica", 10, 'bold'))
        self.meter_tree.tag_configure('active', foreground='green')
        self.meter_tree.tag_configure('inactive', foreground='#A0A0A0')
        self.terminal.tag_configure('ATTACK', foreground='#FF4136', font=("Consolas", 10, "bold"))
    def _create_tab(self, text):
        frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(frame, text=text)
        return frame
    def _populate_operator_tab(self, parent):
        left_panel = ttk.Frame(parent)
        left_panel.pack(side="left", fill="y", expand=False, padx=(0, 10))
        dash_frame = ttk.LabelFrame(left_panel, text="Live Grid Status", padding=15)
        dash_frame.pack(expand=False, fill="x")
        dash_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(dash_frame, text="Power Generation:", font=self.label_font).grid(row=0, column=0, sticky="w", pady=5)
        self.gen_value = ttk.Label(dash_frame, text="-.--", style='Value.TLabel')
        self.gen_value.grid(row=0, column=1, sticky="e")
        ttk.Label(dash_frame, text="kW", font=self.label_font).grid(row=0, column=2, sticky="w")
        ttk.Label(dash_frame, text="City Consumption:", font=self.label_font).grid(row=1, column=0, sticky="w", pady=5)
        self.city_con_value = ttk.Label(dash_frame, text="-.--", style='Value.TLabel')
        self.city_con_value.grid(row=1, column=1, sticky="e")
        ttk.Label(dash_frame, text="kW", font=self.label_font).grid(row=1, column=2, sticky="w")
        ttk.Label(dash_frame, text="Town Consumption:", font=self.label_font).grid(row=2, column=0, sticky="w", pady=5)
        self.town_con_value = ttk.Label(dash_frame, text="-.--", style='Value.TLabel')
        self.town_con_value.grid(row=2, column=1, sticky="e")
        ttk.Label(dash_frame, text="kW", font=self.label_font).grid(row=2, column=2, sticky="w")
        ttk.Separator(dash_frame, orient='horizontal').grid(row=3, columnspan=3, sticky='ew', pady=15)
        ttk.Label(dash_frame, text="GRID STATUS:", font=self.label_font).grid(row=4, column=0, sticky="w", pady=10)
        self.status_value = ttk.Label(dash_frame, text="CONNECTING...", style='Status.TLabel', foreground="orange")
        self.status_value.grid(row=4, column=1, columnspan=2, sticky="e")
        ctrl_frame = ttk.LabelFrame(left_panel, text="Main Switch", padding=15)
        ctrl_frame.pack(expand=False, fill="x", pady=(10, 0))
        ttk.Button(ctrl_frame, text="Turn ALL ON", command=lambda: self.log_and_send(1, self._create_payload("SET_LIGHTS", value=1.0, is_from_operator_panel=True), "Sending Main Switch ON command.")).pack(expand=True, fill="x", pady=5)
        ttk.Button(ctrl_frame, text="Turn ALL OFF", command=lambda: self.log_and_send(1, self._create_payload("SET_LIGHTS", value=0.0, is_from_operator_panel=True), "Sending Main Switch OFF command.")).pack(expand=True, fill="x", pady=5)
        restart_frame = ttk.LabelFrame(left_panel, text="Emergency Grid Control", padding=15)
        restart_frame.pack(expand=False, fill="x", pady=(10, 0))
        ttk.Button(restart_frame, text="Restart All Systems", command=lambda: self.log_and_send(1, self._create_payload("SET_LIGHTS", value=1.0, is_from_operator_panel=True), "EMERGENCY RESTART triggered."), style="Red.TButton").pack(expand=True, fill="x", pady=5)
        meter_frame = ttk.LabelFrame(parent, text="Individual Meter Readings", padding=10)
        meter_frame.pack(side="right", fill="both", expand=True)
        columns = ("status", "id", "count", "location", "consumption")
        self.meter_tree = ttk.Treeview(meter_frame, columns=columns, show="headings")
        for col in columns: self.meter_tree.heading(col, text=col.replace("_", " ").title(), command=lambda c=col: self.sort_column_data(c, False))
        self.meter_tree.column("status", width=60, anchor="center")
        self.meter_tree.column("id", width=300)
        self.meter_tree.column("count", width=100, anchor="center")
        self.meter_tree.column("location", width=100, anchor="center")
        self.meter_tree.column("consumption", width=150, anchor="e")
        scrollbar = ttk.Scrollbar(meter_frame, orient="vertical", command=self.meter_tree.yview)
        self.meter_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.meter_tree.pack(side="left", fill="both", expand=True)
        self.meter_tree.bind("<Button-1>", self.toggle_meter_node)
        self.meter_tree.bind("<Button-3>", self.show_context_menu)
    def _populate_cyber_tab(self, parent):
        attack_frame = ttk.Frame(parent, width=420)
        attack_frame.pack(side="left", fill="y", expand=False, padx=(0, 10))
        mitm_frame = ttk.LabelFrame(attack_frame, text="Man-in-the-Middle Simulation", padding=10)
        mitm_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Checkbutton(mitm_frame, text="Activate MitM Proxy", variable=self.mitm_active).pack(anchor='w')
        ttk.Radiobutton(mitm_frame, text="Passive Mode (Eavesdrop)", variable=self.mitm_mode, value="passive").pack(anchor='w', padx=20)
        ttk.Radiobutton(mitm_frame, text="Active Mode (Intercept & Modify)", variable=self.mitm_mode, value="active").pack(anchor='w', padx=20)
        ttk.Button(mitm_frame, text="Send Unauthorized 'Turn ON' Command", command=self.send_benign_command_for_mitm).pack(fill=tk.X, pady=5)
        ttk.Button(mitm_frame, text="Exfiltrate Grid Data (Data Breach)", command=self.exfiltrate_data).pack(fill=tk.X, pady=5)
        progress_frame = ttk.LabelFrame(attack_frame, text="Attack Status", padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.attack_status_label = ttk.Label(progress_frame, text="Idle")
        self.attack_status_label.pack()
        self.attack_progress = ttk.Progressbar(progress_frame, orient='horizontal', length=300, mode='determinate')
        self.attack_progress.pack(pady=5)
        avail_frame = ttk.LabelFrame(attack_frame, text="Availability Attacks", padding=10)
        avail_frame.pack(fill=tk.X, pady=10)
        integ_frame = ttk.LabelFrame(attack_frame, text="Integrity & Replay Attacks", padding=10)
        integ_frame.pack(fill=tk.X, pady=10)
        self._add_attack_button(avail_frame, "Simulate 20s Blackout", "BLACKOUT", 20)
        self._add_attack_button(avail_frame, "Simulate Grid Instability", "INDUCE_INSTABILITY", 10)
        self._add_attack_button(avail_frame, "Simulate DDoS Flood", "SIMULATE_DDOS", 15)
        ttk.Label(integ_frame, text="Target Meter ID:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.tamper_id_entry = ttk.Entry(integ_frame, width=20)
        self.tamper_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(integ_frame, text="Fake Value (kW):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.tamper_value_entry = ttk.Entry(integ_frame, width=10)
        self.tamper_value_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        integ_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(integ_frame, text="Tamper Meter", command=self.send_tamper_meter).grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        ttk.Button(integ_frame, text="Capture Last Action", command=self.capture_command).grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(integ_frame, text="Execute Replay Attack", command=self.replay_attack).grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(integ_frame, text="Reset All Tampers", command=self.reset_tampers).grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        terminal_frame = ttk.Frame(parent)
        terminal_frame.pack(side="right", fill="both", expand=True)
        ttk.Label(terminal_frame, text="Main Simulation Log", font=self.header_font).pack(anchor="w")
        self.terminal = scrolledtext.ScrolledText(terminal_frame, wrap=tk.WORD, state=tk.DISABLED, bg="black", fg="limegreen", font=("Consolas", 10))
        self.terminal.pack(fill=tk.BOTH, expand=True, pady=(5,0))
    def _populate_defense_tab(self, parent):
        grid_container = ttk.Frame(parent)
        grid_container.pack(fill=tk.BOTH, expand=True)
        # Configure grid for 2 rows, 3 columns
        grid_container.grid_rowconfigure(0, weight=1); grid_container.grid_rowconfigure(1, weight=1)
        grid_container.grid_columnconfigure(0, weight=1); grid_container.grid_columnconfigure(1, weight=1); grid_container.grid_columnconfigure(2, weight=1, minsize=400)
        # Create 2x2 grid for main defenses
        self._create_defense_panel(grid_container, "authentication").grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self._create_defense_panel(grid_container, "replay").grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self._create_defense_panel(grid_container, "anomaly").grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        self._create_defense_panel(grid_container, "encryption").grid(row=1, column=1, padx=5, pady=5, sticky="nsew")
        # Create dedicated authorization log panel
        authz_frame = ttk.LabelFrame(grid_container, text="🛡️ Command Authorization Log", padding=10)
        authz_frame.grid(row=0, column=2, rowspan=2, padx=5, pady=5, sticky="nsew")
        console = scrolledtext.ScrolledText(authz_frame, wrap=tk.WORD, state=tk.DISABLED, height=4, bg="#1E1E1E", fg="#A9D5A9", font=("Consolas", 9))
        console.pack(expand=True, fill='both')
        setattr(self, "console_widget_authorization", console)
        console.tag_configure("BLOCK", foreground="#FF7B7B", font=("Consolas", 9, "bold")); console.tag_configure("INFO", foreground="#98FB98")
    def _create_defense_panel(self, parent, defense_type):
        info = DEFENSE_INFO.get(defense_type, {"title": "Unknown", "description": "", "icon": "❓"})
        frame = ttk.LabelFrame(parent, text=f" {info['icon']} {info['title']} ", padding=10)
        frame.grid_rowconfigure(2, weight=1); frame.grid_columnconfigure(0, weight=1)
        desc_frame = ttk.Frame(frame)
        desc_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        desc_frame.grid_columnconfigure(0, weight=1)
        ttk.Label(desc_frame, text=info["description"].split('\n')[0], font=self.desc_font, wraplength=450, justify=tk.LEFT).grid(row=0, column=0, sticky="w")
        ttk.Button(desc_frame, text="?", width=2, style="Info.TButton", command=lambda t=info["title"], d=info["description"]: self.show_info_popup(t, d)).grid(row=0, column=1, padx=(10,0))
        control_frame = ttk.Frame(frame)
        control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        status_light = tk.Canvas(control_frame, width=20, height=20, bg=self.root.cget('bg'), highlightthickness=0)
        status_light.pack(side=tk.LEFT, padx=(0, 5))
        light_id = status_light.create_oval(3, 3, 18, 18, fill="orange", outline="gray")
        status_label = ttk.Label(control_frame, text="UNKNOWN", font=self.header_font)
        status_label.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Button(control_frame, text="Toggle", command=lambda dt=defense_type: self.toggle_defense(dt)).pack(side=tk.LEFT)
        setattr(self, f"{defense_type}_status_label", status_label)
        setattr(self, f"{defense_type}_status_light", status_light)
        setattr(self, f"{defense_type}_light_id", light_id)
        console = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state=tk.DISABLED, height=4, bg="#1E1E1E", fg="#A9D5A9", font=("Consolas", 9))
        console.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        console.tag_configure("BLOCK", foreground="#FF7B7B", font=("Consolas", 9, "bold")); console.tag_configure("INFO", foreground="#98FB98")
        setattr(self, f"console_widget_{defense_type}", console)
        return frame
    def _add_attack_button(self, parent, text, command, duration):
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, expand=True)
        btn = ttk.Button(btn_frame, text=text, command=lambda c=command, d=duration: self.run_attack_with_animation(c, d))
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.attack_buttons[command] = btn
        info = ATTACK_INFO.get(command, {"title": "Info", "description": "No info."})
        ttk.Button(btn_frame, text="?", width=2, style="Info.TButton", command=lambda t=info["title"], i=info["description"]: self.show_info_popup(t, i)).pack(side=tk.RIGHT, padx=5)
    def run_attack_with_animation(self, command, duration):
        self.log_and_send(1, self._create_payload(command, is_attack=True), f"Initiating {command} sequence...", "ATTACK")
        def animate():
            self.response_queue.put({"type": "animation_start", "command": command})
            step_count = duration * 5 
            for i in range(step_count + 1):
                progress = (i / step_count) * 100
                self.response_queue.put({"type": "animation_progress", "value": progress})
                log_msg = ""
                if command == "SIMULATE_DDOS" and i % 2 == 0: log_msg = f"  -> Flooding server with request from bot: {random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
                elif command == "BLACKOUT":
                    if i == int(step_count * 0.2): log_msg = "  -> Breaching substation controls..."
                    if i == int(step_count * 0.5): log_msg = "  -> Disconnecting City A breakers..."
                    if i == int(step_count * 0.8): log_msg = "  -> Disconnecting Town B breakers..."
                elif command == "INDUCE_INSTABILITY":
                    if i == int(step_count * 0.2): log_msg = "  -> Injecting malicious frequency signals..."
                    if i == int(step_count * 0.5): log_msg = "  -> Generator G-01 frequency desync..."
                    if i == int(step_count * 0.8): log_msg = "  -> Generator G-02 voltage fluctuation..."
                if log_msg: self.response_queue.put({"type": "log", "level": "ATTACK", "message": log_msg})
                time.sleep(0.2)
            final_msg = ""
            if command == "SIMULATE_DDOS": final_msg = ">> SERVER OVERLOADED <<"
            if command == "BLACKOUT": final_msg = ">> BLACKOUT ENFORCED <<"
            if command == "INDUCE_INSTABILITY": final_msg = ">> GRID DESTABILIZED <<"
            if final_msg: self.response_queue.put({"type": "log", "level": "ATTACK", "message": final_msg})
            self.response_queue.put({"type": "animation_end", "command": command})
        threading.Thread(target=animate, daemon=True).start()
    def log_and_send(self, priority, payload, log_message, level="INFO"):
        self.log_to_terminal(log_message, level)
        self.request_queue.put((priority, payload))
    def log_to_terminal(self, message, level="INFO"):
        if not self.is_running: return
        self.terminal.config(state=tk.NORMAL)
        now = datetime.now().strftime("%H:%M:%S")
        tag = ('ATTACK',) if level == "ATTACK" else ()
        self.terminal.insert(tk.END, f"[{now}] [{level}] {message}\n", tag)
        self.terminal.see(tk.END)
        self.terminal.config(state=tk.DISABLED)
    def log_to_defense_console(self, defense_type, message, tag_keyword=None):
        if not self.is_running: return
        try: console_widget = getattr(self, f"console_widget_{defense_type}")
        except AttributeError: return
        console_widget.config(state=tk.NORMAL)
        now = datetime.now().strftime("%H:%M:%S")
        for i, line in enumerate(message.split('\n')):
            prefix = f"[{now}] " if i == 0 else " " * (len(now) + 3)
            full_line = f"{prefix}{line}\n"
            console_widget.insert(tk.END, full_line, "INFO")
            if tag_keyword and tag_keyword in line:
                line_start_index = console_widget.index(f"end-{len(full_line)+1}c")
                start_pos = line.find(tag_keyword)
                if start_pos != -1:
                    tag_start = f"{line_start_index} + {len(prefix) + start_pos}c"
                    tag_end = f"{tag_start} + {len(tag_keyword)}c"
                    console_widget.tag_add("BLOCK", tag_start, tag_end)
        console_widget.see(tk.END)
        console_widget.config(state=tk.DISABLED)
    def send_benign_command_for_mitm(self): self.log_and_send(1, self._create_payload("SET_LIGHTS", value=1.0), "Sending unauthorized 'Turn ON' command to test authorization.")
    def toggle_defense(self, defense_type): self.log_and_send(1, self._create_payload("SET_DEFENSE", targetID=defense_type), f"Toggling '{defense_type}' defense.")
    def send_tamper_meter(self):
        target_id=self.tamper_id_entry.get().strip()
        try:
            value=float(self.tamper_value_entry.get())
            if target_id: self.log_and_send(1, self._create_payload("TAMPER_METER",target_id,value, is_attack=True), f"Sending TAMPER_METER for '{target_id}'.", "ATTACK")
        except ValueError: self.log_to_terminal("Invalid tamper value.", "ERROR")
    def capture_command(self):
        if self.captured_command: self.log_to_terminal(f"Command captured: '{self.captured_command['command']}' from {datetime.fromtimestamp(self.captured_command['timestamp'])}")
        else: self.log_to_terminal("No user action captured yet.", "WARN")
    def replay_attack(self):
        if self.captured_command:
            replayed_payload = self.captured_command.copy()
            replayed_payload['authToken'] = 'INVALID_TOKEN'
            replayed_payload['hash'] = self._calculate_hash(replayed_payload)
            self.log_and_send(1, replayed_payload, "Executing REPLAY ATTACK.", "ATTACK")
        else: self.log_to_terminal("No command to replay.", "ERROR")
    def reset_tampers(self): self.log_and_send(1, self._create_payload("RESET_TAMPERS"), "Resetting all tampered meters.")
    def exfiltrate_data(self): self.log_and_send(1, self._create_payload("DATA_BREACH", is_attack=True), "Attempting data exfiltration...", "ATTACK")
    def update_dashboard(self, data):
        self.last_known_encryption_state = data.get('encryptionActive', False)
        for system in ["authentication", "replay", "anomaly", "encryption"]:
            is_active = data.get(f'{system}Active', False)
            status_label = getattr(self, f"{system}_status_label", None)
            status_light = getattr(self, f"{system}_status_light", None)
            light_id = getattr(self, f"{system}_light_id", None)
            if status_label and status_light and light_id:
                status_text, status_color = ("ACTIVE", "#2ECC71") if is_active else ("INACTIVE", "#E74C3C")
                status_label.config(text=status_text, foreground=status_color)
                status_light.itemconfig(light_id, fill=status_color)
        for item_id in self.meter_tree.get_children(): self.tree_state[item_id] = self.meter_tree.item(item_id, 'open')
        self.meter_tree.delete(*self.meter_tree.get_children())
        grouped_meters = {}
        for meter in data.get('meters', []):
            base_id = meter.get('id', 'N/A').split(' ')[0]
            if base_id not in grouped_meters: grouped_meters[base_id] = {'location': meter.get('location', 'N/A'), 'total_consumption': 0.0, 'count': 0, 'children': []}
            grouped_meters[base_id]['total_consumption'] += meter.get('consumption', 0)
            grouped_meters[base_id]['count'] += 1
            grouped_meters[base_id]['children'].append(meter)
        city_con, town_con, i = 0, 0, 0
        for base_id, details in sorted(grouped_meters.items()):
            consumption = details['total_consumption']
            if details['location'] == 'City': city_con += consumption
            elif details['location'] == 'Town': town_con += consumption
            is_open = self.tree_state.get(base_id, False)
            parent_id = self.meter_tree.insert('', 'end', iid=base_id, values=("●", f"{'▼' if is_open else '▶'} {base_id}", details['count'], details['location'], f"{consumption:.2f} kW"), tags=('evenrow' if i % 2 == 0 else 'oddrow', 'active' if consumption > 0 else 'inactive', 'parent'), open=is_open)
            for child_meter in sorted(details['children'], key=lambda x: x.get('id')):
                self.meter_tree.insert(parent_id, 'end', values=("", f"  └ {child_meter.get('id')}", "", "", f"{child_meter.get('consumption', 0):.2f} kW"), tags=('child_even' if i % 2 == 0 else 'child_odd', 'active' if child_meter.get('consumption', 0) > 0 else 'inactive', 'child'))
            i += 1
        self.gen_value.config(text=f"{data.get('totalGeneration', 0):.2f}")
        self.city_con_value.config(text=f"{city_con:.2f}")
        self.town_con_value.config(text=f"{town_con:.2f}")
        status = data.get('gridStatus', 'UNKNOWN')
        if status == "HIGH DEMAND":
            if not self.is_warning_flashing:
                self.is_warning_flashing = True
                self.flash_warning_label(self.status_value, True)
        else:
            if self.is_warning_flashing: self.is_warning_flashing = False 
            self.status_value.config(text=status, foreground={"STABLE": "green", "OVERLOAD": "red", "UNSTABLE": "red"}.get(status, "orange"))
    def flash_warning_label(self, label, is_flashing):
        if not self.is_running or not is_flashing:
            self.status_value.config(text=self.status_value.cget("text"), foreground={"STABLE": "green", "OVERLOAD": "red", "UNSTABLE": "red"}.get(self.status_value.cget("text"), "orange"))
            return
        next_color = "yellow" if str(label.cget("foreground")) == "orange" else "orange"
        label.config(foreground=next_color, text="⚠️ HIGH DEMAND")
        self.root.after(500, lambda: self.flash_warning_label(label, self.is_warning_flashing))
    def auto_refresh(self):
        if self.is_running:
            self.request_queue.put((10, self._create_payload("GET_STATUS")))
            self.root.after(REFRESH_RATE_MS, self.auto_refresh)
    def on_closing(self):
        self.is_running = False
        self.root.destroy()
    def show_info_popup(self, title, description): messagebox.showinfo(title, description)
    def show_context_menu(self, event):
        item_id = self.meter_tree.identify_row(event.y)
        if item_id:
            if not self.meter_tree.selection() or item_id not in self.meter_tree.selection(): self.meter_tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)
    def copy_selection_to_clipboard(self):
        selected_items = self.meter_tree.selection()
        if not selected_items: return
        headers = [self.meter_tree.heading(col)["text"] for col in self.meter_tree["columns"]]
        lines = ["\t".join(headers)] + ["\t".join(map(str, self.meter_tree.item(item_id)['values'])) for item_id in selected_items]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.log_to_terminal(f"Copied {len(selected_items)} row(s).")
    def copy_meter_id_for_tamper(self):
        selected_items = self.meter_tree.selection()
        if not selected_items: return
        item_values = self.meter_tree.item(selected_items[0], 'values')
        if item_values:
            meter_id_text = str(item_values[1]).lstrip('▶▼ ').lstrip('  └ ').strip()
            self.root.clipboard_clear()
            self.root.clipboard_append(meter_id_text)
            self.notebook.select(1)
            self.tamper_id_entry.delete(0, tk.END)
            self.tamper_id_entry.insert(0, meter_id_text)
            self.log_to_terminal(f"Meter ID '{meter_id_text}' copied and ready for tampering.")
    def sort_column_data(self, col, reverse):
        data = [(self.meter_tree.set(child, col), child) for child in self.meter_tree.get_children('')]
        try: data.sort(key=lambda item: float(str(item[0]).replace('kW', '').strip()), reverse=reverse)
        except (ValueError, IndexError): data.sort(key=lambda item: str(item[0]), reverse=reverse)
        for index, (_val, child_id) in enumerate(data): self.meter_tree.move(child_id, '', index)
        self.meter_tree.heading(col, command=lambda c=col: self.sort_column_data(c, not reverse))
    def toggle_meter_node(self, event):
        item_id = self.meter_tree.identify_row(event.y)
        if item_id and 'parent' in self.meter_tree.item(item_id, 'tags'):
            new_state = not self.meter_tree.item(item_id, 'open')
            self.meter_tree.item(item_id, open=new_state)
            current_values = list(self.meter_tree.item(item_id, 'values'))
            current_values[1] = current_values[1].replace('▶', '▼') if new_state else current_values[1].replace('▼', '▶')
            self.meter_tree.item(item_id, values=tuple(current_values))
            self.tree_state[item_id] = new_state

if __name__ == "__main__":
    root = tk.Tk()
    app = CyberGridSimulatorApp(root)
    root.mainloop()
