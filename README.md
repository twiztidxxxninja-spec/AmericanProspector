# American Prospector

A historically accurate American frontier survival roguelike spanning 1780-1972. Hunt, trap, prospect, fight, trade, build, and survive across eight playable eras -- from Appalachian long hunters to Cold War uranium prospectors. ASCII graphics, AI-powered freeform actions, and no two playthroughs alike.

**v0.4.0-alpha "Powder & Shot"** -- Historical wars, battles, enlistment, NPC combat, artillery, language barriers, disease, river travel, 12 pages of in-game help.

```
  .:T^T.:~~~~~:.T^.    You hear cannon fire to the south.
  .T.^..:::::::.^T.    A column of soldiers marches past
  ...:.:WORKED:.:...    heading west. The Revolution rages
  ~~~~~~~~~~::~~~~~     on, but out here, it's your rifle
  ::::::::*::::::::     against the wilderness.
  ...:.:o:.:...::..
                        [A] Actions   [M] Mining mode
  @ = You               [T] Talk      [?] Help (12 pages)
```

---

## Installation

### Option A: Just Play (Windows, easiest)

1. **Download** -- click the green **Code** button above, then **Download ZIP**
2. **Unzip** anywhere (Desktop, Documents, wherever)
3. **Double-click `PLAY.bat`**

That's it. If Python isn't installed, it opens the Microsoft Store for you -- click Install (free), then double-click PLAY.bat again.

**First run** takes ~30 seconds to install game libraries. After that it starts instantly.

### Option B: Git Clone (Windows)

```bash
git clone https://github.com/twiztidxxxninja-spec/AmericanProspector.git
cd AmericanProspector
play.bat
```

### Option C: Manual Install (Windows / Linux / Mac)

#### Prerequisites

