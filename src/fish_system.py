"""
src/fish_system.py

North American fish species in the 1840s with realistic regional and seasonal distribution.
"""

from dataclasses import dataclass
import random
from typing import List, Optional, Tuple


class FishType:
    # Salmonids - West Coast & Mountains
    CHINOOK_SALMON = "chinook_salmon"
    COHO_SALMON = "coho_salmon"
    SOCKEYE_SALMON = "sockeye_salmon"
    PINK_SALMON = "pink_salmon"
    CHUM_SALMON = "chum_salmon"
    STEELHEAD_TROUT = "steelhead_trout"
    RAINBOW_TROUT = "rainbow_trout"
    CUTTHROAT_TROUT = "cutthroat_trout"
    BROOK_TROUT = "brook_trout"

    # Eastern & Great Lakes
    ATLANTIC_SALMON = "atlantic_salmon"
    LAKE_TROUT = "lake_trout"

    # Bass & Sunfish
    LARGEMOUTH_BASS = "largemouth_bass"
    SMALLMOUTH_BASS = "smallmouth_bass"
    BLUEGILL = "bluegill"

    # Catfish
    CHANNEL_CATFISH = "channel_catfish"
    FLATHEAD_CATFISH = "flathead_catfish"

    # Pike & Perch
    NORTHERN_PIKE = "northern_pike"
    WALLEYE = "walleye"
    YELLOW_PERCH = "yellow_perch"

    # Sturgeon & other
    WHITE_STURGEON = "white_sturgeon"
    GREEN_STURGEON = "green_sturgeon"
    AMERICAN_EEL = "american_eel"


@dataclass
class FishSpecies:
    id: str
    display_name: str
    avg_weight_lb: float
    nutrition: int          # hunger restored
    catch_difficulty: int   # 1 = very easy, 5 = very hard
    preferred_water: List[str]   # "stream", "river", "pond", "lake", "estuary"
    core_regions: List[str]
    seasonal_availability: List[str]   # "spring", "summer", "fall", "winter"
    notes: str = ""


