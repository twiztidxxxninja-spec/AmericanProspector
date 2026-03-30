"""
Build script — creates a distributable folder using PyInstaller.

Usage:
    python build.py

Output:
    dist/AmericanProspector/  — standalone game folder
    dist/AmericanProspector/AmericanProspector.exe  — launch the game

The LLM model is NOT bundled (4.7 GB). It downloads on first run.
CUDA DLLs from llama-cpp-python are bundled automatically by PyInstaller.
"""

import subprocess
import sys
import os
import shutil

GAME_NAME = "AmericanProspector"
MAIN_SCRIPT = "main.py"
ICON = None  # set to "icon.ico" if you have one


def check_deps():
    """Ensure build dependencies are installed."""
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def find_cuda_dlls():
    """Find CUDA runtime DLLs to bundle (cublas, cudart, etc.)."""
    import ctypes.util
    cuda_dlls = []

    # Check common locations
    search_dirs = []
    cuda_path = os.environ.get("CUDA_PATH", "")
    if cuda_path:
        search_dirs.append(os.path.join(cuda_path, "bin"))

    # Also check llama_cpp package directory for bundled DLLs
    try:
        import llama_cpp
        pkg_dir = os.path.dirname(llama_cpp.__file__)
        search_dirs.append(pkg_dir)
        # Check for lib/ subdirectory
        lib_dir = os.path.join(pkg_dir, "lib")
        if os.path.isdir(lib_dir):
            search_dirs.append(lib_dir)
    except ImportError:
        pass

    dll_patterns = ["cublas", "cudart", "cublasLt", "cuda_"]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".dll") and any(p in f.lower() for p in dll_patterns):
                full = os.path.join(d, f)
                if full not in cuda_dlls:
                    cuda_dlls.append(full)

    return cuda_dlls


def build():
    check_deps()

    # Collect data files
    datas = [
        ("src", "src"),       # all game source (needed for imports)
    ]
    # Add data/ directory if it exists
    if os.path.isdir("data"):
        datas.append(("data", "data"))
    # Add music/ directory if it exists
    if os.path.isdir("music"):
        datas.append(("music", "music"))

    # Collect CUDA DLLs
    binaries = []
    cuda_dlls = find_cuda_dlls()
    if cuda_dlls:
        print(f"Found {len(cuda_dlls)} CUDA DLLs to bundle:")
        for dll in cuda_dlls:
            print(f"  {dll}")
            binaries.append((dll, "."))
    else:
        print("WARNING: No CUDA DLLs found. GPU inference may not work.")
        print("  Install CUDA Toolkit or llama-cpp-python with CUDA support.")

    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", GAME_NAME,
        "--noconfirm",
        "--clean",
        # Use directory mode (not one-file) — faster startup, easier to debug
        "--onedir",
        # Console mode (game uses terminal-style rendering)
        "--console",
    ]

    if ICON and os.path.isfile(ICON):
        cmd.extend(["--icon", ICON])

    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])
    for dll, dst in binaries:
        cmd.extend(["--add-binary", f"{dll}{os.pathsep}{dst}"])

    # Hidden imports that PyInstaller might miss
    cmd.extend([
        "--hidden-import", "tcod",
        "--hidden-import", "tcod.event",
        "--hidden-import", "tcod.libtcodpy",
        "--hidden-import", "numpy",
        "--hidden-import", "src.engine",
        "--hidden-import", "src.model_downloader",
        "--hidden-import", "src.local_map",
        "--hidden-import", "src.world_map",
        "--hidden-import", "src.renderer",
        "--hidden-import", "src.player",
        "--hidden-import", "src.constants",
    ])

    # Try to include llama_cpp if available
    try:
        import llama_cpp
        cmd.extend(["--hidden-import", "llama_cpp"])
    except ImportError:
        print("NOTE: llama-cpp-python not installed. Build will work but no LLM.")

    cmd.append(MAIN_SCRIPT)

    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    subprocess.check_call(cmd)

    # Copy config.json to dist if it exists
    dist_dir = os.path.join("dist", GAME_NAME)
    if os.path.isfile("config.json"):
        shutil.copy2("config.json", dist_dir)
        print("Copied config.json")

    # Create empty saves/ directory
    os.makedirs(os.path.join(dist_dir, "saves"), exist_ok=True)

    print(f"\nBuild complete!")
    print(f"  Output: {os.path.abspath(dist_dir)}")
    print(f"  Run:    {os.path.join(dist_dir, GAME_NAME + '.exe')}")
    print(f"\nThe AI model (~4.7 GB) will download on first launch.")


if __name__ == "__main__":
    build()
