import tkinter as tk
from TrainController import Controller

class TrainSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Automated Train Car Sorter")
        self.root.geometry("500x420")

        self.controller = Controller(self.update_status)

        title = tk.Label(root, text="Train Sorter Control Panel", font=("Arial", 16))
        title.pack(pady=10)

        tk.Button(root, text="Start Sorting", width=20,
                  command=self.controller.start_sort).pack(pady=5)

        tk.Button(root, text="STOP / E-STOP", width=20,
                  command=self.controller.emergency_stop).pack(pady=5)

        tk.Button(root, text="Forward", width=20,
                  command=lambda: self.controller.manual_drive(1)).pack(pady=3)

        tk.Button(root, text="Reverse", width=20,
                  command=lambda: self.controller.manual_drive(-1)).pack(pady=3)

        self.status_label = tk.Label(root, text="Status: IDLE", font=("Arial", 12))
        self.status_label.pack(pady=15)

        self.log_box = tk.Text(root, height=8, width=55)
        self.log_box.pack()
        self.log("System initialized.")

    def update_status(self, message):
        self.status_label.config(text=f"Status: {message}")
        self.log(message)

    def log(self, message):
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = TrainSorterGUI(root)
    root.mainloop()