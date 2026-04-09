import tkinter as tk
from tkinter import ttk
import threading
from TrainController import TrainController
import train_config


class TrainSorterGUI:

    def __init__(self, root):
        self.root = root
        self.root.title(train_config.WINDOW_TITLE)

        self.controller = TrainController(logger=self.log)

        self.build()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build(self):
        frame = ttk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        ttk.Button(frame, text="Start Sort", command=self.start_sort).pack(pady=5)
        ttk.Button(frame, text="Stop", command=self.controller.stop_sorting).pack(pady=5)

        ttk.Button(frame, text="DCC Forward", command=self.dcc_forward).pack(pady=5)
        ttk.Button(frame, text="DCC Stop", command=self.dcc_stop).pack(pady=5)

        self.log_box = tk.Text(self.root, height=15)
        self.log_box.pack(fill="both", expand=True)

    def run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def start_sort(self):
        self.controller.start_sorting_async()

    def dcc_forward(self):
        self.run_bg(self.controller.dcc_test_forward)

    def dcc_stop(self):
        self.run_bg(self.controller.dcc_test_stop)

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        print(msg)

    def on_close(self):
        self.controller.shutdown()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = TrainSorterGUI(root)
    root.mainloop()