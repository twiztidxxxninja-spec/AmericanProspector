"""
American Prospector — entry point.
"""

import sys
import os

# Ensure src is on path when run from project root
sys.path.insert(0, os.path.dirname(__file__))

from src.version import VERSION, VERSION_NAME


def main():
    game_root = os.path.dirname(os.path.abspath(__file__))
    print(f"American Prospector {VERSION} ({VERSION_NAME})")

    # Ensure working directory is the game root (where exe lives)
    # so config.json, saves/, bug_reports.json are found correctly
    os.chdir(game_root)

    # For PyInstaller: set GAME_DATA_ROOT so engine can find bundled data/music
    if getattr(sys, '_MEIPASS', None):
        os.environ['GAME_DATA_ROOT'] = sys._MEIPASS
    else:
        os.environ['GAME_DATA_ROOT'] = game_root

    # Check for updates from GitHub
    try:
        from src.updater import run_update_check
        run_update_check(game_root)
    except Exception:
        pass  # no internet, no tkinter, whatever — just start the game

    # Check if using API mode — skip model download if so
    import json as _json
    _cfg = {}
    try:
        with open("config.json") as _f:
            _cfg = _json.load(_f)
    except Exception:
        pass

    llm_mode = _cfg.get("llm_mode", "local")
    if llm_mode == "local":
        # Download LLM on first run if missing
        from src.model_downloader import ensure_model, model_path
        ensure_model()
        _model = model_path()
    else:
        _model = ""  # API mode — no local model needed

    from src.engine import Engine
    engine = Engine(llm_model_path=_model)
    engine.run()


if __name__ == "__main__":
    import traceback
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        with open("error.log", "a") as _f:
            _f.write("\n--- unhandled top-level crash ---\n")
            traceback.print_exc(file=_f)
        input("\nCrash logged to error.log — press Enter to close")
