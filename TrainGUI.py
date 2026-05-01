# TrainGUI.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import train_config
from train_config import WINDOW_TITLE, WINDOW_SIZE
from TrainController import TrainController


class TrainSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)

        self.log_text = None
        self._pending_logs = []

        self.controller = TrainController(logger=self.log)

        # Registration state
        self._scanned_uid = tk.StringVar(value="")
        self._scanned_reader = tk.StringVar(value="")
        self._reg_car_name = tk.StringVar()
        self._reg_track_var = tk.IntVar(value=1)

        # Scrollable main canvas so the window can accommodate all panels
        canvas = tk.Canvas(root)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)
        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._build_widgets()
        self._flush_pending_logs()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── Widget construction ───────────────────────────────────────────────────

    def _build_widgets(self):
        f = self._scroll_frame

        # ── Main controls ─────────────────────────────────────────────────────
        top = ttk.LabelFrame(f, text="Main Controls", padding=8)
        top.pack(fill="x", padx=10, pady=6)

        ttk.Button(top, text="Start Sort",  command=self.start_sort).pack(side="left", padx=5)
        ttk.Button(top, text="Stop",        command=self.stop_sort).pack(side="left", padx=5)
        ttk.Button(top, text="Reset",       command=self.reset_system).pack(side="left", padx=5)
        ttk.Button(top, text="Show State",  command=self.controller.show_state).pack(side="left", padx=5)

        self._mock_var = tk.BooleanVar(value=train_config.MOCK_MODE)
        ttk.Checkbutton(
            top, text="Mock Mode",
            variable=self._mock_var, command=self._toggle_mock_mode,
        ).pack(side="left", padx=12)

        # ── RFID Registration ─────────────────────────────────────────────────
        reg = ttk.LabelFrame(f, text="RFID Registration", padding=8)
        reg.pack(fill="x", padx=10, pady=6)

        scan_row = ttk.Frame(reg)
        scan_row.pack(fill="x", pady=2)
        ttk.Button(scan_row, text="Scan All Readers", command=self._start_scan_for_registration).pack(side="left", padx=4)
        ttk.Label(scan_row, text="Reader:").pack(side="left", padx=(10, 2))
        ttk.Label(scan_row, textvariable=self._scanned_reader, width=8, relief="sunken").pack(side="left", padx=2)
        ttk.Label(scan_row, text="UID:").pack(side="left", padx=(10, 2))
        ttk.Label(scan_row, textvariable=self._scanned_uid, width=12, relief="sunken", font=("Courier", 10)).pack(side="left", padx=2)

        reg_row = ttk.Frame(reg)
        reg_row.pack(fill="x", pady=2)
        ttk.Label(reg_row, text="Car name:").pack(side="left", padx=4)
        ttk.Entry(reg_row, textvariable=self._reg_car_name, width=14).pack(side="left", padx=4)
        ttk.Label(reg_row, text="→ Track:").pack(side="left", padx=(8, 2))
        ttk.Combobox(
            reg_row, textvariable=self._reg_track_var,
            values=[1, 2, 3], state="readonly", width=5
        ).pack(side="left", padx=4)
        ttk.Button(reg_row, text="Register Tag", command=self._register_car).pack(side="left", padx=8)
        ttk.Button(reg_row, text="Clear", command=self._clear_registration_fields).pack(side="left", padx=2)

        # Roster table
        roster_frame = ttk.Frame(reg)
        roster_frame.pack(fill="x", pady=4)

        cols = ("car", "uid", "track")
        self._roster_tree = ttk.Treeview(
            roster_frame, columns=cols, show="headings", height=5
        )
        self._roster_tree.heading("car",   text="Car Name")
        self._roster_tree.heading("uid",   text="RFID UID")
        self._roster_tree.heading("track", text="Default Track")
        self._roster_tree.column("car",   width=120)
        self._roster_tree.column("uid",   width=120)
        self._roster_tree.column("track", width=100)
        self._roster_tree.pack(side="left", fill="x", expand=True)

        tree_scroll = ttk.Scrollbar(roster_frame, orient="vertical", command=self._roster_tree.yview)
        self._roster_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")

        ttk.Button(reg, text="Delete Selected Car", command=self._delete_selected_car).pack(anchor="w", pady=2)

        self._refresh_roster_tree()

        # ── Car Destination Assignment (rebuilt dynamically) ──────────────────
        self._dest_outer = ttk.LabelFrame(f, text="Car Destination Assignment", padding=8)
        self._dest_outer.pack(fill="x", padx=10, pady=6)
        self._dest_inner = None
        self._track_vars: dict = {}
        self._rebuild_destination_panel()

        # ── Consist Order ─────────────────────────────────────────────────────
        self._consist_outer = ttk.LabelFrame(f, text="Consist Order (front → back)", padding=8)
        self._consist_outer.pack(fill="x", padx=10, pady=6)
        self._consist_listbox = None
        self._rebuild_consist_panel()

        # ── Manual Test Controls ──────────────────────────────────────────────
        manual = ttk.LabelFrame(f, text="Manual Test Controls", padding=8)
        manual.pack(fill="x", padx=10, pady=6)

        ttk.Button(manual, text="Route Track 1", command=lambda: self.controller.manual_route_track(1)).pack(side="left", padx=4)
        ttk.Button(manual, text="Route Track 2", command=lambda: self.controller.manual_route_track(2)).pack(side="left", padx=4)
        ttk.Button(manual, text="Route Track 3", command=lambda: self.controller.manual_route_track(3)).pack(side="left", padx=4)
        ttk.Button(manual, text="Main Line",     command=self.controller.manual_route_main).pack(side="left", padx=4)
        ttk.Button(manual, text="Decouple",      command=self.run_manual_decouple).pack(side="left", padx=4)
        ttk.Button(manual, text="Victory Lap",   command=self.run_victory_lap).pack(side="left", padx=4)

        # ── RFID Test Controls ────────────────────────────────────────────────
        rfid_frame = ttk.LabelFrame(f, text="RFID Test Controls", padding=8)
        rfid_frame.pack(fill="x", padx=10, pady=6)

        ttk.Button(rfid_frame, text="Scan (log only)",  command=self.scan_rfid_log).pack(side="left", padx=4)
        ttk.Button(rfid_frame, text="Scan + Route",     command=self.scan_and_route).pack(side="left", padx=4)

        reader_names = [r["name"] for r in train_config.RFID_READERS]
        for i, name in enumerate(reader_names):
            ttk.Button(
                rfid_frame,
                text=f"Poll {name}",
                command=lambda idx=i: self.run_background(lambda i=idx: self._poll_single_reader(i))
            ).pack(side="left", padx=4)

        # ── DCC Controls ─────────────────────────────────────────────────────
        dcc_frame = ttk.LabelFrame(f, text="DCC / H-Bridge Test Controls", padding=8)
        dcc_frame.pack(fill="x", padx=10, pady=6)

        ttk.Button(dcc_frame, text="DCC Idle",    command=self.dcc_idle).pack(side="left", padx=4)
        ttk.Button(dcc_frame, text="DCC Forward", command=self.dcc_forward).pack(side="left", padx=4)
        ttk.Button(dcc_frame, text="DCC Reverse", command=self.dcc_reverse).pack(side="left", padx=4)
        ttk.Button(dcc_frame, text="DCC Stop",    command=self.dcc_stop).pack(side="left", padx=4)

        # ── System Log ────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(f, text="System Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.log_text = tk.Text(log_frame, wrap="word", height=18)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    # ── Dynamic panel builders ────────────────────────────────────────────────

    def _rebuild_destination_panel(self):
        if self._dest_inner:
            self._dest_inner.destroy()
        self._dest_inner = ttk.Frame(self._dest_outer)
        self._dest_inner.pack(fill="x")
        self._track_vars = {}

        cars = list(train_config.CAR_ROSTER.keys())
        if not cars:
            ttk.Label(self._dest_inner, text="No cars registered yet.").pack(anchor="w")
            return

        for row_i, car_name in enumerate(cars):
            default = self.controller.car_destinations.get(car_name, 1)
            ttk.Label(self._dest_inner, text=car_name, width=14).grid(
                row=row_i, column=0, padx=5, pady=3, sticky="w"
            )
            var = tk.IntVar(value=default)
            self._track_vars[car_name] = var
            combo = ttk.Combobox(
                self._dest_inner, textvariable=var,
                values=[1, 2, 3], state="readonly", width=8
            )
            combo.grid(row=row_i, column=1, padx=5, pady=3)
            ttk.Button(
                self._dest_inner, text="Apply",
                command=lambda c=car_name, v=var: self.controller.set_destination(c, int(v.get()))
            ).grid(row=row_i, column=2, padx=5, pady=3)

    def _rebuild_consist_panel(self):
        # Clear the frame
        for w in self._consist_outer.winfo_children():
            w.destroy()

        cars = list(train_config.CAR_ROSTER.keys())

        ttk.Label(self._consist_outer, text="Drag order with Up/Down buttons. Position 1 = first car dropped.").pack(anchor="w")

        lb_frame = ttk.Frame(self._consist_outer)
        lb_frame.pack(fill="x", pady=4)

        self._consist_listbox = tk.Listbox(lb_frame, height=6, selectmode="single", exportselection=False)
        for car in self.controller.consist if self.controller.consist else cars:
            self._consist_listbox.insert("end", car)
        self._consist_listbox.pack(side="left", fill="x", expand=True)

        btn_col = ttk.Frame(lb_frame)
        btn_col.pack(side="left", padx=6)
        ttk.Button(btn_col, text="▲ Up",   command=self._consist_move_up).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="▼ Down", command=self._consist_move_down).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="Apply Consist", command=self._apply_consist_order).pack(fill="x", pady=6)

    # ── Roster helpers ────────────────────────────────────────────────────────

    def _refresh_roster_tree(self):
        self._roster_tree.delete(*self._roster_tree.get_children())
        for name, info in train_config.CAR_ROSTER.items():
            self._roster_tree.insert("", "end", values=(name, info["rfid"], info["default_track"]))

    # ── Registration flow ─────────────────────────────────────────────────────

    def _start_scan_for_registration(self):
        self._scanned_uid.set("scanning…")
        self._scanned_reader.set("")
        self.run_background(self._do_scan_for_registration)

    def _do_scan_for_registration(self):
        reader_idx, uid = self.controller.rfid.scan_all(timeout_sec=5.0)
        if uid is None:
            self.root.after(0, lambda: self._scanned_uid.set("(none)"))
            self.root.after(0, lambda: self._scanned_reader.set(""))
            self.log("[REG] No tag detected within 5 s")
        else:
            rname = train_config.RFID_READERS[reader_idx]["name"]
            self.root.after(0, lambda: self._scanned_uid.set(uid))
            self.root.after(0, lambda: self._scanned_reader.set(rname))
            # Pre-fill car name if this UID is already known
            known = self.controller.rfid.identify_car(uid)
            if known:
                self.root.after(0, lambda: self._reg_car_name.set(known))
            self.log(f"[REG] Scanned {uid} on {rname}")

    def _register_car(self):
        uid = self._scanned_uid.get().strip()
        name = self._reg_car_name.get().strip()
        track = self._reg_track_var.get()

        if not uid or uid in ("scanning…", "(none)"):
            messagebox.showwarning("Registration", "Scan a tag first.")
            return
        if not name:
            messagebox.showwarning("Registration", "Enter a car name.")
            return

        ok = self.controller.register_car(name, uid, track)
        if ok:
            self._refresh_roster_tree()
            self._rebuild_destination_panel()
            self._rebuild_consist_panel()
            self._clear_registration_fields()
            self.log(f"[GUI] Registered {name}")

    def _clear_registration_fields(self):
        self._scanned_uid.set("")
        self._scanned_reader.set("")
        self._reg_car_name.set("")
        self._reg_track_var.set(1)

    def _delete_selected_car(self):
        sel = self._roster_tree.selection()
        if not sel:
            return
        car_name = self._roster_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Delete Car", f"Remove '{car_name}' from the roster?"):
            self.controller.unregister_car(car_name)
            self._refresh_roster_tree()
            self._rebuild_destination_panel()
            self._rebuild_consist_panel()

    # ── Consist order helpers ─────────────────────────────────────────────────

    def _consist_move_up(self):
        lb = self._consist_listbox
        idx = lb.curselection()
        if not idx or idx[0] == 0:
            return
        i = idx[0]
        val = lb.get(i)
        lb.delete(i)
        lb.insert(i - 1, val)
        lb.selection_set(i - 1)

    def _consist_move_down(self):
        lb = self._consist_listbox
        idx = lb.curselection()
        if not idx or idx[0] >= lb.size() - 1:
            return
        i = idx[0]
        val = lb.get(i)
        lb.delete(i)
        lb.insert(i + 1, val)
        lb.selection_set(i + 1)

    def _apply_consist_order(self):
        lb = self._consist_listbox
        order = list(lb.get(0, "end"))
        self.controller.set_consist_order(order)

    # ── Logging ───────────────────────────────────────────────────────────────

    def _append_log(self, msg: str):
        if self.log_text is None:
            self._pending_logs.append(msg)
            print(msg)
            return
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        print(msg)

    def _flush_pending_logs(self):
        if self.log_text is None:
            return
        for msg in self._pending_logs:
            self.log_text.insert("end", msg + "\n")
        if self._pending_logs:
            self.log_text.see("end")
        self._pending_logs.clear()

    def log(self, msg: str):
        try:
            self.root.after(0, lambda m=msg: self._append_log(m))
        except Exception:
            print(msg)

    def run_background(self, target):
        threading.Thread(target=target, daemon=True).start()

    # ── Button callbacks ──────────────────────────────────────────────────────

    def start_sort(self):
        self.controller.start_sorting_async()

    def stop_sort(self):
        self.controller.stop_sorting()

    def reset_system(self):
        self.controller.reset_system()
        self._rebuild_destination_panel()
        self._rebuild_consist_panel()
        self.log("[GUI] Reset")

    def scan_rfid_log(self):
        self.run_background(self.controller.scan_rfid_once)

    def scan_and_route(self):
        self.run_background(self.controller.scan_and_prepare_route)

    def _poll_single_reader(self, reader_idx: int):
        uid = self.controller.rfid.scan_reader(reader_idx, timeout_sec=3.0)
        name = train_config.RFID_READERS[reader_idx]["name"]
        if uid:
            car = self.controller.rfid.identify_car(uid)
            self.log(f"[RFID] {name}: {uid}{' → ' + car if car else ' (unregistered)'}")
        else:
            self.log(f"[RFID] {name}: no tag detected")

    def dcc_idle(self):
        self.run_background(self.controller.dcc_test_idle)

    def dcc_forward(self):
        self.run_background(self.controller.dcc_test_forward)

    def dcc_reverse(self):
        self.run_background(self.controller.dcc_test_reverse)

    def dcc_stop(self):
        self.run_background(self.controller.dcc_test_stop)

    def run_manual_decouple(self):
        self.run_background(self.controller.manual_decouple)

    def run_victory_lap(self):
        self.run_background(self.controller.manual_send_to_victory_lap)

    def _toggle_mock_mode(self):
        train_config.MOCK_MODE = self._mock_var.get()
        self.log(f"[CONFIG] MOCK_MODE = {train_config.MOCK_MODE}")

    def on_close(self):
        self.log("[GUI] Closing")
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
