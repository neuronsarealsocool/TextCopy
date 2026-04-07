import json
import os
import threading
import time
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

state = {"recording": False}
_capture_lock = threading.Lock()
tray_icon = None

# Invisible marker — Unicode Private Use Area character, never appears in
# normal text, supported by every modern editor.
MARKER = "\uE000"

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
# Capture logic
# ---------------------------------------------------------------------------

def toggle_capture():
    # Non-blocking lock — silently drops rapid double-presses
    if not _capture_lock.acquire(blocking=False):
        return
    try:
        if not state["recording"]:
            # F9 #1 — plant invisible start marker at the current cursor position
            state["recording"] = True
            update_icon("recording")
            keyboard.write(MARKER)

        else:
            # F9 #2 — plant end marker, grab whole doc, extract between markers,
            #          then undo both marker insertions so the doc is untouched.
            state["recording"] = False
            update_icon("idle")

            keyboard.write(MARKER)          # end marker
            time.sleep(0.08)
            keyboard.send("ctrl+a")         # select all text in the editor
            time.sleep(0.08)
            keyboard.send("ctrl+c")         # copy it
            time.sleep(0.15)                # give clipboard time to update

            full = pyperclip.paste()
            parts = full.split(MARKER)

            # Always extract from the LAST pair of markers.
            # Markers may accumulate across captures if Ctrl+Z undo doesn't
            # clean up perfectly (undo granularity varies by editor), but
            # parts[-2] is always the text from the most recent F9 session.
            extracted = parts[-2] if len(parts) >= 3 else ""

            # Best-effort cleanup — undo the two markers we just inserted.
            keyboard.send("ctrl+z")
            time.sleep(0.05)
            keyboard.send("ctrl+z")
            time.sleep(0.05)

            if extracted:
                pyperclip.copy(extracted)
                if config["notify"] and tray_icon is not None:
                    tray_icon.notify(
                        f"Copied {len(extracted)} character{'s' if len(extracted) != 1 else ''}",
                        "TextCopy",
                    )
    finally:
        _capture_lock.release()


def on_key_event(event):
    if event.event_type != keyboard.KEY_DOWN:
        return
    if event.name == config["hotkey"]:
        # Spawn a daemon thread so the hook callback returns instantly.
        # Calling toggle_capture() directly would block the hook thread with
        # keyboard.send / time.sleep calls, causing captures to fail after
        # the first one.
        threading.Thread(target=toggle_capture, daemon=True).start()


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
