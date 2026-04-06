"""
Auto-updater — checks GitHub repo for newer files on game start.

Compares local version.py against remote. If newer version exists,
downloads changed files. Skips saves/, models/, config.json.

Runs silently on startup. If no internet or update fails, game starts normally.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import hashlib
import threading
from typing import Optional

from src.version import VERSION, REPO_RAW, REPO_URL


UPDATE_MANIFEST = "update_manifest.json"
SKIP_DIRS = {"saves", "models", "__pycache__", ".git", "dist", "build"}
SKIP_FILES = {"config.json", "error.log", "keylog.txt", "event_debug.log"}


def _get_remote_version() -> Optional[str]:
    """Fetch remote version string from GitHub."""
    try:
        url = f"{REPO_RAW}/src/version.py"
        req = urllib.request.Request(url, headers={"User-Agent": "AmericanProspector"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8")
        for line in text.splitlines():
            if line.startswith("VERSION"):
                # Parse: VERSION = "0.1.1-alpha"
                return line.split('"')[1]
    except Exception:
        pass
    return None


def _parse_version(v: str) -> tuple:
    """Parse '0.1.0-alpha' into comparable tuple of ints (pre-release = -1)."""
    parts = v.replace("-", ".").split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            # Pre-release tags sort before release: alpha=-3, beta=-2, rc=-1
            tag = p.lower()
            if "alpha" in tag:
                result.append(-3)
            elif "beta" in tag:
                result.append(-2)
            elif "rc" in tag:
                result.append(-1)
            else:
                result.append(0)
    return tuple(result)


def _fetch_file_list() -> Optional[list]:
    """Fetch list of files from GitHub API (top-level + src/)."""
    files = []
    try:
        for path in ["", "src", "data", "data/fonts"]:
            url = f"https://api.github.com/repos/twiztidxxxninja-spec/AmericanProspector/contents/{path}?ref=main"
            req = urllib.request.Request(url, headers={
                "User-Agent": "AmericanProspector",
                "Accept": "application/vnd.github.v3+json",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                items = json.loads(resp.read().decode("utf-8"))
            for item in items:
                if item["type"] == "file":
                    files.append({
                        "path": item["path"],
                        "sha": item["sha"],
                        "download_url": item["download_url"],
                        "size": item["size"],
                    })
    except Exception:
        return None
    return files


def _local_sha(filepath: str) -> str:
    """Compute git-compatible SHA1 of a local file."""
    try:
        with open(filepath, "rb") as f:
            data = f.read()
        # Git blob SHA: "blob <size>\0<content>"
        header = f"blob {len(data)}\0".encode("utf-8")
        return hashlib.sha1(header + data).hexdigest()
    except (FileNotFoundError, PermissionError):
        return ""


def check_for_updates(game_root: str, quiet: bool = True) -> dict:
    """
    Check for updates from GitHub.
    Returns {"available": bool, "remote_version": str, "files_changed": int, "files": [...]}
    """
    result = {"available": False, "remote_version": VERSION,
              "files_changed": 0, "files": []}

    remote_ver = _get_remote_version()
    if remote_ver is None:
        return result  # no internet

    result["remote_version"] = remote_ver

    if _parse_version(remote_ver) <= _parse_version(VERSION):
        return result  # up to date

    # Newer version exists — get file list
    remote_files = _fetch_file_list()
    if remote_files is None:
        return result

    changed = []
    for rf in remote_files:
        # Skip protected files
        parts = rf["path"].split("/")
        if parts[0] in SKIP_DIRS:
            continue
        if rf["path"] in SKIP_FILES:
            continue
        # Skip music (large, don't auto-update)
        if parts[0] == "music":
            continue

        local_path = os.path.join(game_root, rf["path"].replace("/", os.sep))
        local_hash = _local_sha(local_path)

        if local_hash != rf["sha"]:
            changed.append(rf)

    result["available"] = len(changed) > 0
    result["files_changed"] = len(changed)
    result["files"] = changed
    return result


def apply_updates(game_root: str, files: list,
                  progress_callback=None) -> tuple:
    """
    Download and replace changed files.
    Returns (success_count, fail_count).
    """
    success = 0
    fail = 0
    for i, rf in enumerate(files):
        local_path = os.path.join(game_root, rf["path"].replace("/", os.sep))
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            tmp = local_path + ".tmp"
            urllib.request.urlretrieve(rf["download_url"], tmp)
            # Atomic replace
            if os.path.exists(local_path):
                os.replace(tmp, local_path)
            else:
                os.rename(tmp, local_path)
            success += 1
        except Exception:
            fail += 1
            try:
                os.remove(local_path + ".tmp")
            except OSError:
                pass
        if progress_callback:
            progress_callback(i + 1, len(files))
    return success, fail


def run_update_check(game_root: str) -> None:
    """
    Run on game startup. Shows tkinter dialog if update available.
    Non-blocking if no update. Blocks briefly to check version (5s timeout).
    """
    info = check_for_updates(game_root)
    if not info["available"]:
        return

    n = info["files_changed"]
    remote = info["remote_version"]

    # Show update prompt
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        # No tkinter — print to console
        print(f"\nUpdate available: {VERSION} -> {remote} ({n} files changed)")
        print(f"Run 'git pull' to update, or download from {REPO_URL}\n")
        return

    root = tk.Tk()
    root.withdraw()

    answer = messagebox.askyesno(
        "Update Available",
        f"American Prospector {remote} is available!\n"
        f"(You have {VERSION})\n\n"
        f"{n} file(s) changed.\n\n"
        f"Download update now?",
    )

    if answer:
        # Show progress
        root.deiconify()
        root.title("Updating...")
        root.geometry("400x100")
        root.configure(bg="#1a1a1a")

        import tkinter.ttk as ttk
        lbl = tk.Label(root, text="Downloading...", fg="#d4b483", bg="#1a1a1a",
                       font=("Courier", 10))
        lbl.pack(pady=10)
        bar = ttk.Progressbar(root, length=360, maximum=n)
        bar.pack(pady=5)

        def do_update():
            def progress(done, total):
                bar["value"] = done
                lbl.config(text=f"Downloading {done}/{total}...")
                root.update_idletasks()

            ok, fail = apply_updates(game_root, info["files"], progress)
            lbl.config(text=f"Updated {ok} files. {'(' + str(fail) + ' failed)' if fail else ''}")
            if fail == 0:
                lbl.config(text=f"Updated to {remote}! Restart the game.")
            root.after(2500, root.destroy)

        root.after(100, do_update)
        root.mainloop()

        if answer:
            print(f"Updated to {remote}. Please restart the game.")
            sys.exit(0)
    else:
        root.destroy()
