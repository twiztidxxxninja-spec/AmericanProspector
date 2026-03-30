# American Prospector

A hard, comprehensive Gold Rush simulator set in 1849 California. ASCII roguelike with survival, prospecting, trading, combat, trapping, business management, and AI-powered freeform actions.

---

## How to Play

1. **Download** — click the green "Code" button on GitHub → "Download ZIP"
2. **Unzip** anywhere
3. **Double-click `PLAY.bat`**

That's it. If Python isn't installed, it opens the Microsoft Store for you — click Install (free), then double-click PLAY.bat again. Everything else is automatic.

**First run** takes ~30 seconds to install game libraries. After that it starts instantly.

**The game does not:**
- Install anything to your system
- Modify your registry or system files
- Run at startup or in the background
- Access anything outside its own folder

Delete the folder and it's completely gone.

---

## Configuration (Optional)

Settings are in `config.json` in the game folder. If missing, game uses defaults.

### AI Modes

**API mode** (recommended, already configured if someone set it up for you):
```json
"llm_mode": "api",
"llm_api_key": "sk-ant-your-key-here"
```
Uses Claude AI over the internet. No downloads, no GPU. 3-8 second delay on freeform actions only.

**Local mode** (for players with a gaming GPU):
```json
"llm_mode": "local",
"model_path": "models/qwen2.5-7b-instruct-q4_k_m.gguf"
```
Requires 5GB model download + 8GB+ GPU VRAM. Faster, no content filtering.

**No AI** (game fully playable without it):
```json
"llm_enabled": false
```
All hardcoded gameplay works. Freeform typed actions get generic responses.

---

## Bug Reports

Press **ESC** in-game → **Report Bug** → type what happened → Enter. Sent automatically.

---

## Controls

| Key | Action |
|-----|--------|
| Arrows / Numpad | Move |
| A | Actions menu |
| I | Inventory |
| C | Crafting |
| T | Talk to NPC |
| K | Combat mode |
| B | Build |
| E | Examine |
| J | Journal |
| ? | Help (detailed) |
| ESC | Pause menu |

---

## What Is This Game?

You arrive in California in 1849 with $150, a mule, a rifle, and a gold pan. Pan for gold, stake claims, hunt, trap, craft 111 items, brew whiskey, start businesses, fight bandits, survive winters, get rich or die trying.

v0.3.0-alpha "Fur & Fortune"

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
