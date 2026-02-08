import ctypes
import tkinter as tk

from gui import App


def main():
    # Make the process DPI-aware so mss coordinates match pyautogui/tkinter
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
