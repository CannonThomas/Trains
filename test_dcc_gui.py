import subprocess
import tkinter as tk

dcc = subprocess.Popen(
    ["sudo", "./dcc_pio"],
    stdin=subprocess.PIPE,
    text=True,
    bufsize=1
)

def send(cmd):
    print("Sending:", cmd)
    dcc.stdin.write(cmd + "\n")
    dcc.stdin.flush()

root = tk.Tk()
root.title("DCC Test GUI")

tk.Button(root, text="Forward 20", width=20, command=lambda: send("F 20")).pack(pady=5)
tk.Button(root, text="Forward 40", width=20, command=lambda: send("F 40")).pack(pady=5)
tk.Button(root, text="Reverse 20", width=20, command=lambda: send("R 20")).pack(pady=5)
tk.Button(root, text="Reverse 40", width=20, command=lambda: send("R 40")).pack(pady=5)
tk.Button(root, text="STOP", width=20, command=lambda: send("S")).pack(pady=10)

root.mainloop()