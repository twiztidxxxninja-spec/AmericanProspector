"""
src/model_downloader.py

First-run model downloader. Shows a simple tkinter window with a progress
bar while downloading the LLM from Hugging Face. Called once, on startup,
if the model file is missing. On success the game continues normally.
On failure (no internet, cancelled) the game starts with LLM disabled.
"""

import os
import sys
import threading
import urllib.request


# ── Model config ──────────────────────────────────────────────────────────────

# Split GGUF — llama-cpp loads part 1 and finds part 2 automatically
MODEL_PARTS = [
    {
        "filename": "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF"
            "/resolve/bb5d59e06d9551d752d08b292a50eb208b07ab1f"
            "/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
        ),
    },
    {
        "filename": "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF"
            "/resolve/bb5d59e06d9551d752d08b292a50eb208b07ab1f"
            "/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf"
        ),
    },
]

# Point llama-cpp at the first part — it discovers part 2 automatically
MODEL_FILENAME = MODEL_PARTS[0]["filename"]


def get_models_dir() -> str:
    """
    Return a user-level models folder that persists across game updates.

    Windows:  C:\\Users\\<name>\\AppData\\Roaming\\AmericanProspector\\models
    Fallback: ~/AmericanProspector/models
    """
    base = (os.environ.get("APPDATA")        # Windows
            or os.environ.get("XDG_DATA_HOME")  # Linux
            or os.path.expanduser("~"))
    return os.path.join(base, "AmericanProspector", "models")


def model_path() -> str:
    return os.path.join(get_models_dir(), MODEL_FILENAME)


def model_exists() -> bool:
    # Check if ALL parts are present
    models_dir = get_models_dir()
    all_present = all(
        os.path.isfile(os.path.join(models_dir, p["filename"]))
        for p in MODEL_PARTS
    )
    if all_present:
        return True
    # Also accept a model already configured in config.json
    try:
        import json
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_file = os.path.join(base, "config.json")
        with open(cfg_file) as _f:
            cfg = json.load(_f)
        cfg_path = cfg.get("model_path", "")
        if cfg_path:
            for candidate in (cfg_path, os.path.join(base, cfg_path)):
                if os.path.isfile(candidate):
                    return True
    except Exception:
        pass
    return False


# ── Downloader UI ─────────────────────────────────────────────────────────────