FISH_DB = {
    # ==============================================
    # PACIFIC SALMONIDS (West Coast & Alaska)
    # ==============================================
    FishType.CHINOOK_SALMON: FishSpecies(
        id="chinook_salmon", display_name="Chinook Salmon", avg_weight_lb=22.0, nutrition=65,
        catch_difficulty=4, preferred_water=["river", "stream"],
        core_regions=["Sierra Nevada", "California", "Pacific Northwest", "Alaska"],
        seasonal_availability=["spring", "fall"], notes="King salmon — largest and most prized"
    ),
    FishType.COHO_SALMON: FishSpecies(
        id="coho_salmon", display_name="Coho Salmon", avg_weight_lb=8.0, nutrition=35,
        catch_difficulty=3, preferred_water=["river", "stream"],
        core_regions=["California", "Pacific Northwest", "Alaska"],
        seasonal_availability=["fall"], notes="Silver salmon"
    ),
    FishType.SOCKEYE_SALMON: FishSpecies(
        id="sockeye_salmon", display_name="Sockeye Salmon", avg_weight_lb=6.0, nutrition=32,
        catch_difficulty=3, preferred_water=["river"],
        core_regions=["Alaska", "Pacific Northwest"],
        seasonal_availability=["summer", "fall"], notes="Red salmon"
    ),
    FishType.PINK_SALMON: FishSpecies(
        id="pink_salmon", display_name="Pink Salmon", avg_weight_lb=4.0, nutrition=25,
        catch_difficulty=2, preferred_water=["river"],
        core_regions=["Alaska", "Pacific Northwest"],
        seasonal_availability=["summer"], notes="Humpback salmon"
    ),
    FishType.CHUM_SALMON: FishSpecies(
        id="chum_salmon", display_name="Chum Salmon", avg_weight_lb=9.0, nutrition=38,
        catch_difficulty=3, preferred_water=["river"],
        core_regions=["Alaska", "Pacific Northwest"],
        seasonal_availability=["fall"], notes="Dog salmon"
    ),
    FishType.STEELHEAD_TROUT: FishSpecies(
        id="steelhead_trout", display_name="Steelhead Trout", avg_weight_lb=8.0, nutrition=32,
        catch_difficulty=4, preferred_water=["river", "stream"],
        core_regions=["Sierra Nevada", "California", "Pacific Northwest"],
        seasonal_availability=["winter", "spring"], notes="Sea-run rainbow trout"
    ),
    FishType.RAINBOW_TROUT: FishSpecies(
        id="rainbow_trout", display_name="Rainbow Trout", avg_weight_lb=2.5, nutrition=18,
        catch_difficulty=2, preferred_water=["stream", "river", "pond"],
        core_regions=["Sierra Nevada", "Rockies"],
        seasonal_availability=["spring", "summer", "fall"], notes="Most common western mountain trout"
    ),
    FishType.CUTTHROAT_TROUT: FishSpecies(
        id="cutthroat_trout", display_name="Cutthroat Trout", avg_weight_lb=2.8, nutrition=20,
        catch_difficulty=3, preferred_water=["stream", "river"],
        core_regions=["Sierra Nevada", "Rockies", "Great Basin"],
        seasonal_availability=["spring", "summer", "fall"], notes="Native western trout"
    ),

    # ==============================================
    # EASTERN & GREAT LAKES SPECIES
    # ==============================================
    FishType.ATLANTIC_SALMON: FishSpecies(
        id="atlantic_salmon", display_name="Atlantic Salmon", avg_weight_lb=12.0, nutrition=48,
        catch_difficulty=4, preferred_water=["river"],
        core_regions=["Northeast", "Appalachians"],
        seasonal_availability=["spring", "fall"], notes="East Coast king"
    ),
    FishType.BROOK_TROUT: FishSpecies(
        id="brook_trout", display_name="Brook Trout", avg_weight_lb=1.8, nutrition=16,
        catch_difficulty=2, preferred_water=["stream", "pond"],
        core_regions=["Appalachians", "Northeast", "Great Lakes"],
        seasonal_availability=["spring", "fall"], notes="Eastern native char"
    ),
    FishType.LAKE_TROUT: FishSpecies(
        id="lake_trout", display_name="Lake Trout", avg_weight_lb=15.0, nutrition=50,
        catch_difficulty=4, preferred_water=["lake"],
        core_regions=["Great Lakes", "Northern US"],
        seasonal_availability=["spring", "summer"], notes="Large cold-water predator"
    ),

    # ==============================================
    # BASS & SUNFISH FAMILY
    # ==============================================
    FishType.LARGEMOUTH_BASS: FishSpecies(
        id="largemouth_bass", display_name="Largemouth Bass", avg_weight_lb=4.5, nutrition=24,
        catch_difficulty=3, preferred_water=["pond", "river"],
        core_regions=["Eastern US", "California (introduced)"],
        seasonal_availability=["spring", "summer"], notes="Aggressive fighter"
    ),
    FishType.SMALLMOUTH_BASS: FishSpecies(
        id="smallmouth_bass", display_name="Smallmouth Bass", avg_weight_lb=3.5, nutrition=21,
        catch_difficulty=3, preferred_water=["river", "pond"],
        core_regions=["Eastern US", "Great Lakes"],
        seasonal_availability=["spring", "summer"], notes="Strong fighter in moving water"
    ),
    FishType.BLUEGILL: FishSpecies(
        id="bluegill", display_name="Bluegill", avg_weight_lb=0.8, nutrition=12,
        catch_difficulty=1, preferred_water=["pond", "lake"],
        core_regions=["Eastern US"],
        seasonal_availability=["spring", "summer"], notes="Abundant panfish"
    ),

    # ==============================================
    # CATFISH FAMILY
    # ==============================================
    FishType.CHANNEL_CATFISH: FishSpecies(
        id="channel_catfish", display_name="Channel Catfish", avg_weight_lb=6.0, nutrition=28,
        catch_difficulty=2, preferred_water=["river", "pond"],
        core_regions=["Great Plains", "Midwest", "California rivers"],
        seasonal_availability=["spring", "summer"], notes="Common bottom feeder"
    ),
    FishType.FLATHEAD_CATFISH: FishSpecies(
        id="flathead_catfish", display_name="Flathead Catfish", avg_weight_lb=25.0, nutrition=70,
        catch_difficulty=4, preferred_water=["river"],
        core_regions=["Midwest", "Southern US"],
        seasonal_availability=["spring", "summer"], notes="Very large predator"
    ),

    # ==============================================
    # PIKE FAMILY
    # ==============================================
    FishType.NORTHERN_PIKE: FishSpecies(
        id="northern_pike", display_name="Northern Pike", avg_weight_lb=12.0, nutrition=38,
        catch_difficulty=4, preferred_water=["river", "lake"],
        core_regions=["Great Lakes", "Northern US"],
        seasonal_availability=["spring"], notes="Aggressive predator"
    ),

    # ==============================================
    # PERCH FAMILY
    # ==============================================
    FishType.WALLEYE: FishSpecies(
        id="walleye", display_name="Walleye", avg_weight_lb=5.0, nutrition=26,
        catch_difficulty=3, preferred_water=["river", "lake"],
        core_regions=["Great Lakes", "Midwest"],
        seasonal_availability=["spring", "fall"], notes="Excellent table fish"
    ),
    FishType.YELLOW_PERCH: FishSpecies(
        id="yellow_perch", display_name="Yellow Perch", avg_weight_lb=0.8, nutrition=14,
        catch_difficulty=1, preferred_water=["lake", "river"],
        core_regions=["Great Lakes", "Northeast"],
        seasonal_availability=["spring", "summer"], notes="Abundant small panfish"
    ),

    # ==============================================
    # STURGEON
    # ==============================================
    FishType.WHITE_STURGEON: FishSpecies(
        id="white_sturgeon", display_name="White Sturgeon", avg_weight_lb=60.0, nutrition=110,
        catch_difficulty=5, preferred_water=["river"],
        core_regions=["California", "Pacific Northwest"],
        seasonal_availability=["spring"], notes="Ancient giant fish"
    ),

    # ==============================================
    # EEL & OTHER
    # ==============================================
    FishType.AMERICAN_EEL: FishSpecies(
        id="american_eel", display_name="American Eel", avg_weight_lb=3.0, nutrition=18,
        catch_difficulty=2, preferred_water=["river", "estuary"],
        core_regions=["Eastern US"],
        seasonal_availability=["spring", "fall"], notes="Migratory eel"
    ),

    # ── Additional California & Western Species ──────────────────
    "sacramento_pikeminnow": FishSpecies(
        id="sacramento_pikeminnow", display_name="Sacramento Pikeminnow",
        avg_weight_lb=3.0, nutrition=15, catch_difficulty=2,
        preferred_water=["river", "stream"],
        core_regions=["California", "Sierra Nevada"],
        seasonal_availability=["spring", "summer", "fall"],
        notes="Common in Central Valley rivers. Easy to catch, bony."
    ),
    "sacramento_sucker": FishSpecies(
        id="sacramento_sucker", display_name="Sacramento Sucker",
        avg_weight_lb=2.0, nutrition=12, catch_difficulty=1,
        preferred_water=["river", "stream", "pond"],
        core_regions=["California", "Sierra Nevada"],
        seasonal_availability=["spring", "summer", "fall", "winter"],
        notes="Bottom feeder. Year-round, easy catch, low quality."
    ),
    "tule_perch": FishSpecies(
        id="tule_perch", display_name="Tule Perch",
        avg_weight_lb=0.5, nutrition=8, catch_difficulty=1,
        preferred_water=["pond", "river"],
        core_regions=["California"],
        seasonal_availability=["spring", "summer"],
        notes="Small but plentiful. Good bait fish."
    ),
    "hardhead_minnow": FishSpecies(
        id="hardhead_minnow", display_name="Hardhead",
        avg_weight_lb=1.5, nutrition=10, catch_difficulty=1,
        preferred_water=["stream", "river"],
        core_regions=["California", "Sierra Nevada"],
        seasonal_availability=["spring", "summer", "fall"],
        notes="Native minnow. Common, easy to catch."
    ),
    "sacramento_blackfish": FishSpecies(
        id="sacramento_blackfish", display_name="Sacramento Blackfish",
        avg_weight_lb=3.0, nutrition=14, catch_difficulty=2,
        preferred_water=["pond", "river"],
        core_regions=["California"],
        seasonal_availability=["spring", "summer"],
        notes="Thrives in warm, slow water."
    ),
    "hitch": FishSpecies(
        id="hitch", display_name="Hitch",
        avg_weight_lb=1.0, nutrition=8, catch_difficulty=1,
        preferred_water=["pond", "stream"],
        core_regions=["California"],
        seasonal_availability=["spring", "summer"],
        notes="Native to Clear Lake. Small but abundant."
    ),
    "mountain_whitefish": FishSpecies(
        id="mountain_whitefish", display_name="Mountain Whitefish",
        avg_weight_lb=2.0, nutrition=14, catch_difficulty=2,
        preferred_water=["stream", "river"],
        core_regions=["Sierra Nevada", "Rocky Mountains", "Pacific Northwest"],
        seasonal_availability=["fall", "winter"],
        notes="Cold-water fish. Good eating in winter when trout are sluggish."
    ),
    "bull_trout": FishSpecies(
        id="bull_trout", display_name="Bull Trout",
        avg_weight_lb=6.0, nutrition=28, catch_difficulty=4,
        preferred_water=["stream", "river"],
        core_regions=["Pacific Northwest", "Rocky Mountains"],
        seasonal_availability=["fall", "winter"],
        notes="Cold-water predator. Aggressive, fights hard."
    ),
    "dolly_varden": FishSpecies(
        id="dolly_varden", display_name="Dolly Varden",
        avg_weight_lb=4.0, nutrition=22, catch_difficulty=3,
        preferred_water=["stream", "river"],
        core_regions=["Alaska", "Pacific Northwest"],
        seasonal_availability=["summer", "fall"],
        notes="Arctic char relative. Beautiful spotted fish."
    ),
    "green_sunfish": FishSpecies(
        id="green_sunfish", display_name="Green Sunfish",
        avg_weight_lb=0.5, nutrition=6, catch_difficulty=1,
        preferred_water=["pond", "stream"],
        core_regions=["California", "Great Plains", "Eastern US"],
        seasonal_availability=["spring", "summer"],
        notes="Tiny but everywhere. Good for beginners."
    ),
    "white_catfish": FishSpecies(
        id="white_catfish", display_name="White Catfish",
        avg_weight_lb=4.0, nutrition=20, catch_difficulty=2,
        preferred_water=["river", "pond"],
        core_regions=["California", "Eastern US"],
        seasonal_availability=["spring", "summer", "fall"],
        notes="Night feeder. Best caught after dark."
    ),
    "striped_bass": FishSpecies(
        id="striped_bass", display_name="Striped Bass",
        avg_weight_lb=12.0, nutrition=40, catch_difficulty=4,
        preferred_water=["river", "estuary"],
        core_regions=["California", "Eastern US"],
        seasonal_availability=["spring", "fall"],
        notes="Large, powerful. Fights hard. Excellent eating."
    ),
    "pacific_lamprey": FishSpecies(
        id="pacific_lamprey", display_name="Pacific Lamprey",
        avg_weight_lb=1.5, nutrition=15, catch_difficulty=2,
        preferred_water=["river", "stream"],
        core_regions=["California", "Pacific Northwest"],
        seasonal_availability=["spring"],
        notes="Eel-like. Valued food for Native peoples."
    ),
}


