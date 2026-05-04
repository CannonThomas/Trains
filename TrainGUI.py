# TrainGUI.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import train_config
from TrainController import TrainController

WINDOW_TITLE = "Train Sorter"
WINDOW_SIZE  = "860x900"

CAR_COLORS = {
    "Red":    "#e74c3c",
    "Yellow": "#f1c40f",
    "Orange": "#e67e22",
}


class TrainSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)

        self.log_text = None
        self._pending_logs = []

        self.controller = TrainController(logger=self.log)
        self.controller.on_car_scanned    = self._on_car_scanned
        self.controller.on_status_change  = self._on_status_change
        self.controller.on_drop_confirmed = self._on_drop_confirmed

        # Pre-create StringVars so helper methods can reference them safely
        self._status_var    = tk.StringVar(value="Scan cars first (Step 1).")
        self._next_car_var  = tk.StringVar(value="Next to drop: —")

        self._build_widgets()
        self._flush_pending_logs()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 5}

        # ── STEP 1: Scan ──────────────────────────────────────────────────────
        f1 = ttk.LabelFrame(self.root, text="Step 1 — Scan Car Order (drive past entry reader)", padding=8)
        f1.pack(fill="x", **pad)

        btn_row = ttk.Frame(f1)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="▶  Start Scan", command=self._start_scan).pack(side="left", padx=4)
        ttk.Button(btn_row, text="■  Stop Scan",  command=self._stop_scan).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Clear",         command=self._clear_consist).pack(side="left", padx=4)

        ttk.Label(f1, text="Consist (front → back):").pack(anchor="w", pady=(6, 0))
        self._consist_frame = ttk.Frame(f1)
        self._consist_frame.pack(fill="x")
        self._refresh_consist_display()

        # ── STEP 2: Assign Tracks ─────────────────────────────────────────────
        f2 = ttk.LabelFrame(self.root, text="Step 2 — Assign Destination Tracks", padding=8)
        f2.pack(fill="x", **pad)

        self._dest_inner = None
        self._track_vars: dict = {}
        self._dest_outer = f2
        self._rebuild_dest_panel()

        # ── STEP 3: Sort ──────────────────────────────────────────────────────
        f3 = ttk.LabelFrame(self.root, text="Step 3 — Sort", padding=8)
        f3.pack(fill="x", **pad)

        status_lbl = ttk.Label(
            f3, textvariable=self._status_var,
            relief="sunken", anchor="w", padding=6,
            wraplength=780, justify="left",
            font=("TkDefaultFont", 11, "bold")
        )
        status_lbl.pack(fill="x", pady=(0, 6))

        ttk.Label(f3, textvariable=self._next_car_var).pack(anchor="w")

        sort_btns = ttk.Frame(f3)
        sort_btns.pack(fill="x", pady=4)
        ttk.Button(sort_btns, text="🔀  Fire Switch & Wait",
                   command=self._fire_switch).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="✓  Manual Confirm Drop",
                   command=self.controller.manual_confirm_drop).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="Skip Car",
                   command=self._skip_car).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="Reset All",
                   command=self._reset).pack(side="left", padx=20)

        # ── Track Status ──────────────────────────────────────────────────────
        f4 = ttk.LabelFrame(self.root, text="Track Status", padding=8)
        f4.pack(fill="x", **pad)

        self._track_vars_display = {}
        self._track_labels = {}
        for track in (1, 2, 3):
            var = tk.StringVar(value=f"Track {track}: empty")
            self._track_vars_display[track] = var
            lbl = tk.Label(f4, textvariable=var, width=22, relief="groove",
                           anchor="center", pady=4, font=("TkDefaultFont", 10, "bold"))
            lbl.pack(side="left", padx=6)
            self._track_labels[track] = lbl

        # ── Manual Switch Controls ────────────────────────────────────────────
        f5 = ttk.LabelFrame(self.root, text="Manual Switch Control", padding=8)
        f5.pack(fill="x", **pad)

        for sw in ("S1", "S2", "S3"):
            row = ttk.Frame(f5)
            row.pack(side="left", padx=10)
            ttk.Label(row, text=sw, width=4).pack(side="left")
            ttk.Button(row, text="LEFT",
                       command=lambda s=sw: self.run_bg(
                           lambda sw=s: self.controller.manual_pulse(sw, "LEFT")
                       )).pack(side="left", padx=2)
            ttk.Button(row, text="RIGHT",
                       command=lambda s=sw: self.run_bg(
                           lambda sw=s: self.controller.manual_pulse(sw, "RIGHT")
                       )).pack(side="left", padx=2)

        ttk.Button(f5, text="All Straight",
                   command=lambda: self.run_bg(self.controller.manual_all_straight)
                   ).pack(side="left", padx=16)

        # ── Track Power (L298 H-bridge) ───────────────────────────────────────
        f_track = ttk.LabelFrame(self.root, text="Track Power", padding=8)
        f_track.pack(fill="x", **pad)

        dir_row = ttk.Frame(f_track)
        dir_row.pack(fill="x")
        ttk.Label(dir_row, text="Direction:").pack(side="left", padx=(0, 6))
        self._paused = False
        self._saved_dir   = "STOP"
        self._saved_speed = 0
        ttk.Button(dir_row, text="◀ REV",
                   command=lambda: self._set_dir("REV")
                   ).pack(side="left", padx=2)
        self._pause_btn = ttk.Button(dir_row, text="■ PAUSE",
                                     command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=2)
        ttk.Button(dir_row, text="FWD ▶",
                   command=lambda: self._set_dir("FWD")
                   ).pack(side="left", padx=2)

        speed_row = ttk.Frame(f_track)
        speed_row.pack(fill="x", pady=(6, 0))
        ttk.Label(speed_row, text="Speed:").pack(side="left", padx=(0, 6))
        self._speed_var = tk.IntVar(value=0)
        self._speed_label_var = tk.StringVar(value="0%  (~0.0V)")
        speed_scale = ttk.Scale(
            speed_row, from_=0, to=100, orient="horizontal",
            variable=self._speed_var, command=self._on_speed_change,
        )
        speed_scale.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(speed_row, textvariable=self._speed_label_var,
                  width=14).pack(side="left", padx=4)

        # ── RFID Test ─────────────────────────────────────────────────────────
        f6 = ttk.LabelFrame(self.root, text="RFID Test", padding=8)
        f6.pack(fill="x", **pad)

        reader_labels = ["Entry (RFID1)", "Track 1 end (RFID2)",
                         "Track 2 end (RFID3)", "Track 3 end (RFID4)"]
        for i, label in enumerate(reader_labels):
            ttk.Button(
                f6, text=f"Test {label}",
                command=lambda idx=i: self.run_bg(
                    lambda i=idx: self.controller.test_reader(i)
                )
            ).pack(side="left", padx=4)

        ttk.Button(f6, text="Diagnose All",
                   command=lambda: self.run_bg(self.controller.rfid.diagnose)
                   ).pack(side="left", padx=8)
        ttk.Button(f6, text="Show State",
                   command=self.controller.show_state).pack(side="left", padx=8)

        # ── Mock mode ─────────────────────────────────────────────────────────
        misc = ttk.Frame(self.root)
        misc.pack(fill="x", padx=10, pady=2)
        self._mock_var = tk.BooleanVar(value=train_config.MOCK_MODE)
        ttk.Checkbutton(misc, text="Mock Mode (no hardware)",
                        variable=self._mock_var,
                        command=self._toggle_mock).pack(side="left")

        # ── Log ───────────────────────────────────────────────────────────────
        f7 = ttk.LabelFrame(self.root, text="Log", padding=8)
        f7.pack(fill="both", expand=True, **pad)

        self.log_text = tk.Text(f7, wrap="word", height=12)
        sb = ttk.Scrollbar(f7, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ── Dynamic panels ────────────────────────────────────────────────────────

    def _refresh_consist_display(self):
        for w in self._consist_frame.winfo_children():
            w.destroy()
        if not self.controller.car_order:
            ttk.Label(self._consist_frame, text="(none yet)",
                      foreground="gray").pack(side="left", padx=4)
        else:
            for i, car in enumerate(self.controller.car_order):
                color = CAR_COLORS.get(car, "#555555")
                lbl = tk.Label(self._consist_frame,
                               text=f"{i+1}. {car}",
                               bg=color, fg="white",
                               relief="groove", padx=8, pady=4,
                               font=("TkDefaultFont", 10, "bold"))
                lbl.pack(side="left", padx=3)
        self._update_next_car_label()

    def _rebuild_dest_panel(self):
        if self._dest_inner:
            self._dest_inner.destroy()
        self._dest_inner = ttk.Frame(self._dest_outer)
        self._dest_inner.pack(fill="x")
        self._track_vars = {}

        cars = list(train_config.CAR_ROSTER.keys())
        if not cars:
            ttk.Label(self._dest_inner,
                      text="No cars in roster yet — add UIDs to car_roster.json",
                      foreground="gray").grid(row=0, column=0, padx=5, pady=3)
            return

        for col, car_name in enumerate(cars):
            default = self.controller.car_destinations.get(car_name, 1)
            ttk.Label(self._dest_inner, text=car_name,
                      width=10).grid(row=0, column=col*3,   padx=4, pady=3)
            var = tk.IntVar(value=default)
            self._track_vars[car_name] = var
            ttk.Combobox(self._dest_inner, textvariable=var,
                         values=[1, 2, 3], state="readonly",
                         width=5).grid(row=0, column=col*3+1, padx=2, pady=3)
            ttk.Button(self._dest_inner, text="Set",
                       command=lambda c=car_name, v=var:
                           self.controller.set_destination(c, int(v.get()))
                       ).grid(row=0, column=col*3+2, padx=2, pady=3)

    def _update_next_car_label(self):
        car = self.controller.next_car
        if car:
            track = self.controller.car_destinations.get(car, "?")
            self._next_car_var.set(f"Next to drop (back of train): {car} → Track {track}")
        else:
            self._next_car_var.set("Next to drop: — (no cars in consist)")

    # ── Controller callbacks (called from background threads) ─────────────────

    def _on_car_scanned(self, car_name):
        self.root.after(0, self._refresh_consist_display)

    def _on_status_change(self, msg):
        self.root.after(0, lambda m=msg: self._status_var.set(m))
        self.root.after(0, self._update_next_car_label)

    def _on_drop_confirmed(self, car_name, track):
        def _update():
            self._track_vars_display[track].set(f"Track {track}: {car_name}")
            color = CAR_COLORS.get(car_name, "#27ae60")
            self._track_labels[track].configure(bg=color, fg="white")
            self._refresh_consist_display()
        self.root.after(0, _update)

    # ── Button handlers ───────────────────────────────────────────────────────

    def _start_scan(self):
        self.run_bg(self.controller.start_entry_scan)

    def _stop_scan(self):
        self.controller.stop_entry_scan()
        self.root.after(0, self._refresh_consist_display)

    def _clear_consist(self):
        self.controller.clear_consist()
        self.root.after(0, self._refresh_consist_display)

    def _fire_switch(self):
        self.run_bg(self.controller.fire_switch_for_next_car)

    def _skip_car(self):
        self.controller.skip_car()
        self.root.after(0, self._refresh_consist_display)

    def _reset(self):
        self.controller.reset()
        for t in (1, 2, 3):
            self._track_vars_display[t].set(f"Track {t}: empty")
            self._track_labels[t].configure(bg="SystemButtonFace", fg="black")
        self.root.after(0, self._refresh_consist_display)

    def _set_dir(self, direction: str):
        """Direct FWD/REV press — clears pause state and applies new direction."""
        if self._paused:
            self._paused = False
            self._pause_btn.configure(text="■ PAUSE")
        self.run_bg(lambda d=direction: self.controller.track.set_direction(d))

    def _toggle_pause(self):
        if not self._paused:
            # Remember direction so resume restores it
            self._saved_dir = self.controller.track.direction
            self._paused = True
            self._pause_btn.configure(text="▶ RESUME")
            self.run_bg(self.controller.track.stop)
        else:
            # Resume — controller preserved speed_pct through stop()
            saved_dir = self._saved_dir if self._saved_dir in ("FWD", "REV") else "FWD"
            self._paused = False
            self._pause_btn.configure(text="■ PAUSE")
            self.run_bg(lambda d=saved_dir: self.controller.track.set_direction(d))

    def _on_speed_change(self, _val):
        pct = int(float(_val))
        # Estimate output voltage: duty * (Vin - L298 dropout)
        max_duty = train_config.TRACK_MAX_DUTY / 100.0
        duty = pct / 100.0 * max_duty
        est_v = duty * (train_config.TRACK_INPUT_VOLTS - 2.0)
        self._speed_label_var.set(f"{pct}%  (~{est_v:.1f}V)")
        self.run_bg(lambda p=pct: self.controller.track.set_speed(p))

    def _toggle_mock(self):
        train_config.MOCK_MODE = self._mock_var.get()
        self.log(f"[CONFIG] MOCK_MODE = {train_config.MOCK_MODE}")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _append_log(self, msg):
        if self.log_text is None:
            self._pending_logs.append(msg)
            print(msg)
            return
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        print(msg)

    def _flush_pending_logs(self):
        if not self.log_text:
            return
        for msg in self._pending_logs:
            self.log_text.insert("end", msg + "\n")
        if self._pending_logs:
            self.log_text.see("end")
        self._pending_logs.clear()

    def log(self, msg):
        try:
            self.root.after(0, lambda m=msg: self._append_log(m))
        except Exception:
            print(msg)

    def run_bg(self, target):
        threading.Thread(target=target, daemon=True).start()

    def on_close(self):
        try:
            self.controller.shutdown()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    TrainSorterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
