import tkinter as tk
from tkinter import ttk, scrolledtext
import requests
import threading
import queue
import time
from datetime import datetime

# --- Configuration ---
FIREBASE_URL = "https://smartgrid-harshi-default-rtdb.asia-southeast1.firebasedatabase.app/"
COMMAND_ENDPOINT = FIREBASE_URL + "command.json"
STATUS_ENDPOINT = FIREBASE_URL + ".json"

class CyberAttackApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CYBER ATTACK CONSOLE [UNAUTHORIZED]")
        self.root.geometry("1000x700")
        self.root.configure(bg="#1e1e1e")

        self.request_queue = queue.PriorityQueue()
        self.is_running = True

        # Inputs
        self.tamper_target = tk.StringVar()
        self.tamper_value = tk.StringVar()
        self.blackout_target = tk.StringVar()

        self.defenses_active = False  # TRUE when any defense is active

        self._setup_ui()

        # Network Thread
        self.network_thread = threading.Thread(target=self.network_worker, daemon=True)
        self.network_thread.start()

        # Poll for defense status every 1 sec
        self.root.after(500, self.poll_defense_status)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        #self.remaining_blackout_time = 0 // should have been in defense

    # -------------------------------------------------------------------
    # PAYLOAD CREATION
    # -------------------------------------------------------------------
    def _create_payload(self, command, targetID="", value=0.0):
        return {
            "command": command,
            "targetID": targetID,
            "value": float(value),
            "authToken": "INVALID_TOKEN_X99",
            "timestamp": datetime.now().timestamp(),
            "fromOperator": False,
            "hash": "INVALID_HASH"
        }

    # -------------------------------------------------------------------
    # NETWORK WORKER (sending only)
    # -------------------------------------------------------------------
    def network_worker(self):
        while self.is_running:
            try:
                try:
                    _p, payload = self.request_queue.get(block=False)

                    # Straight send (attacks blocked in send_attack, not here)
                    resp = requests.put(COMMAND_ENDPOINT, json=payload, timeout=4)
                    if resp.status_code == 200:
                        self.log(f"SENT EXPLOIT: {payload['command']} (target={payload.get('targetID','')})", "sent")
                    else:
                        self.log(f"FAILED TO SEND: {resp.status_code}", "err")

                except queue.Empty:
                    pass
                except Exception as e:
                    self.log(f"Network Error: {e}", "err")

                time.sleep(0.05)
            except Exception:
                time.sleep(1)

    # -------------------------------------------------------------------
    # ATTACK BUTTON HANDLER
    # -------------------------------------------------------------------
    def send_attack(self, cmd, target="", val=0.0):
        """Called ONLY when user clicks a button"""

        # Defense system blocks attacks
        if self.defenses_active and cmd in ("BLACKOUT", "SIMULATE_DDOS", "INSTABILITY"):
            self.log(f"⚠ BLOCKED: Defense system active. Cannot execute {cmd}.", "err")
            return

        # Parse injected value
        try:
            v = float(val) if val != "" else 0.0
        except:
            v = 0.0

        # Queue payload
        self.request_queue.put((1, self._create_payload(cmd, target, v)))

    # -------------------------------------------------------------------
    # SPY REQUEST (GET GRID DATA)
    # -------------------------------------------------------------------
    def fetch_grid_data(self):

        # FIXED: block spying when defenses are active
        if self.defenses_active:
            self.log("⚠ BLOCKED: Defense system active. Cannot retrieve grid data.", "err")
            return

        # otherwise allow
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        self.log("ATTEMPTING TO INTERCEPT GRID DATA...", "info")

        try:
            resp = requests.get(STATUS_ENDPOINT, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                self.root.after(0, lambda: self._display_spy_data(data))
            else:
                self.log(f"INTERCEPTION FAILED: {resp.status_code}", "err")
        except Exception as e:
            self.log(f"CONNECTION ERROR: {e}", "err")

    def _display_spy_data(self, data):

        grid = data.get("grid", {})
        devices = data.get("devices", {})

        generation = grid.get("totalGeneration", 0)
        status = grid.get("gridStatus", "UNKNOWN")

        self.term.insert("end", "\n=== INTERCEPTED GRID REPORT ===\n", "info")
        self.term.insert("end", f"Total Generation: {generation} kW\n", "info")
        self.term.insert("end", f"Grid Status: {status}\n", "info")

        self.term.insert("end", "--- METER DETAILS ---\n", "info")

        for meter_id, meter_data in devices.items():

            if not meter_id.startswith("meter_"):
                continue

            load = meter_data.get("power_consumption", 0)

            self.term.insert(
                "end",
                f"ID: {meter_id:<15} | Load: {load} kW\n",
                "mitm"
            )

        self.term.insert("end", "===============================\n\n", "info")
        self.term.see("end")

    # -------------------------------------------------------------------
    # UI SETUP
    # -------------------------------------------------------------------
    def _setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')

        style.configure(".", background="#1e1e1e", foreground="#ffffff")
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff")
        style.configure("TLabelframe", background="#1e1e1e", foreground="#ffffff")
        style.configure("TLabelframe.Label", background="#1e1e1e", foreground="#ffffff")
        style.configure("TButton", background="#2c2c2c", foreground="#ffffff")

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # ---------- ESPIONAGE ----------
        espionage = ttk.LabelFrame(main, text="Network Espionage (Reconnaissance)")
        espionage.pack(fill="x", pady=5)

        ttk.Label(espionage, text="Intercept status packets to reveal infrastructure details.").pack(
            side="left", padx=10, pady=10
        )
        ttk.Button(espionage, text="GET GRID DATA (SPY)", width=25,
                   command=self.fetch_grid_data).pack(
            side="right", padx=10, pady=10)

        # ---------- ATTACKS ----------
        avail = ttk.LabelFrame(main, text="Availability Attacks (Denial of Service)")
        avail.pack(fill="x", pady=5)

        f = ttk.Frame(avail)
        f.pack(fill="x", pady=15)

        ttk.Button(f, text="TRIGGER BLACKOUT (ALL)",
                   command=lambda: self.send_attack("BLACKOUT")).pack(
            side="left", padx=10, expand=True, fill="x")

        ttk.Button(f, text="LOAD SPIKE ATTACK",
                   command=lambda: self.send_attack("LOAD_SPIKE")).pack(
            side="left", padx=10, expand=True, fill="x")

        ttk.Button(f, text="INDUCE INSTABILITY",
                   command=lambda: self.send_attack("INSTABILITY")).pack(
            side="left", padx=10, expand=True, fill="x")

        # ---------- TARGETED BLACKOUT ----------
        tb = ttk.LabelFrame(main, text="Targeted Blackout")
        tb.pack(fill="x", pady=5)

        ttk.Label(tb, text="Meter ID:").pack(side="left", padx=5)
        tk.Entry(tb, textvariable=self.blackout_target, width=20,
         bg="#2c2c2c", fg="white", insertbackground="white").pack(side="left", padx=5)
        ttk.Button(tb, text="TRIGGER TARGETED BLACKOUT",
                   command=lambda: self.send_attack("BLACKOUT",
                                                    self.blackout_target.get())).pack(
            side="left", padx=10)
        
        ttk.Button(tb, text="RESET TARGETED BLACKOUT",
           command=lambda: self.send_attack("RESET_TARGETED_BLACKOUT",
                                            self.blackout_target.get())).pack(
    side="left", padx=10)

        # ---------- TAMPERING ----------
        integ = ttk.LabelFrame(main, text="Integrity Attacks (Data Injection)")
        integ.pack(fill="x", pady=5)

        ff = ttk.Frame(integ)
        ff.pack(fill="x", pady=10)

        ttk.Label(ff, text="Target Meter ID:").pack(side="left", padx=5)
        tk.Entry(ff, textvariable=self.tamper_target, width=20,
         bg="#2c2c2c", fg="white", insertbackground="white").pack(side="left", padx=5)

        ttk.Label(ff, text="Injection Value:").pack(side="left", padx=5)
        tk.Entry(ff, textvariable=self.tamper_value, width=10,
         bg="#2c2c2c", fg="white", insertbackground="white").pack(side="left", padx=5)

        ttk.Button(ff, text="INJECT PAYLOAD",
                   command=lambda: self.send_attack("TAMPER_METER",
                                                    self.tamper_target.get(),
                                                    self.tamper_value.get())).pack(
            side="left", padx=10)

        ttk.Button(ff, text="RESET INJECTIONS",
                   command=lambda: self.send_attack("RESET_TAMPERS")).pack(
            side="right", padx=10)

        # ---------- OUTPUT ----------
        term_frame = ttk.LabelFrame(main, text="Command & Control Output")
        term_frame.pack(fill="both", expand=True, pady=5)

        self.term = scrolledtext.ScrolledText(
            term_frame, bg="#000000", fg="#00ff9c", font=("Consolas", 10), insertbackground="white"
        )
        self.term.pack(fill="both", expand=True)

        # Coloring
        self.term.tag_config("sent", foreground="#f1c40f") 
        self.term.tag_config("mitm", foreground="#3498db")
        self.term.tag_config("err", foreground="#e74c3c")
        self.term.tag_config("info", foreground="#2ecc71")

    # -------------------------------------------------------------------
    # LOGGING
    # -------------------------------------------------------------------
    def log(self, msg, tag=""):
        self.term.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n", tag)
        self.term.see("end")

    # -------------------------------------------------------------------
    # DEFENSE POLLING
    # -------------------------------------------------------------------
    def poll_defense_status(self):
        """Check if ANY defense system is active."""
        try:
            resp = requests.get(STATUS_ENDPOINT, timeout=3)

            if resp.status_code == 200:
                data = resp.json()

                grid = data.get("grid", {})
                defenses = grid.get("defenses", {})

                auth = defenses.get("authGateway", False)
                firewall = defenses.get("firewall", False)
                anomaly = defenses.get("anomalyDetection", False)

                self.defenses_active = auth or firewall or anomaly

        except:
            pass

        finally:
            if self.is_running:
                self.root.after(1000, self.poll_defense_status)

    # -------------------------------------------------------------------
    # CLOSE APP
    # -------------------------------------------------------------------
    def on_closing(self):
        self.is_running = False
        self.root.destroy()

# -------------------------------------------------------------------
# RUN APP
# -------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = CyberAttackApp(root)
    root.mainloop()
