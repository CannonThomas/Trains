# TrainGUI.py

import tkinter as tk
from tkinter import ttk
from train_config import WINDOW_TITLE, WINDOW_SIZE
from TrainController import TrainController


class TrainSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)

        self.controller = TrainController(logger=self.log)
        self._build_widgets()

    def _build_widgets(self):
        # ------------------------------------------
        # Main sorter controls
        # ------------------------------------------
        top = ttk.LabelFrame(self.root, text="Main Controls", padding=10)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Button(top, text="Start Sort", command=self.start_sort).pack(side="left", padx=6)
        ttk.Button(top, text="Stop", command=self.stop_sort).pack(side="left", padx=6)
        ttk.Button(top, text="Reset", command=self.reset_system).pack(side="left", padx=6)
        ttk.Button(top, text="Show State", command=self.controller.show_state).pack(side="left", padx=6)

        # ------------------------------------------
        # Car destination assignment
        # ------------------------------------------
        dest_frame = ttk.LabelFrame(self.root, text="Car Destination Assignment", padding=10)
        dest_frame.pack(fill="x", padx=10, pady=10)

        self.track_vars = {}

        for row_index, car_name in enumerate(["CAR_A", "CAR_B", "CAR_C", "CAR_D"]):
            ttk.Label(dest_frame, text=car_name, width=12).grid(
                row=row_index, column=0, padx=5, pady=5, sticky="w"
            )

            var = tk.IntVar(value=self.controller.car_destinations[car_name])
            self.track_vars[car_name] = var

            combo = ttk.Combobox(
                dest_frame,
                textvariable=var,
                values=[1, 2, 3, 4],
                state="readonly",
                width=10
            )
            combo.grid(row=row_index, column=1, padx=5, pady=5)

            ttk.Button(
                dest_frame,
                text="Apply",
                command=lambda c=car_name, v=var: self.apply_destination(c, v)
            ).grid(row=row_index, column=2, padx=5, pady=5)

        # ------------------------------------------
        # Starting consist order
        # ------------------------------------------
        consist_frame = ttk.LabelFrame(self.root, text="Starting Consist Order", padding=10)
        consist_frame.pack(fill="x", padx=10, pady=10)

        self.consist_vars = []
        default_order = self.controller.consist

        for i in range(4):
            ttk.Label(consist_frame, text=f"Position {i + 1}").grid(
                row=0, column=i * 2, padx=5, pady=5
            )

            var = tk.StringVar(value=default_order[i])
            self.consist_vars.append(var)

            combo = ttk.Combobox(
                consist_frame,
                textvariable=var,
                values=["CAR_A", "CAR_B", "CAR_C", "CAR_D"],
                state="readonly",
                width=10
            )
            combo.grid(row=0, column=i * 2 + 1, padx=5, pady=5)

        ttk.Button(
            consist_frame,
            text="Apply Consist Order",
            command=self.apply_consist_order
        ).grid(row=1, column=0, columnspan=8, pady=8)

        # ------------------------------------------
        # Manual test / debug controls
        # ------------------------------------------
        manual_frame = ttk.LabelFrame(self.root, text="Manual Test Controls", padding=10)
        manual_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(manual_frame, text="Route Track 1", command=lambda: self.controller.manual_route_track(1)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 2", command=lambda: self.controller.manual_route_track(2)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 3", command=lambda: self.controller.manual_route_track(3)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 4", command=lambda: self.controller.manual_route_track(4)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Decouple", command=self.controller.manual_decouple).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Send to Victory Lap", command=self.controller.manual_send_to_victory_lap).pack(side="left", padx=5)

        # ------------------------------------------
        # Log output
        # ------------------------------------------
        log_frame = ttk.LabelFrame(self.root, text="System Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, wrap="word", height=24)
        self.log_text.pack(fill="both", expand=True)

    def log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        print(msg)

    def apply_destination(self, car_name, var):
        track = int(var.get())
        self.controller.set_destination(car_name, track)

    def apply_consist_order(self):
        order = [var.get() for var in self.consist_vars]
        if len(set(order)) != 4:
            self.log("[GUI] Invalid consist order: duplicate cars selected")
            return

        self.controller.set_consist_order(order)

    def start_sort(self):
        self.root.after(50, self.controller.start_sorting)

    def stop_sort(self):
        self.controller.stop_sorting()

    def reset_system(self):
        self.controller.reset_system()
        self.log("[GUI] Reset pressed")


def main():
    root = tk.Tk()
    app = TrainSorterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
