# TrainGUI.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import train_config
from TrainController import TrainController

WINDOW_TITLE = "Train Sorter Control"
WINDOW_SIZE  = "1000x980"

# ── Theme palette ────────────────────────────────────────────────────────────
BG_DARK      = "#1e272e"   # window bg
BG_PANEL     = "#2f3640"   # frame bg
BG_CARD      = "#353b48"   # tile bg
FG_TEXT      = "#f5f6fa"   # primary text
FG_MUTED     = "#7f8fa6"   # muted text
ACCENT_BLUE  = "#3498db"
ACCENT_GREEN = "#1abc9c"
ACCENT_GOLD  = "#f39c12"
ACCENT_RED   = "#e74c3c"
BORDER_LINE  = "#576574"

CAR_COLORS = {
    "Santa Fe": "#b71c1c",   # deep Santa Fe warbonnet red
    "Yellow":   "#f1c40f",   # bright yellow
    "Triangle": "#e67e22",   # orange
}

# Unicode glyph for each car so it's recognisable beyond color alone
CAR_ICONS = {
    "Santa Fe": "✦",   # star — Santa Fe nose emblem vibe
    "Yellow":   "●",   # filled circle
    "Triangle": "▲",   # literal triangle
}


def _apply_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG_DARK)

    style.configure(".",
        background=BG_PANEL, foreground=FG_TEXT,
        fieldbackground=BG_CARD, bordercolor=BORDER_LINE,
        font=("Helvetica", 10))
    style.configure("TFrame", background=BG_PANEL)
    style.configure("TLabel", background=BG_PANEL, foreground=FG_TEXT)
    style.configure("Muted.TLabel", foreground=FG_MUTED)
    style.configure("Header.TLabel",
        background=BG_DARK, foreground=ACCENT_BLUE,
        font=("Helvetica", 18, "bold"))
    style.configure("SubHeader.TLabel",
        background=BG_DARK, foreground=FG_MUTED,
        font=("Helvetica", 10, "italic"))
    style.configure("TLabelframe",
        background=BG_PANEL, foreground=ACCENT_GREEN,
        bordercolor=BORDER_LINE, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label",
        background=BG_PANEL, foreground=ACCENT_GREEN,
        font=("Helvetica", 11, "bold"))
    style.configure("TButton",
        background=BG_CARD, foreground=FG_TEXT,
        bordercolor=BORDER_LINE, padding=(10, 6),
        font=("Helvetica", 10, "bold"))
    style.map("TButton",
        background=[("active", ACCENT_BLUE), ("pressed", ACCENT_BLUE)],
        foreground=[("active", "white")])
    style.configure("Go.TButton", background=ACCENT_GREEN, foreground="white")
    style.map("Go.TButton", background=[("active", "#16a085")])
    style.configure("ActiveSpeed.TButton",
        background=ACCENT_GREEN, foreground="white",
        bordercolor="white", relief="raised", borderwidth=3,
        font=("Helvetica", 10, "bold"))
    style.map("ActiveSpeed.TButton", background=[("active", "#16a085")])
    style.configure("InactiveSpeed.TButton",
        background=BG_CARD, foreground=FG_TEXT,
        font=("Helvetica", 10, "bold"))
    style.map("InactiveSpeed.TButton", background=[("active", ACCENT_BLUE)])
    style.configure("Stop.TButton", background=ACCENT_RED, foreground="white")
    style.map("Stop.TButton", background=[("active", "#c0392b")])
    style.configure("Warn.TButton", background=ACCENT_GOLD, foreground="white")
    style.map("Warn.TButton", background=[("active", "#d68910")])
    style.configure("TCheckbutton", background=BG_PANEL, foreground=FG_TEXT)
    style.configure("TCombobox",
        fieldbackground=BG_CARD, background=BG_CARD, foreground=FG_TEXT,
        bordercolor=BORDER_LINE, arrowcolor=FG_TEXT)
    style.configure("Horizontal.TScale",
        background=BG_PANEL, troughcolor=BG_CARD)


class TrainSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        _apply_theme(root)

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

        # Always run the live track monitor in the background
        self.controller.start_track_monitor()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_scroll_container(self):
        """Wrap the whole GUI in a scrollable canvas so it scrolls vertically."""
        outer = tk.Frame(self.root, bg=BG_DARK)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = tk.Frame(canvas, bg=BG_DARK)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_configure(e):
            canvas.itemconfigure(window_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scrolling (Linux uses Button-4/5; macOS/Windows use MouseWheel)
        def _on_mousewheel(e):
            if e.num == 4 or e.delta > 0:
                canvas.yview_scroll(-3, "units")
            elif e.num == 5 or e.delta < 0:
                canvas.yview_scroll(3, "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        return inner

    def _build_widgets(self):
        # Build a scrollable container and route all section frames to it
        # by aliasing self._parent. The original self.root stays as the Tk window.
        content = self._build_scroll_container()
        # Override self.root for the rest of this build only — restored at end
        _orig_root = self.root
        self.root = content
        pad = {"padx": 12, "pady": 6}
        # Note: all the existing `self.root.pack(...)` calls below now pack into
        # the scrollable frame. We restore the real root at the end of this method.

        # ── Title bar ─────────────────────────────────────────────────────────
        title_bar = tk.Frame(self.root, bg=BG_DARK)
        title_bar.pack(fill="x", padx=12, pady=(10, 0))
        ttk.Label(title_bar, text="🚂  TRAIN SORTER CONTROL",
                  style="Header.TLabel").pack(side="left")
        ttk.Label(title_bar, text="  ·  Pi 5 + RC522 + L298",
                  style="SubHeader.TLabel").pack(side="left", padx=(8, 0))

        # ── STEP 1: Scan ──────────────────────────────────────────────────────
        f1 = ttk.LabelFrame(self.root, text="① Scan Car Order — drive past entry reader", padding=10)
        f1.pack(fill="x", **pad)

        btn_row = ttk.Frame(f1)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="▶  Start Scan", style="Go.TButton",
                   command=self._start_scan).pack(side="left", padx=4)
        ttk.Button(btn_row, text="■  Stop Scan", style="Stop.TButton",
                   command=self._stop_scan).pack(side="left", padx=4)
        ttk.Button(btn_row, text="✖  Clear", style="Warn.TButton",
                   command=self._clear_consist).pack(side="left", padx=4)

        ttk.Label(f1, text="Consist (front → back):").pack(anchor="w", pady=(6, 0))
        self._consist_frame = ttk.Frame(f1)
        self._consist_frame.pack(fill="x")
        self._refresh_consist_display()

        # ── STEP 2: Assign Tracks ─────────────────────────────────────────────
        f2 = ttk.LabelFrame(self.root, text="② Assign Destination Tracks", padding=10)
        f2.pack(fill="x", **pad)

        self._dest_inner = None
        self._track_vars: dict = {}
        self._dest_outer = f2
        self._rebuild_dest_panel()

        # ── STEP 3: Sort ──────────────────────────────────────────────────────
        f3 = ttk.LabelFrame(self.root, text="③ Sort", padding=10)
        f3.pack(fill="x", **pad)

        status_lbl = tk.Label(
            f3, textvariable=self._status_var,
            anchor="w", padx=10, pady=8,
            wraplength=900, justify="left",
            bg=BG_CARD, fg=ACCENT_GOLD,
            relief="flat", borderwidth=0,
            font=("Helvetica", 11, "bold"))
        status_lbl.pack(fill="x", pady=(0, 6))

        ttk.Label(f3, textvariable=self._next_car_var,
                  style="Muted.TLabel").pack(anchor="w")

        sort_btns = ttk.Frame(f3)
        sort_btns.pack(fill="x", pady=8)
        ttk.Button(sort_btns, text="🔀  Fire Switch & Wait", style="Go.TButton",
                   command=self._fire_switch).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="✓  Manual Confirm Drop",
                   command=self.controller.manual_confirm_drop).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="⏭  Skip Car",
                   command=self._skip_car).pack(side="left", padx=4)
        ttk.Button(sort_btns, text="↺  Reset All", style="Stop.TButton",
                   command=self._reset).pack(side="right", padx=4)

        # ── Autonomous ────────────────────────────────────────────────────────
        f_auto = ttk.LabelFrame(self.root, text="🤖  Autonomous Run", padding=10)
        f_auto.pack(fill="x", **pad)

        auto_row = ttk.Frame(f_auto)
        auto_row.pack(fill="x")
        ttk.Label(auto_row, text="Pickup order (e.g. 1,2,3):",
                  font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 6))
        self._pickup_order_var = tk.StringVar(value="1,2,3")
        ttk.Entry(auto_row, textvariable=self._pickup_order_var,
                  width=10).pack(side="left", padx=4)
        ttk.Button(auto_row, text="▶  Start Autonomous", style="Go.TButton",
                   command=self._start_autonomous).pack(side="left", padx=8)
        ttk.Button(auto_row, text="■  Abort", style="Stop.TButton",
                   command=self.controller.abort_autonomous
                   ).pack(side="left", padx=4)

        ttk.Label(auto_row, text="👁 Live Track Monitor: ON",
                  foreground=ACCENT_GREEN,
                  font=("Helvetica", 10, "bold")).pack(side="right", padx=4)

        # ── Track Status ──────────────────────────────────────────────────────
        f4 = ttk.LabelFrame(self.root, text="🚉  Track Status", padding=10)
        f4.pack(fill="x", **pad)

        self._track_vars_display = {}
        self._track_labels = {}
        tile_row = ttk.Frame(f4)
        tile_row.pack(fill="x", expand=True)
        for track in (1, 2, 3):
            var = tk.StringVar(value=f"TRACK {track}\n\n— empty —")
            self._track_vars_display[track] = var
            lbl = tk.Label(tile_row, textvariable=var, width=20, height=4,
                           relief="flat", borderwidth=2,
                           anchor="center",
                           bg=BG_CARD, fg=FG_MUTED,
                           highlightthickness=2, highlightbackground=BORDER_LINE,
                           font=("Helvetica", 12, "bold"))
            lbl.pack(side="left", padx=8, ipady=8, fill="both", expand=True)
            self._track_labels[track] = lbl

        # ── Manual Switch Controls ────────────────────────────────────────────
        f5 = ttk.LabelFrame(self.root, text="⇄  Manual Switch Control", padding=10)
        f5.pack(fill="x", **pad)

        for sw in ("S1", "S2", "S3"):
            row = ttk.Frame(f5)
            row.pack(side="left", padx=12)
            ttk.Label(row, text=sw, width=4,
                      font=("Helvetica", 11, "bold")).pack(side="left")
            ttk.Button(row, text="◀ LEFT",
                       command=lambda s=sw: self.run_bg(
                           lambda sw=s: self.controller.manual_pulse(sw, "LEFT")
                       )).pack(side="left", padx=2)
            ttk.Button(row, text="RIGHT ▶",
                       command=lambda s=sw: self.run_bg(
                           lambda sw=s: self.controller.manual_pulse(sw, "RIGHT")
                       )).pack(side="left", padx=2)

        ttk.Button(f5, text="↑  All Straight", style="Go.TButton",
                   command=lambda: self.run_bg(self.controller.manual_all_straight)
                   ).pack(side="right", padx=8)

        # ── Track Power (L298 H-bridge) ───────────────────────────────────────
        f_track = ttk.LabelFrame(self.root, text="⚡  Track Power", padding=10)
        f_track.pack(fill="x", **pad)

        dir_row = ttk.Frame(f_track)
        dir_row.pack(fill="x")
        ttk.Label(dir_row, text="Direction:",
                  font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 8))
        self._paused = False
        self._saved_dir   = "STOP"
        self._saved_speed = 0
        ttk.Button(dir_row, text="◀  REV",
                   command=lambda: self._set_dir("REV")
                   ).pack(side="left", padx=3)
        self._pause_btn = ttk.Button(dir_row, text="■  PAUSE", style="Stop.TButton",
                                     command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=3)
        ttk.Button(dir_row, text="FWD  ▶", style="Go.TButton",
                   command=lambda: self._set_dir("FWD")
                   ).pack(side="left", padx=3)

        speed_row = ttk.Frame(f_track)
        speed_row.pack(fill="x", pady=(10, 0))
        ttk.Label(speed_row, text="Speed:",
                  font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 8))
        self._speed_var = tk.IntVar(value=0)
        self._speed_label_var = tk.StringVar(value="OFF  (0V)")

        self._slow_btn = ttk.Button(speed_row, text="🐢  SLOW (40%)",
                                    style="InactiveSpeed.TButton",
                                    command=lambda: self._set_preset_speed(40))
        self._slow_btn.pack(side="left", padx=4)
        self._fast_btn = ttk.Button(speed_row, text="🐇  FAST (80%)",
                                    style="InactiveSpeed.TButton",
                                    command=lambda: self._set_preset_speed(80))
        self._fast_btn.pack(side="left", padx=4)
        ttk.Button(speed_row, text="⏹  OFF", style="Stop.TButton",
                   command=lambda: self._set_preset_speed(0)
                   ).pack(side="left", padx=4)

        tk.Label(speed_row, textvariable=self._speed_label_var, width=18,
                 bg=BG_CARD, fg=ACCENT_GOLD,
                 font=("Helvetica", 11, "bold"),
                 padx=10, pady=4).pack(side="right", padx=4)

        # ── RFID Test ─────────────────────────────────────────────────────────
        f6 = ttk.LabelFrame(self.root, text="📡  RFID Test", padding=10)
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
        f7 = ttk.LabelFrame(self.root, text="📜  Log", padding=10)
        f7.pack(fill="both", expand=True, **pad)

        self.log_text = tk.Text(f7, wrap="word", height=10,
                                bg="#1e272e", fg="#dfe6e9",
                                insertbackground=FG_TEXT,
                                relief="flat", borderwidth=0,
                                font=("Menlo", 10))
        sb = ttk.Scrollbar(f7, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Restore real Tk root so root.after / protocol still work elsewhere
        self.root = _orig_root

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
                icon = CAR_ICONS.get(car, "■")
                lbl = tk.Label(self._consist_frame,
                               text=f"{i+1}. {icon} {car}",
                               bg=color, fg="white",
                               relief="groove", padx=10, pady=6,
                               font=("Helvetica", 11, "bold"))
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
            if car_name:
                icon = CAR_ICONS.get(car_name, "●")
                self._track_vars_display[track].set(
                    f"TRACK {track}\n\n{icon}  {car_name.upper()}  {icon}\nFULL")
                color = CAR_COLORS.get(car_name, "#27ae60")
                self._track_labels[track].configure(
                    bg=color, fg="white",
                    highlightbackground="white", highlightthickness=3)
            else:
                # No car detected — reset to empty state
                self._track_vars_display[track].set(
                    f"TRACK {track}\n\n— empty —")
                self._track_labels[track].configure(
                    bg=BG_CARD, fg=FG_MUTED,
                    highlightbackground=BORDER_LINE, highlightthickness=2)
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
            self._track_vars_display[t].set(f"TRACK {t}\n\n— empty —")
            self._track_labels[t].configure(
                bg=BG_CARD, fg=FG_MUTED,
                highlightbackground=BORDER_LINE, highlightthickness=2)
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

    def _set_preset_speed(self, pct: int):
        max_duty = train_config.TRACK_MAX_DUTY / 100.0
        duty = pct / 100.0 * max_duty
        est_v = duty * (train_config.TRACK_INPUT_VOLTS - 2.0)
        if pct == 0:
            self._speed_label_var.set("OFF  (0V)")
        else:
            self._speed_label_var.set(f"{pct}%  (~{est_v:.1f}V)")
        self._speed_var.set(pct)

        # Highlight whichever speed button is active
        self._slow_btn.configure(
            style="ActiveSpeed.TButton" if pct == 40 else "InactiveSpeed.TButton")
        self._fast_btn.configure(
            style="ActiveSpeed.TButton" if pct == 80 else "InactiveSpeed.TButton")

        self.run_bg(lambda p=pct: self.controller.track.set_speed(p))

    def _start_autonomous(self):
        try:
            order = [int(x.strip()) for x in self._pickup_order_var.get().split(",") if x.strip()]
        except ValueError:
            self.log("[AUTO] invalid pickup order — use comma-separated track numbers")
            return
        self.controller.start_autonomous(order)

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
