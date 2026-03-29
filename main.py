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

    # Check for updates from GitHub
    try:
        from src.updater import run_update_check
        run_update_check(game_root)
    except Exception:
        pass  # no internet, no tkinter, whatever — just start the game

    # Download LLM on first run if missing
    from src.model_downloader import ensure_model, model_path
    ensure_model()

    from src.engine import Engine
    engine = Engine(llm_model_path=model_path())
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