class FishingMechanics:
    @staticmethod
    def attempt_catch(region_name: str, method: str, survival_skill: int,
                      season: str, rng: random.Random) -> Optional[FishSpecies]:
        """
        Attempt to catch a fish.
        method: "pole", "spear", "net", "trap", "hand"
        Returns FishSpecies on success, None on failure.
        """
        possible = [f for f in FISH_DB.values()
                    if season in f.seasonal_availability
                    and any(r.lower() in region_name.lower() for r in f.core_regions)]

        # Fall back to widespread species if nothing matches (e.g. generic plains river)
        if not possible:
            possible = [FISH_DB[FishType.CHANNEL_CATFISH],
                        FISH_DB[FishType.RAINBOW_TROUT]]

        # Base success chance
        base = 0.20 + (survival_skill * 0.06)

        method_bonus = {
            "pole":  0.40,
            "net":   0.35,
            "spear": 0.25,
            "trap":  0.35,
            "hand":  0.10,
        }.get(method, 0.20)

        if rng.random() > (base + method_bonus):
            return None

        # Weighted by inverse difficulty (easier fish caught more often)
        weights = [max(1, 6 - f.catch_difficulty) for f in possible]
        return rng.choices(possible, weights=weights, k=1)[0]

    @staticmethod
    def time_cost(method: str) -> int:
        """Minutes spent fishing per attempt."""
        return {"pole": 30, "net": 20, "spear": 15, "trap": 60, "hand": 20}.get(method, 30)

    @staticmethod
    def get_catch_message(fish: FishSpecies, method: str) -> str:
        if fish.avg_weight_lb >= 30:
            return f"You haul in a massive {fish.display_name} using your {method}!"
        elif fish.avg_weight_lb >= 10:
            return f"You catch a large {fish.display_name}!"
        else:
            return f"You catch a {fish.display_name}."