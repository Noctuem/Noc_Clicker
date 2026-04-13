import ctypes
import tkinter as tk

from gui import App


def main():
    # Per-monitor DPI awareness keeps mss and tkinter in the same coordinate space
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
