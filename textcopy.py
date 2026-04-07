import json
import os
import threading
import ctypes
import tkinter as tk
from tkinter import ttk

import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULT_CONFIG = {"hotkey": "f9", "notify": True}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


config = load_config()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

buffer = []
state = {"recording": False}
tray_icon = None

# ---------------------------------------------------------------------------
# Icon helpers
# ---------------------------------------------------------------------------

def make_icon(fill_color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=fill_color)
    return img


ICON_IDLE = make_icon("#888888")
ICON_RECORDING = make_icon("#22cc55")


def update_icon(mode):
    if tray_icon is None:
        return
    if mode == "recording":
        tray_icon.icon = ICON_RECORDING
        tray_icon.title = "TextCopy — Recording…"
    else:
        tray_icon.icon = ICON_IDLE
        tray_icon.title = f"TextCopy — Idle  (press {config['hotkey'].upper()} to start)"


# ---------------------------------------------------------------------------
# Keyboard capture
# ---------------------------------------------------------------------------

SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?", "`": "~",
}


def caps_lock_on():
    return bool(ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1)


def resolve_char(event):
    """Return the printable character for this keypress, or None."""
    name = event.name
    if not name or len(name) != 1:
        return None
    shift = keyboard.is_pressed("shift")
    caps = caps_lock_on()
    if name in SHIFT_MAP:
        return SHIFT_MAP[name] if shift else name
    if name.isalpha():
        upper = shift ^ caps  # XOR: caps inverts, shift toggles again
        return name.upper() if upper else name
    return name


def toggle_capture():
    if not state["recording"]:
        buffer.clear()
        state["recording"] = True
        update_icon("recording")
    else:
        text = "".join(buffer)
        state["recording"] = False
        update_icon("idle")
        if text:
            pyperclip.copy(text)
            if config["notify"] and tray_icon is not None:
                tray_icon.notify(f"Copied {len(text)} character{'s' if len(text) != 1 else ''}", "TextCopy")


def on_key_event(event):
    if event.event_type != keyboard.KEY_DOWN:
        return

    if event.name == config["hotkey"]:
        toggle_capture()
        return

    if not state["recording"]:
        return

    if event.name == "backspace":
        if buffer:
            buffer.pop()
    elif event.name == "enter":
        buffer.append("\n")
    elif event.name == "tab":
        buffer.append("\t")
    elif event.name == "space":
        buffer.append(" ")
    else:
        ch = resolve_char(event)
        if ch:
            buffer.append(ch)


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------

def open_settings():
    win = tk.Tk()
    win.title("TextCopy Settings")
    win.resizable(False, False)
    win.geometry("270x130")
    win.attributes("-topmost", True)

    pad = {"padx": 14, "pady": 8}

    tk.Label(win, text="Hotkey:").grid(row=0, column=0, sticky="w", **pad)
    hotkey_var = tk.StringVar(value=config["hotkey"].upper())
    hotkey_cb = ttk.Combobox(
        win, textvariable=hotkey_var, width=7,
        values=[f"F{i}" for i in range(1, 13)], state="readonly",
    )
    hotkey_cb.grid(row=0, column=1, sticky="w", **pad)

    notify_var = tk.BooleanVar(value=config["notify"])
    tk.Checkbutton(win, text="Show notification on copy", variable=notify_var).grid(
        row=1, column=0, columnspan=2, sticky="w", padx=14,
    )

    def save_and_close():
        config["hotkey"] = hotkey_var.get().lower()
        config["notify"] = notify_var.get()
        save_config(config)
        # Re-register the hook so the new hotkey takes effect immediately
        keyboard.unhook_all()
        keyboard.hook(on_key_event)
        update_icon("idle")
        win.destroy()

    tk.Button(win, text="Save", width=10, command=save_and_close).grid(
        row=2, column=0, columnspan=2, pady=10,
    )

    win.mainloop()


# ---------------------------------------------------------------------------
# Tray menu callbacks
# ---------------------------------------------------------------------------

def on_settings(icon, item):
    threading.Thread(target=open_settings, daemon=True).start()


def on_quit(icon, item):
    keyboard.unhook_all()
    icon.stop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global tray_icon

    keyboard.hook(on_key_event)

    menu = pystray.Menu(
        pystray.MenuItem("Settings", on_settings),
        pystray.MenuItem("Quit", on_quit),
    )

    tray_icon = pystray.Icon(
        "textcopy",
        ICON_IDLE,
        f"TextCopy — Idle  (press {config['hotkey'].upper()} to start)",
        menu,
    )

    tray_icon.run()


if __name__ == "__main__":
    main()
