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
        self._scanned_uid    = tk.StringVar(value="")
        self._scanned_reader = tk.StringVar(value="")
        self._reg_car_name   = tk.StringVar()
        self._reg_track_var  = tk.IntVar(value=1)

        self._build_widgets()
        self._flush_pending_logs()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── Widget construction ───────────────────────────────────────────────────

    def _build_widgets(self):
        # ── Top controls ──────────────────────────────────────────────────────
        top = ttk.LabelFrame(self.root, text="Controls", padding=8)
        top.pack(fill="x", padx=10, pady=6)

        self._auto_btn = ttk.Button(top, text="Start Auto-Scan", command=self._toggle_auto_scan)
        self._auto_btn.pack(side="left", padx=5)

        ttk.Button(top, text="Show State", command=self.controller.show_state).pack(side="left", padx=5)

        self._mock_var = tk.BooleanVar(value=train_config.MOCK_MODE)
        ttk.Checkbutton(
            top, text="Mock Mode",
            variable=self._mock_var, command=self._toggle_mock
        ).pack(side="left", padx=12)

        # ── RFID Registration ─────────────────────────────────────────────────
        reg = ttk.LabelFrame(self.root, text="RFID Registration", padding=8)
        reg.pack(fill="x", padx=10, pady=6)

        scan_row = ttk.Frame(reg)
        scan_row.pack(fill="x", pady=2)
        ttk.Button(scan_row, text="Scan All Readers", command=self._start_scan).pack(side="left", padx=4)
        ttk.Label(scan_row, text="Reader:").pack(side="left", padx=(12, 2))
        ttk.Label(scan_row, textvariable=self._scanned_reader, width=8, relief="sunken").pack(side="left")
        ttk.Label(scan_row, text="UID:").pack(side="left", padx=(10, 2))
        ttk.Label(scan_row, textvariable=self._scanned_uid, width=12,
                  relief="sunken", font=("Courier", 10)).pack(side="left")

        reg_row = ttk.Frame(reg)
        reg_row.pack(fill="x", pady=4)
        ttk.Label(reg_row, text="Car name:").pack(side="left", padx=4)
        ttk.Entry(reg_row, textvariable=self._reg_car_name, width=14).pack(side="left", padx=4)
        ttk.Label(reg_row, text="→ Track:").pack(side="left", padx=(8, 2))
        ttk.Combobox(
            reg_row, textvariable=self._reg_track_var,
            values=[1, 2, 3], state="readonly", width=5
        ).pack(side="left", padx=4)
        ttk.Button(reg_row, text="Register Tag", command=self._register_car).pack(side="left", padx=8)
        ttk.Button(reg_row, text="Clear",        command=self._clear_reg).pack(side="left")

        # Roster table
        tree_frame = ttk.Frame(reg)
        tree_frame.pack(fill="x", pady=4)

        cols = ("car", "uid", "track")
        self._roster_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=5)
        self._roster_tree.heading("car",   text="Car Name")
        self._roster_tree.heading("uid",   text="RFID UID")
        self._roster_tree.heading("track", text="Track")
        self._roster_tree.column("car",   width=130)
        self._roster_tree.column("uid",   width=130)
        self._roster_tree.column("track", width=70)
        self._roster_tree.pack(side="left", fill="x", expand=True)
        ttk.Scrollbar(tree_frame, orient="vertical",
                      command=self._roster_tree.yview).pack(side="right", fill="y")

        ttk.Button(reg, text="Delete Selected Car", command=self._delete_car).pack(anchor="w", pady=2)
        self._refresh_tree()

        # ── Car Destination Assignment ─────────────────────────────────────────
        self._dest_outer = ttk.LabelFrame(self.root, text="Car Destination Assignment", padding=8)
        self._dest_outer.pack(fill="x", padx=10, pady=6)
        self._dest_inner = None
        self._track_vars: dict = {}
        self._rebuild_dest_panel()

        # ── Manual Switch Controls ─────────────────────────────────────────────
        sw = ttk.LabelFrame(self.root, text="Manual Switch Control", padding=8)
        sw.pack(fill="x", padx=10, pady=6)

        ttk.Button(sw, text="Route Track 1", command=lambda: self.controller.manual_route_track(1)).pack(side="left", padx=5)
        ttk.Button(sw, text="Route Track 2", command=lambda: self.controller.manual_route_track(2)).pack(side="left", padx=5)
        ttk.Button(sw, text="Route Track 3", command=lambda: self.controller.manual_route_track(3)).pack(side="left", padx=5)
        ttk.Button(sw, text="Main Line",     command=self.controller.manual_route_main).pack(side="left", padx=5)

        # ── RFID Test Controls ─────────────────────────────────────────────────
        rfid = ttk.LabelFrame(self.root, text="RFID Test", padding=8)
        rfid.pack(fill="x", padx=10, pady=6)

        ttk.Button(rfid, text="Scan Once (log)",  command=lambda: self.run_bg(self.controller.scan_once)).pack(side="left", padx=4)
        ttk.Button(rfid, text="Scan + Route",     command=lambda: self.run_bg(self.controller.scan_and_route)).pack(side="left", padx=4)

        for i, r in enumerate(train_config.RFID_READERS):
            ttk.Button(
                rfid, text=f"Poll {r['name']}",
                command=lambda idx=i: self.run_bg(lambda i=idx: self._poll_reader(i))
            ).pack(side="left", padx=3)

        # ── System Log ────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self.root, text="System Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.log_text = tk.Text(log_frame, wrap="word", height=16)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ── Dynamic panels ────────────────────────────────────────────────────────

    def _rebuild_dest_panel(self):
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
            ttk.Combobox(
                self._dest_inner, textvariable=var,
                values=[1, 2, 3], state="readonly", width=8
            ).grid(row=row_i, column=1, padx=5, pady=3)
            ttk.Button(
                self._dest_inner, text="Apply",
                command=lambda c=car_name, v=var: self.controller.set_destination(c, int(v.get()))
            ).grid(row=row_i, column=2, padx=5, pady=3)

    # ── Roster ────────────────────────────────────────────────────────────────

    def _refresh_tree(self):
        self._roster_tree.delete(*self._roster_tree.get_children())
        for name, info in train_config.CAR_ROSTER.items():
            self._roster_tree.insert("", "end", values=(name, info["rfid"], info["default_track"]))

    # ── Registration ─────────────────────────────────────────────────────────

    def _start_scan(self):
        self._scanned_uid.set("scanning…")
        self._scanned_reader.set("")
        self.run_bg(self._do_scan)

    def _do_scan(self):
        reader_idx, uid = self.controller.rfid.scan_all(timeout_sec=5.0)
        if uid is None:
            self.root.after(0, lambda: self._scanned_uid.set("(none)"))
            self.root.after(0, lambda: self._scanned_reader.set(""))
            self.log("[REG] No tag found within 5 s")
        else:
            rname = train_config.RFID_READERS[reader_idx]["name"]
            self.root.after(0, lambda u=uid:    self._scanned_uid.set(u))
            self.root.after(0, lambda n=rname:  self._scanned_reader.set(n))
            known = self.controller.rfid.identify_car(uid)
            if known:
                self.root.after(0, lambda k=known: self._reg_car_name.set(k))
            self.log(f"[REG] Scanned {uid} on {rname}")

    def _register_car(self):
        uid   = self._scanned_uid.get().strip()
        name  = self._reg_car_name.get().strip()
        track = self._reg_track_var.get()

        if not uid or uid in ("scanning…", "(none)"):
            messagebox.showwarning("Registration", "Scan a tag first.")
            return
        if not name:
            messagebox.showwarning("Registration", "Enter a car name.")
            return

        if self.controller.register_car(name, uid, track):
            self._refresh_tree()
            self._rebuild_dest_panel()
            self._clear_reg()

    def _clear_reg(self):
        self._scanned_uid.set("")
        self._scanned_reader.set("")
        self._reg_car_name.set("")
        self._reg_track_var.set(1)

    def _delete_car(self):
        sel = self._roster_tree.selection()
        if not sel:
            return
        car_name = self._roster_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Delete", f"Remove '{car_name}' from the roster?"):
            self.controller.unregister_car(car_name)
            self._refresh_tree()
            self._rebuild_dest_panel()

    # ── Auto-scan toggle ──────────────────────────────────────────────────────

    def _toggle_auto_scan(self):
        if self.controller._auto_scan:
            self.controller.stop_auto_scan()
            self._auto_btn.configure(text="Start Auto-Scan")
        else:
            self.controller.start_auto_scan()
            self._auto_btn.configure(text="Stop Auto-Scan")

    # ── RFID test helpers ─────────────────────────────────────────────────────

    def _poll_reader(self, reader_idx: int):
        uid = self.controller.rfid.scan_reader(reader_idx, timeout_sec=3.0)
        name = train_config.RFID_READERS[reader_idx]["name"]
        if uid:
            car = self.controller.rfid.identify_car(uid)
            self.log(f"[RFID] {name}: {uid}{' → ' + car if car else ' (unregistered)'}")
        else:
            self.log(f"[RFID] {name}: no tag detected")

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
        if not self.log_text:
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

    def run_bg(self, target):
        threading.Thread(target=target, daemon=True).start()

    def _toggle_mock(self):
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
