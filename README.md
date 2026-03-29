# American Prospector

A hard, comprehensive prospecting simulator set in America 1849-2000. Single character, tile-based, time-driven survival + prospecting RPG. Built with Python + python-tcod + llama-cpp-python for local AI.

Pan for gold, dig mines, build sluice boxes, trade with merchants, explore the American frontier. Every action takes time. Survival is not guaranteed.

```
  .:T^T.:~~~~~:.T^.    You stand at the edge of a gravel bar
  .T.^..:::::::.^T.    on the American River. April, 1849.
  ...:.:WORKED:.:...    The rush has begun.
  ~~~~~~~~~~::~~~~~
  ::::::::*::::::::     [A] Pan for gold
  ...:.:o:.:...::..     [M] Mining mode
                        [T] Talk to NPCs
  @ = You               [?] Help
```

## Requirements

- Windows 10/11
- Python 3.11+
- NVIDIA GPU with 8GB+ VRAM (recommended for AI features)
- ~5GB disk space (game + AI model)

The game works without a GPU but AI features (freeform actions, NPC dialogue) will be slower on CPU.

## Quick Install

1. Install [Python 3.11+](https://www.python.org/downloads/) -- check "Add Python to PATH" during install
2. Clone or download this repo
3. Double-click **`install.bat`** -- installs dependencies (tries CUDA GPU support first, falls back to CPU)
4. Double-click **`play.bat`** -- launches the game

The AI model (~4.7 GB) downloads automatically on first launch. You need internet for the first run only.

## Manual Install

```
git clone https://github.com/twiztidxxxninja-spec/AmericanProspector.git
cd AmericanProspector
pip install tcod numpy
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
python main.py
```

If the CUDA install fails (no NVIDIA GPU), use CPU-only:
```
pip install llama-cpp-python --prefer-binary
```

## Controls

| Key | Action |
|-----|--------|
| Arrows / Numpad | Move |
| A | Actions (pan, dig, build, custom) |
| M | Mining mode (pan or sluice work loop) |
| T | Talk to nearby NPC |
| I | Inventory |
| C | Character stats |
| J | Journal |
| B | Build menu |
| K | Combat |
| E | Examine |
| P | Pick up / Butcher |
| G | Gold overlay |
| [ ] | Zoom out / in (world map) |
| Enter | Fast travel (on zoomed map) |
| ? | Full controls list |

## How to Play

**Find gold:** Walk to a gravel bar (`:` tiles near water `~`). Press **A** and select "Pan for gold." You'll see what the ground holds.

**Mining mode:** Press **M** near water for rapid panning. Near a sluice box, **M** enters sluice mode -- shovel loads with SPACE, clean out with ENTER.

**Sell gold:** Find a merchant in town. Press **T** to talk, select "Sell gold dust." They'll weigh it and pay cash.

**Build equipment:** Press **B** to build sluice boxes, rocker boxes, and other equipment. Requires materials and engineering skill.

**Explore:** Use **[** to zoom out and see the world map. Press **Enter** on any tile to fast travel there.

**Survive:** Eat, drink, rest. Watch your hunger, thirst, fatigue, and warmth in the sidebar. Pan near water, hunt animals, buy food from merchants.

**Type anything:** Press **A** and type a custom action. The AI resolves what happens. "climb the tree," "set a snare," "write a letter home" -- anything is valid.

## Building a Standalone Installer

To create a distributable .exe that doesn't require Python:

```
pip install pyinstaller
python build.py
```

This creates `dist/AmericanProspector/` with a standalone game folder. To wrap it in a Windows installer, install [Inno Setup](https://jrsoftware.org/isinfo.php) and compile `installer.iss`.

## Tech Stack

- **Engine:** python-tcod (ASCII roguelike rendering, FOV, pathfinding)
- **AI:** llama-cpp-python with Qwen2.5-7B-Instruct (runs locally, no API keys needed)
- **Platform:** Windows (CUDA for GPU inference)

## License

This project is provided as-is for personal use.