- **Python 3.11 or newer** -- [download here](https://www.python.org/downloads/)
  - **Windows:** check "Add Python to PATH" during the installer
  - **Linux:** `sudo apt install python3 python3-pip` (Ubuntu/Debian) or `sudo dnf install python3 python3-pip` (Fedora)
  - **Mac:** `brew install python` or use the python.org installer

#### Step-by-step

```bash
# 1. Clone the repository
git clone https://github.com/twiztidxxxninja-spec/AmericanProspector.git
cd AmericanProspector

# 2. Install required libraries
pip install tcod numpy pygame-ce

# 3. (Optional) Install local AI support for freeform actions
#    With NVIDIA GPU (CUDA, fastest):
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

#    Without NVIDIA GPU (CPU-only, slower but works):
pip install llama-cpp-python --prefer-binary

# 4. Run the game
python main.py
```

The AI model (~4.7 GB) downloads automatically on first launch if using local mode. You need internet for that first run only.

### Option D: Full Setup Script (Windows)

```bash
# From the game folder:
dev\install.bat
```

This script:
1. Checks for Python
2. Installs tcod, numpy, pygame-ce
3. Tries CUDA-accelerated llama-cpp-python, falls back to CPU if no NVIDIA GPU
4. Reports success or failure at each step

After install, run `play.bat` or `python main.py`.

---

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10, Linux, macOS | Windows 11 |
| Python | 3.11+ | 3.12+ |
| RAM | 4 GB | 8 GB |
| Disk | 500 MB (no AI) | 6 GB (with AI model) |
| GPU | None required | NVIDIA 8GB+ VRAM (for local AI) |

The game is fully playable without a GPU and without AI. Freeform typed actions get generic responses without AI; all hardcoded gameplay works perfectly.

---

## AI Modes

Settings are in `config.json` (created from `config.json.example` on first run).

**No AI** (default, game fully playable):
```json
"llm_enabled": false
```

**API mode** (recommended if you have an Anthropic key):
```json
"llm_mode": "api",
"llm_api_key": "sk-ant-your-key-here"
```
Uses Claude AI over the internet. No downloads, no GPU needed. 3-8 second delay on freeform actions only.

**Local mode** (for players with a gaming GPU):
```json
"llm_mode": "local",
"model_path": "models/qwen2.5-7b-instruct-q4_k_m.gguf"
```
Requires ~5 GB model download + 8 GB+ GPU VRAM. Faster responses, no content filtering, fully offline after first download.

---

## What Gets Installed

- Three Python libraries: `tcod`, `pygame-ce`, `numpy` (via pip)
- Optionally: `llama-cpp-python` (for local AI)
- Optionally: ~4.7 GB AI model in `models/` folder (first launch, local mode only)
- Save files go in `saves/` inside the game directory
- **No registry changes, no startup entries, no background processes**

**To fully uninstall:** delete the game folder. Optionally `pip uninstall tcod pygame-ce numpy llama-cpp-python` to remove the libraries.

---

## Controls

| Key | Action |
|-----|--------|
| Arrow keys / Numpad | Move |
| A | Actions (eat, drink, forage, pan, dig, custom...) |
| M | Mining mode (area select, pan/sluice auto-work) |
| H | Hunting mode (stalk, track, shoot) |
| Y | Trapping mode (set, check, collect traps) |
| K | Combat mode |
| T | Talk (trade, barter, hire, enlist, learn language) |
| I | Inventory (items, equip, clothing) |
| C | Character (stats, health, wounds, skills) |
| J | Journal (diary, people, places, rumors, mail) |
| B | Build (structures, walls, furniture, zones) |
| E | Examine nearby |
| P | Pick up items / Butcher carcasses |
| L | Message log (scroll history) |
| G | Gold overlay (panned tile grades) |
| S | Cycle stance |
| W | Cycle speed |
| < > | Z-level up/down |
| [ ] | Zoom out/in (world map) |
| Enter | Fast travel (on world map) |
| Space | Wait / Rest / Sleep |
| Ctrl+S | Save game |
| ? | Help (12 pages, era-aware) |
| Esc | Pause menu |

Press **?** in-game for 12 pages of detailed help covering every mode, feature, and mechanic.

---

## Playable Eras

| Era | Year | Starting Region | Focus |
|-----|------|-----------------|-------|
| Long Hunters | 1780 | Appalachian Frontier | Deer hides, frontier survival, Revolution-era |
| Mountain Men | 1825 | Missouri Frontier | Beaver trapping, fur trade, Rendezvous |
| Gold Rush | 1849 | Northern California | Placer gold, boomtowns, lawless west |
| Industrial Mining | 1872 | Nevada / Colorado | Lode mining, dynamite, railroads |
| Petroleum Age | 1901 | Texas / Oklahoma | Oil drilling, gushers, black gold |
| Depression Era | 1933 | Colorado / New Mexico | $35/oz gold, desperate prospecting |
| Atomic Age | 1948 | Colorado Plateau | Uranium, Geiger counters, AEC contracts |
| Regulated Era | 1972 | Montana / Idaho | Permits, NEPA, free-market gold |

Currently playable: **Long Hunters, Mountain Men, Gold Rush**. Later eras are defined and coming.

---

## Features

### Prospecting & Mining
- Pan for gold, build sluice boxes, rockers, long toms, arrastras
- Area-select tiles, auto-work animation (watch your @ walk and pan)
- Riffle capacity system -- clean out when riffles fill up
- Historically accurate gold distribution by region
- Nugget system calibrated to real geology (Appalachian gold small but pure, California up to 25 oz)
- Z-level mining -- dig ramps, excavate deeper pay layers

### Combat
- Firearms are lethal -- one rifle shot can kill
- Body-part targeting (legs, chest, head, arms, abdomen, eyes)
- Cover system (partial, full), crouch/stand toggle
- Melee escalation -- bar fights stay melee unless someone draws a gun
- Intimidation, surrender, grappling
- Weapon-specific kill/hit/miss messages (100+ unique, no repeats)
- Detailed wound feedback -- no HP numbers, just what you see

### Historical Wars
- 12 historical wars from Lord Dunmore's War (1774) to the Apache Wars (1886)
- Wars are background events that change the world: supply shortages, price spikes, refugees, military patrols, destroyed settlements
- Enlist as scout, soldier, or medic at frontier forts
- Historical battles at the right place and date -- hear cannon fire, choose to join or avoid
- Multi-patch battlefields with 20-30 real NPC combatants per patch
- Artillery fire, NPC-vs-NPC combat, hybrid army scaling
- Player impact scoring -- your actions can shift small battle outcomes
- Wartime kills of enemy combatants are not crimes; killing civilians still is
- Medic role: drag wounded, bandage, treat with full health system
- Desertion bounties, faction reputation, conscription patrols

### Survival
- Hunger, thirst, fatigue, warmth -- neglect any and you die
- 7 diseases: cholera, dysentery, malaria, smallpox, typhoid, mountain fever, wound infection
- Prevention through gameplay (boil water, campfire smoke, bandage wounds)
- Diseases warn before they kill -- pay attention and you'll live
- Alcohol system: warmth bonus but fatigue drain, aim penalties, blackout
- Detailed wound system with bleeding, infection, limb damage

### NPCs & Social
- Language barriers: gesture, pidgin, fluent (9 tribal + 4 European languages)
- Learn languages through practice, word-pointing, bilingual NPC lessons
- NPCs remember you, hold grudges, build relationships
- NPC-initiated conversation topics (wounded, destitute, jealous, gossip)
- Overheard NPC-to-NPC conversations with actionable intelligence
- Marriage system with full relationship progression
- Provocation -- insults and threats have consequences
- 35+ emergent NPC mishap events (drunk incidents, animal mischief, dark comedy)

### Economy & Business
- Era-accurate gold prices ($19-$120+/oz across 200 years)
- Barter system -- trade items directly, no cash needed
- 20+ business types: saloon, store, smithy, sawmill, bakery, livery, hotel
- Production chains (sawmill: logs->planks, bakery: flour->bread)
- Hire managers, set pricing strategy, work it yourself
- Buy property, build on your land, store items

### World
- Massive procedural map of the American continent
- Historically accurate wildlife distribution with era-specific population curves
- Frontier line moves west over the decades
- Seasonal weather: frozen rivers, floods, drought, wildfire
- World elevation system (feet above sea level)
- Historical trail system (Wilderness Road, Oregon Trail, Santa Fe Trail)
- River/canoe travel with upstream/downstream speed
- Steamboat routes on major rivers
- Dynamic settlements that grow, shrink, and die

### Crafting & Building
- 127+ recipes: food, weapons, ammo, tools, clothing, shelters, traps, medicine
- Build mode with wall/door/window/fence/floor placement
- Multi-level structures with Z-level construction
- Portable structures -- pick up and relocate
- Custom LLM blueprints -- describe what you want to build
- Construction continues across sessions

### Other
- Hunting mode with stalking, tracking, shooting
- Trapping mode with 4 trap types, auto-bait, field crafting
- Fishing with 6 methods (hands, net, rod, trap, weir, spear)
- Foraging with 50+ plants by region and season
- Gambling: poker, blackjack, dice, marked cards
- Bounty hunting system
- Newspaper system with era-appropriate headlines
- Journal with diary, people, places, rumors, mail, combat logs
- Pack animals (mule, horse, donkey, ox) with feeding and health
- Vehicles (handcart to freight wagon, canoe to keelboat)
- Tribal capture/escape/adoption mechanics
- Rival prospectors competing for claims
- AI-powered freeform actions -- type anything, the game resolves it

---

## Bug Reports

Press **ESC** in-game, select **Report Bug**, type what happened, press Enter. Sent automatically.

---

## Building a Standalone Installer

To create a distributable .exe that doesn't require Python:

```bash
pip install pyinstaller
python dev/build.py
```

This creates `dist/AmericanProspector/` with a standalone game folder. To wrap it in a Windows installer, install [Inno Setup](https://jrsoftware.org/isinfo.php) and compile `installer.iss`.

---

## Tech Stack

- **Engine:** python-tcod (ASCII roguelike rendering, FOV, pathfinding)
- **Audio:** pygame-ce (music, sound effects)
- **AI:** llama-cpp-python with Qwen 2.5 7B-Instruct (local) or Claude API (remote)
- **Platform:** Windows primary, Linux/Mac compatible

---

## License

This project is provided as-is for personal use.
