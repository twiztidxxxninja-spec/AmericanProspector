# Changelog

## 0.2.0-alpha "Blood & Iron" — 2026-03-28

### Combat Overhaul
- **Lethal firearms**: Percussion Rifle 35-70 dmg, Colt Revolver 20-40, Shotgun 40-80. One or two shots kill.
- **Melee rebalanced**: Pickaxe 15-35, Hand Axe 12-30, Hunting Knife 8-18. Every weapon is dangerous.
- **Body part HP caps**: Extremity wounds (hands, arms, legs) can't directly kill — the bleeding does. Head/chest/neck shots are immediately lethal. Getting shot in the hand does 15 HP of shock but the arterial bleed is what finishes you.
- **Aimed shots**: Choose where to aim in combat (K key) — Head (2x damage, instant kill chance), Legs (slow target), Arms (disarm), Torso (heavy bleed), Center mass (default).
- **40+ original wound descriptions**: Per damage-type and body part. "The chest is shattered by a bullet — bone fragments visible" instead of generic text.
- **40+ incapacitation lines**: Wounded characters exhibit vivid, unique behavior — clutching wounds, whispering prayers, crawling, going still.
- **30+ NPC combat taunts**: Period-appropriate threats, wounded bravado, and terrified pleas. Plus 10 insults.
- **Blood on the map**: Pink tiles for light bleeding, dark red for heavy/arterial. Blood pools form around killed targets.
- **Severed body parts**: Critical hits can fling severed limbs across the map, leaving blood trails. Parts land as items on the ground.
- **No damage numbers in combat log**: Replaced with descriptive condition ("barely standing", "bleeding heavily").
- **After Action Report**: Journal tab (AAR) records combat encounters as narrative summaries. Navigate between past fights with < and >.

### Mining & Prospecting
- **Mining Mode [M key]**: Streamlined panning and sluice work. SPACE to pan repeatedly, arrows to move between spots, ESC shows session totals.
- **Sluice Mode**: Shovel loads into sluice (SPACE), fill bar shows progress, ENTER cleans out for big gold payout. Requires shovel + water + sluice.
- **Vivid pan messages**: "Your hands are shaking. The bottom of the pan is YELLOW." Multiple random variants per grade level.
- **Depletion feedback**: "The pans are thinning out" / "The color's nearly gone. This spot is played out."
- **Test-pan workflow**: Load pan from any tile (tracks source location + depth), walk to water, wash it. Result reflects the source tile's grade.
- **Visual terrain changes**: Worked gravel (:), turned dirt (~), shallow pit (o), deep pit (O), tailings (=) show where you've been mining.
- **Sluice/rocker now active**: Must shovel material in and clean out. No more passive multiplier.

### Hunting
- **Hunting Mode [H key]**: Stalk wildlife with stealth movement. Wind direction indicator, animal state display, tracking signs.
- **Aimed shots at animals**: Fire (F) with range and hit chance displayed. TAB cycles targets. SPACE waits/watches.
- **Tracking skill integration**: Skill 1+ shows nearby track count. Skill 3+ shows direction to closest animal.

### Map & Navigation
- **Multi-scale patch system**: 14x14 area patches per world tile. Walking off a patch edge enters the adjacent patch seamlessly — no more 5-mile teleport jumps.
- **5ft tile scale**: Trees are individual trunks (block movement), NPCs adjacent = melee range, buildings have interior space.
- **Terrain continuity**: Absolute-position noise ensures terrain flows across patch boundaries with no visible seams.
- **FOV scaled for 5ft**: Daytime 60 tiles (300ft), dawn/dusk 35 tiles (175ft), night 12 tiles (60ft).
- **FOV optimized**: Cached numpy terrain array + limited wall checks. 4ms per recompute (was 123ms).
- **Compass navigation**: Sidebar shows direction and distance to nearest town when carrying a compass.
- **Terrain name in sidebar**: Shows what you're standing on (Gravel Bar, Pine Tree, Worked Gravel, etc.).
- **Streams everywhere**: Increased stream density. Most patches have at least one creek/spring. Player spawns adjacent to water.
- **Trees block movement**: Individual tree trunks are impassable at 5ft scale.
- **No fog on state/country maps**: Full-brightness terrain at zoomed-out views. City labels filtered by zoom level.
- **Structure markers on maps**: Player-built structures show as + on area and county zoom levels.
- **Fast travel anywhere**: No restriction on destination — travel to any tile on the map.

### Persistence
- **Tile state saves**: dig_depth, panned status, mineral_hint, and ground items all persist through save/load.
- **Theft tags persist**: Unpaid items survive save/reload.
- **Structure persistence**: Built equipment, walls, floors, zones all save correctly.

### Quality of Life
- **Version number**: Shown in title bar. Auto-updater checks GitHub for new versions on startup.
- **Encumbrance matters**: 1.5x movement cost at 75% capacity, 2.5x when overloaded.
- **Talk is free**: Conversation doesn't advance game time — no penalty for talking during combat.
- **Action menu filtered**: Pan/cook/fill canteen only appear when terrain/structures are appropriate.
- **Weight tracking**: Recalculated every frame. Overload warnings on pickup.
- **NPC witness range**: 200ft day, 125ft dawn/dusk, 75ft night. NPCs far away don't witness crimes.
- **Wildlife alert distances**: Scaled for 5ft tiles. Prey detects at 150-250ft, predators at 60ft.
- **Theft system**: Items picked up in settlements tagged as unpaid. Leaving triggers theft crime if witnessed.
- **pygame in requirements**: Music system no longer crashes on fresh installs.

## 0.1.0-alpha — 2026-03-28

Initial release. Core gameplay: panning, movement, NPCs, combat, survival, save/load.