def run_download_ui() -> bool:
    """
    Show a tkinter download window. Blocks until download finishes or fails.
    Returns True if model was successfully downloaded.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        # tkinter not available — fall back to terminal download
        return _download_terminal()

    root = tk.Tk()
    root.title("American Prospector — First Run Setup")
    root.geometry("520x180")
    root.resizable(False, False)
    root.configure(bg="#1a1a1a")

    # Center on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth()  - 520) // 2
    y = (root.winfo_screenheight() - 180) // 2
    root.geometry(f"+{x}+{y}")

    FG   = "#d4b483"
    BG   = "#1a1a1a"
    GREY = "#888888"

    tk.Label(root, text="American Prospector", font=("Courier", 14, "bold"),
             fg=FG, bg=BG).pack(pady=(18, 2))
    tk.Label(root, text="Downloading AI model (≈4.7 GB) — this happens once only.",
             font=("Courier", 9), fg=GREY, bg=BG).pack()

    progress_var = tk.DoubleVar(value=0)
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Gold.Horizontal.TProgressbar",
                    troughcolor="#2a2a2a", background="#b8860b",
                    bordercolor="#1a1a1a", lightcolor="#d4a017",
                    darkcolor="#8b6914")

    bar = ttk.Progressbar(root, variable=progress_var, maximum=100,
                          length=460, style="Gold.Horizontal.TProgressbar")
    bar.pack(pady=10)

    status_var = tk.StringVar(value="Connecting…")
    tk.Label(root, textvariable=status_var, font=("Courier", 9),
             fg=GREY, bg=BG).pack()

    cancel_flag = [False]
    success_flag = [False]

    def on_close():
        cancel_flag[0] = True
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def download():
        os.makedirs(get_models_dir(), exist_ok=True)

        try:
            for part_idx, part in enumerate(MODEL_PARTS):
                dest = os.path.join(get_models_dir(), part["filename"])
                if os.path.isfile(dest):
                    continue  # already have this part
                tmp = dest + ".tmp"
                part_label = f"Part {part_idx + 1}/{len(MODEL_PARTS)}"

                def reporthook(count, block_size, total_size, _label=part_label):
                    if cancel_flag[0]:
                        raise InterruptedError("Cancelled by user")
                    if total_size > 0:
                        done = count * block_size
                        pct = min(done / total_size * 100, 100)
                        mb_d = done / 1_048_576
                        mb_t = total_size / 1_048_576
                        progress_var.set(pct)
                        status_var.set(
                            f"{_label}: {mb_d:,.0f} MB / {mb_t:,.0f} MB  ({pct:.1f}%)")

                urllib.request.urlretrieve(part["url"], tmp, reporthook)

                if cancel_flag[0]:
                    _cleanup(tmp)
                    return
                os.replace(tmp, dest)

            success_flag[0] = True
            status_var.set("Done! Starting game…")
            root.after(1200, root.destroy)

        except InterruptedError:
            _cleanup(os.path.join(get_models_dir(), MODEL_PARTS[0]["filename"]) + ".tmp")
            _cleanup(os.path.join(get_models_dir(), MODEL_PARTS[1]["filename"]) + ".tmp")
        except Exception as e:
            for p in MODEL_PARTS:
                _cleanup(os.path.join(get_models_dir(), p["filename"]) + ".tmp")
            err_msg = str(e)
            status_var.set(f"Download failed: {err_msg}")
            root.after(100, lambda: messagebox.showerror(
                "Download Failed",
                f"Could not download the AI model:\n{err_msg}\n\n"
                "The game will start without AI features.\n"
                "You can retry by deleting the models/ folder and restarting.",
                parent=root))
            root.after(3000, root.destroy)

    t = threading.Thread(target=download, daemon=True)
    t.start()
    root.mainloop()
    t.join(timeout=2)

    return success_flag[0]


def _cleanup(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _download_terminal() -> bool:
    """Fallback: download with terminal progress (no tkinter)."""
    import sys

    os.makedirs(get_models_dir(), exist_ok=True)

    print("American Prospector — First Run Setup")
    print(f"Downloading AI model (~4.7 GB, 2 parts) to {get_models_dir()}")
    print("This only happens once.\n")

    try:
        for part_idx, part in enumerate(MODEL_PARTS):
            dest = os.path.join(get_models_dir(), part["filename"])
            if os.path.isfile(dest):
                print(f"  Part {part_idx+1} already present, skipping.")
                continue
            tmp = dest + ".tmp"
            print(f"  Downloading part {part_idx+1}/{len(MODEL_PARTS)}...")

            def reporthook(count, block_size, total_size):
                done = count * block_size
                if total_size > 0:
                    pct = min(done / total_size * 100, 100)
                    mb_d = done / 1_048_576
                    mb_t = total_size / 1_048_576
                    bar = "#" * int(pct / 2) + "." * (50 - int(pct / 2))
                    sys.stdout.write(
                        f"\r  [{bar}] {pct:5.1f}%  {mb_d:,.0f}/{mb_t:,.0f} MB")
                    sys.stdout.flush()

            urllib.request.urlretrieve(part["url"], tmp, reporthook)
            os.replace(tmp, dest)
            print()

        print("\nDownload complete. Starting game…\n")
        return True

    except Exception as e:
        for p in MODEL_PARTS:
            _cleanup(os.path.join(get_models_dir(), p["filename"]) + ".tmp")
        print(f"\n\nDownload failed: {e}")
        print("Starting without AI features.\n")
        return False


# ── Public entry point ────────────────────────────────────────────────────────

def ensure_model() -> bool:
    """
    Call this at startup before initialising tcod.
    Returns True if the model is present (downloaded or already existed).
    Returns False if it is missing and download was skipped/failed — game
    should start with LLM disabled.
    """
    if model_exists():
        return True
    return run_download_ui()
