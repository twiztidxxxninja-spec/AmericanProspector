"""
American Prospector — entry point.
"""

import sys
import os

# Ensure src is on path when run from project root
sys.path.insert(0, os.path.dirname(__file__))

from src.model_downloader import ensure_model, model_path
from src.engine import Engine


def main():
    # Download LLM on first run if missing (shows progress UI, then continues)
    ensure_model()

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
