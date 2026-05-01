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

        self.track_vars = {}
        self.consist_vars = []

        self._build_widgets()

    def _build_widgets(self):
        top = ttk.LabelFrame(self.root, text="Main Controls", padding=10)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Button(top, text="Start Sort", command=self.start_sort).pack(side="left", padx=6)
        ttk.Button(top, text="Stop", command=self.stop_sort).pack(side="left", padx=6)
        ttk.Button(top, text="Reset", command=self.reset_system).pack(side="left", padx=6)
        ttk.Button(top, text="Show State", command=self.controller.show_state).pack(side="left", padx=6)

        dest_frame = ttk.LabelFrame(self.root, text="Car Destination Assignment", padding=10)
        dest_frame.pack(fill="x", padx=10, pady=10)

        for row_index, car_name in enumerate(["CAR_A", "CAR_B", "CAR_C", "CAR_D"]):
            ttk.Label(dest_frame, text=car_name, width=12).grid(
                row=row_index,
                column=0,
                padx=5,
                pady=5,
                sticky="w",
            )

            var = tk.IntVar(value=self.controller.car_destinations[car_name])
            self.track_vars[car_name] = var

            combo = ttk.Combobox(
                dest_frame,
                textvariable=var,
                values=[1, 2, 3, 4],
                state="readonly",
                width=10,
            )
            combo.grid(row=row_index, column=1, padx=5, pady=5)

            ttk.Button(
                dest_frame,
                text="Apply",
                command=lambda c=car_name, v=var: self.apply_destination(c, v),
            ).grid(row=row_index, column=2, padx=5, pady=5)

        consist_frame = ttk.LabelFrame(self.root, text="Starting Consist Order", padding=10)
        consist_frame.pack(fill="x", padx=10, pady=10)

        default_order = self.controller.consist

        for i in range(4):
            ttk.Label(consist_frame, text=f"Position {i + 1}").grid(
                row=0,
                column=i * 2,
                padx=5,
                pady=5,
            )

            var = tk.StringVar(value=default_order[i])
            self.consist_vars.append(var)

            combo = ttk.Combobox(
                consist_frame,
                textvariable=var,
                values=["CAR_A", "CAR_B", "CAR_C", "CAR_D"],
                state="readonly",
                width=10,
            )
            combo.grid(row=0, column=i * 2 + 1, padx=5, pady=5)

        ttk.Button(
            consist_frame,
            text="Apply Consist Order",
            command=self.apply_consist_order,
        ).grid(row=1, column=0, columnspan=8, pady=8)

        manual_frame = ttk.LabelFrame(self.root, text="Manual Test Controls", padding=10)
        manual_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(manual_frame, text="Route Track 1", command=lambda: self.controller.manual_route_track(1)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 2", command=lambda: self.controller.manual_route_track(2)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 3", command=lambda: self.controller.manual_route_track(3)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Route Track 4", command=lambda: self.controller.manual_route_track(4)).pack(side="left", padx=5)
        ttk.Button(manual_frame, text="Decouple", command=self.controller.manual_decouple).pack(side="left", padx=5)

        mock_frame = ttk.LabelFrame(self.root, text="Mock RFID Test", padding=10)
        mock_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(mock_frame, text="Mock CAR_A", command=lambda: self.mock_car("CAR_A")).pack(side="left", padx=5)
        ttk.Button(mock_frame, text="Mock CAR_B", command=lambda: self.mock_car("CAR_B")).pack(side="left", padx=5)
        ttk.Button(mock_frame, text="Mock CAR_C", command=lambda: self.mock_car("CAR_C")).pack(side="left", padx=5)
        ttk.Button(mock_frame, text="Mock CAR_D", command=lambda: self.mock_car("CAR_D")).pack(side="left", padx=5)
        ttk.Button(mock_frame, text="Queue All Cars", command=self.queue_all_mock_cars).pack(side="left", padx=5)

        log_frame = ttk.LabelFrame(self.root, text="System Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, wrap="word", height=24)
        self.log_text.pack(fill="both", expand=True)

    def log(self, msg):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        print(msg)

    def apply_destination(self, car_name, var):
        self.controller.set_destination(car_name, int(var.get()))

    def apply_consist_order(self):
        order = [var.get() for var in self.consist_vars]

        if len(set(order)) != 4:
            self.log("[GUI] Invalid consist order: duplicate cars selected")
            return

        self.controller.set_consist_order(order)

    def mock_car(self, car_name):
        self.controller.rfid.enqueue_mock_car("RFID0_ENTRY", car_name)
        self.log(f"[GUI] Queued mock RFID for {car_name}")

    def queue_all_mock_cars(self):
        for car_name in ["CAR_A", "CAR_B", "CAR_C", "CAR_D"]:
            self.controller.rfid.enqueue_mock_car("RFID0_ENTRY", car_name)

        self.log("[GUI] Queued mock RFID for all cars")

    def start_sort(self):
        self.controller.start_sorting()
        self.run_state_machine_loop()

    def run_state_machine_loop(self):
        if self.controller.running:
            self.controller.step_state_machine()
            self.root.after(250, self.run_state_machine_loop)

    def stop_sort(self):
        self.controller.stop_sorting()

    def reset_system(self):
        self.controller.reset_system()
        self.log("[GUI] Reset pressed")


def main():
    root = tk.Tk()
    TrainSorterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()