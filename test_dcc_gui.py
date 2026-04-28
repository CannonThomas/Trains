import subprocess
import tkinter as tk
import os
import signal

dcc = subprocess.Popen(
    ["./dcc_pio"],
    stdin=subprocess.PIPE,
    text=True,
    bufsize=1
)

def send(cmd):
    print("Sending:", cmd)
    dcc.stdin.write(cmd + "\n")
    dcc.stdin.flush()

def close():
    try:
        send("S")
        dcc.terminate()
    except Exception:
        pass
    root.destroy()

root = tk.Tk()
root.title("DCC Test GUI")

tk.Button(root, text="Forward 20", width=20, command=lambda: send("F 20")).pack(pady=5)
tk.Button(root, text="Forward 60", width=20, command=lambda: send("F 60")).pack(pady=5)
tk.Button(root, text="Reverse 20", width=20, command=lambda: send("R 20")).pack(pady=5)
tk.Button(root, text="Reverse 60", width=20, command=lambda: send("R 60")).pack(pady=5)
tk.Button(root, text="STOP", width=20, command=lambda: send("S")).pack(pady=10)

root.protocol("WM_DELETE_WINDOW", close)
root.mainloop()