"""
src/npc_knowledge.py

Hardcoded NPC knowledge response system.
Replaces LLM calls for practical game questions. When a player asks an NPC
about trapping, plants, survival, etc., they get a real, accurate,
deterministic answer grounded in 1840s-1860s frontier knowledge.

Every response is period-appropriate, actionable, and teaches the player
how to play the game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class KnowledgeTopic:
    topic_id: str
    keywords: List[str]
    label: str
    category: str  # survival, plants, animals, crafting, mining, trading, local, combat, legal
    occupations: List[str]  # NPC occupations that answer well; empty = anyone
    response: str
    teaches_plants: List[str] = field(default_factory=list)
    teaches_skill_xp: Tuple[str, float] = ("", 0.0)
    requires_friendly: bool = False


# =============================================================================
#  MASTER KNOWLEDGE DATABASE
# =============================================================================

KNOWLEDGE_DB: List[KnowledgeTopic] = [

    # =========================================================================
    #  SURVIVAL  (15+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="fire_making",
        keywords=["fire", "make fire", "start fire", "flint", "tinder", "campfire"],
        label="How to make fire",
        category="survival",
        occupations=[],
        response=(
            "Strike your flint against steel at a sharp angle to throw sparks "
            "into a tinder nest of dry grass, birch bark, or cedar shavings. "
            "Once the tinder catches, blow gently and add small kindling sticks "
            "before building up to larger wood. In wet weather, split dead "
            "standing wood to get dry heartwood for kindling -- never use "
            "wood from the ground, it soaks up rain."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="build_shelter",
        keywords=["shelter", "build shelter", "lean-to", "debris hut", "camp", "make camp"],
        label="How to build shelter",
        category="survival",
        occupations=[],
        response=(
            "For a quick lean-to, prop a ridgepole between two trees at "
            "chest height and lean branches against one side at a steep angle. "
            "Pile evergreen boughs or bark on top for rain shedding. A debris "
            "hut is warmer: build a low ridgepole just wider than your body, "
            "lean sticks along both sides, then heap leaves and pine needles "
            "two feet thick over the frame. Always face the opening away "
            "from prevailing wind."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="find_water",
        keywords=["water", "find water", "thirsty", "drink", "stream", "spring"],
        label="How to find water",
        category="survival",
        occupations=[],
        response=(
            "Follow game trails downhill -- animals visit water daily. Look "
            "for green vegetation in otherwise dry country; cottonwoods and "
            "willows always grow near water. Listen for running streams, "
            "especially in the mornings when the air is still. In mountains, "
            "check the base of cliffs and rock outcrops for seeps. Dig a "
            "hole in a dry streambed where the sand is damp and let it fill."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="blizzard_survival",
        keywords=["blizzard", "snowstorm", "whiteout", "snow storm", "stuck in snow"],
        label="What to do in a blizzard",
        category="survival",
        occupations=[],
        response=(
            "Do NOT try to travel in a whiteout -- men walk in circles and "
            "freeze to death within a mile of shelter. Dig into a snowbank "
            "and hollow out a cave just big enough to sit in. Pack the walls "
            "smooth so they don't drip. A single candle inside raises the "
            "temperature above freezing. Conserve body heat: sit on your "
            "pack, not bare snow, and eat any food you have -- your body "
            "burns fuel to stay warm."
        ),
        teaches_skill_xp=("survival", 8.0),
    ),

    KnowledgeTopic(
        topic_id="cross_river",
        keywords=["river", "cross river", "ford", "crossing", "wade", "swim across"],
        label="How to cross a river",
        category="survival",
        occupations=[],
        response=(
            "Test the depth with a long pole before wading. Unbuckle your "
            "pack so you can shed it if you fall. Remove your boots and tie "
            "them around your neck -- bare feet grip rocks better, and dry "
            "boots save your life afterward. Face upstream and angle your "
            "crossing downstream with the current, never fight it straight "
            "across. If you have rope, tie it to a tree and use it as a "
            "safety line."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="avoid_bears",
        keywords=["bear", "bears", "grizzly", "bear attack", "avoid bear"],
        label="How to avoid bears",
        category="survival",
        occupations=["Trapper", "Scout"],
        response=(
            "Make noise on the trail -- talk, sing, clap. Most bears run "
            "from human sound. Never run from a grizzly; it triggers their "
            "chase instinct and they outrun a horse over short ground. If "
            "charged, stand tall and speak firmly. If knocked down, play "
            "dead face-down with hands behind your neck. Hang food and "
            "greasy goods from a tree branch at least ten feet up and four "
            "feet out from the trunk, well away from where you sleep."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="stay_warm",
        keywords=["warm", "stay warm", "cold", "freeze", "freezing", "hypothermia", "frostbite"],
        label="How to stay warm",
        category="survival",
        occupations=[],
        response=(
            "Three things kill you in cold: wet clothes, no shelter, and "
            "an empty stomach. Change out of wet clothes immediately -- even "
            "rolling in dry snow is better than staying soaked. Build a fire "
            "with a reflector wall of green logs behind it to throw heat "
            "toward your shelter. Eat fatty food: tallow, pemmican, bear "
            "grease. Fat burns slow and keeps your body furnace stoked "
            "through the night."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="pine_needle_tea",
        keywords=["pine needle tea", "pine tea", "pine needles", "scurvy tea"],
        label="Pine needle tea",
        category="survival",
        occupations=[],
        response=(
            "Strip fresh green needles from pine, spruce, or fir -- avoid "
            "yew, which is poisonous. Chop the needles and steep them in "
            "hot water for ten minutes. The tea is tart and full of the "
            "vitamin that prevents scurvy. Drink a cup daily when you have "
            "no fresh vegetables or fruit. The needles are available year-round, "
            "even in deep winter."
        ),
        teaches_plants=["pine_needles"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="prevent_scurvy",
        keywords=["scurvy", "bleeding gums", "teeth falling", "prevent scurvy"],
        label="How to prevent scurvy",
        category="survival",
        occupations=[],
        response=(
            "Scurvy comes from months without fresh greens or fruit. Your "
            "gums bleed first, then old wounds reopen, then you die. Eat "
            "anything green: pine needle tea works well, and rose hips have "
            "more of the curative than lemons. Wild onions, watercress, and "
            "spruce tips all prevent it. Even raw potatoes help. Make pine "
            "needle tea a daily habit in winter camp and you will be fine."
        ),
        teaches_plants=["pine_needles", "rose_hips"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="eat_in_winter",
        keywords=["eat in winter", "winter food", "food in snow", "starving winter",
                  "what to eat winter"],
        label="What to eat in winter",
        category="survival",
        occupations=[],
        response=(
            "Cache food in fall: jerk meat, make pemmican, store dried "
            "berries. In a pinch, the inner bark of pine and aspen is "
            "edible -- scrape the white cambium layer and eat it raw or "
            "roast it. Cattail roots can be dug from frozen marsh edges. "
            "Set snares for rabbit and ptarmigan. Chop holes in ice for "
            "fishing -- trout and whitefish feed all winter."
        ),
        teaches_plants=["cattail_root"],
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="navigate_wilderness",
        keywords=["navigate", "lost", "direction", "compass", "find way", "which way",
                  "north"],
        label="How to navigate without a compass",
        category="survival",
        occupations=["Scout", "Trapper"],
        response=(
            "The North Star sits above the last two stars of the Big Dipper's "
            "cup -- follow the line they make upward. By day, drive a stick "
            "into the ground and mark the tip of its shadow, wait an hour, "
            "mark again; the line between marks runs east-west. Moss grows "
            "thicker on the north side of trees in deep forest. Rivers "
            "generally flow toward lower, flatter country -- follow them "
            "downstream to reach settlements."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="lightning_safety",
        keywords=["lightning", "thunder", "thunderstorm", "storm safety"],
        label="What to do in a thunderstorm",
        category="survival",
        occupations=[],
        response=(
            "Get off ridgelines and away from lone trees -- lightning "
            "strikes the tallest thing around. Drop metal tools and your "
            "rifle at a distance. Crouch low in a depression or among short "
            "brush with your feet together. In forest, stay among shorter "
            "trees, not the tallest ones. If your hair stands on end, drop "
            "flat immediately -- a strike is imminent."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="signal_for_help",
        keywords=["signal", "help", "rescue", "lost signal", "smoke signal"],
        label="How to signal for help",
        category="survival",
        occupations=[],
        response=(
            "Three of anything is a distress signal: three fires in a "
            "triangle, three gunshots, three columns of smoke. Build a "
            "smoky fire with green branches or wet grass on top of a high "
            "point. A mirror or any shiny metal flashed toward the sun "
            "can be seen for miles. At night, keep a fire burning on the "
            "highest ground you can safely reach."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="quicksand",
        keywords=["quicksand", "sinking", "mud stuck", "bog"],
        label="How to escape quicksand",
        category="survival",
        occupations=[],
        response=(
            "Do not thrash -- that drives you deeper. Lean back slowly to "
            "spread your weight across the surface. Work your legs in small "
            "circles to let water in around them, then pull each leg free "
            "slowly. Crawl on your belly toward solid ground. A walking "
            "stick laid flat gives you something to pull against. Quicksand "
            "is rarely deeper than waist height, but panic kills."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="snakebite",
        keywords=["snake", "snakebite", "rattlesnake", "venom", "bitten by snake"],
        label="What to do about snakebite",
        category="survival",
        occupations=["Doctor"],
        response=(
            "Stay calm and still -- a racing heart spreads the venom faster. "
            "Do NOT cut the wound or try to suck out the poison, that just "
            "causes infection. Remove rings and tight clothing before the "
            "swelling starts. Splint the bitten limb and keep it below heart "
            "level. Get to a doctor if you can, otherwise rest and drink "
            "water. Most rattlesnake bites are survivable if you stay still."
        ),
        teaches_skill_xp=("firstAid", 5.0),
    ),

    # =========================================================================
    #  PLANTS  (20+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="edible_mushrooms",
        keywords=["mushroom", "mushrooms", "edible mushroom", "morel", "chanterelle",
                  "puffball", "fungi"],
        label="Edible mushrooms",
        category="plants",
        occupations=["Trapper", "Scout", "Farmer"],
        response=(
            "Morels are the safest to learn -- they look like a wrinkled "
            "brown sponge on a stem, hollow inside. Find them in spring "
            "near dead elms and in burned areas. Chanterelles are golden, "
            "funnel-shaped, and smell like apricots; look under oaks in "
            "summer. Giant puffballs are safe when the inside flesh is pure "
            "white. NEVER eat a white-capped mushroom with a skirt on the "
            "stem and a cup at the base -- that is the destroying angel and "
            "it will kill you dead in three days."
        ),
        teaches_plants=["morel_mushroom", "chanterelle", "puffball_mushroom"],
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="edible_berries",
        keywords=["berries", "edible berries", "wild berries", "chokecherry",
                  "serviceberry", "berry picking"],
        label="Edible berries",
        category="plants",
        occupations=[],
        response=(
            "Chokecherries grow in thick clusters along streams -- they are "
            "sour raw but good dried or in pemmican. Serviceberries ripen "
            "in midsummer on rocky hillsides and taste like mild blueberries. "
            "Regular wild berries -- blackberries, raspberries -- grow in "
            "sunny clearings and forest edges. AVOID white berries as a rule, "
            "especially baneberry, which has a black dot on each white fruit "
            "and will sicken or kill you."
        ),
        teaches_plants=["chokecherry", "serviceberry", "wild_berries"],
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="edible_roots",
        keywords=["roots", "edible roots", "dig roots", "cattail", "camas", "bitterroot",
                  "turnip", "root digging"],
        label="Edible roots",
        category="plants",
        occupations=["Trapper", "Scout", "Farmer"],
        response=(
            "Cattail roots grow in any marsh and can be eaten year-round -- "
            "peel and roast them or pound them into flour. Camas root is a "
            "staple: it has blue flowers and grows in wet meadows. Dig the "
            "bulbs and pit-roast them for two days to sweeten them. Bitterroot "
            "grows on dry, rocky slopes -- peel off the bitter red outer layer "
            "and boil the white core. Wild turnip is starchy and filling. "
            "Be CAREFUL with camas: death camas looks similar but has white "
            "or yellow flowers and is deadly poisonous."
        ),
        teaches_plants=["cattail_root", "camas_root", "wild_turnip", "bitterroot"],
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="poisonous_plants",
        keywords=["poison", "poisonous", "toxic", "dangerous plant", "hemlock",
                  "nightshade", "death camas", "avoid plant"],
        label="Poisonous plants",
        category="plants",
        occupations=[],
        response=(
            "Water hemlock is the deadliest plant in the territory -- it "
            "looks like wild carrot but grows near water and has a chambered "
            "root that smells like raw parsnip. One bite of the root can kill "
            "a grown man. Destroying angel is a pure white mushroom that "
            "causes liver failure -- you feel fine for a day, then die. "
            "Baneberry has white fruit with a black dot. Nightshade has "
            "shiny black berries on a sprawling vine. When in doubt, do not "
            "eat it."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="medicinal_plants",
        keywords=["medicine", "medicinal", "healing plant", "herbal", "yarrow",
                  "wild mint", "remedy", "herb"],
        label="Medicinal plants",
        category="plants",
        occupations=["Doctor", "Trapper", "Scout"],
        response=(
            "Yarrow is the soldier's herb -- chew the leaves into a paste "
            "and pack it on a wound to slow bleeding. It grows everywhere "
            "in open meadows with flat white flower clusters. Wild mint "
            "settles a sour stomach and eases headache -- brew a strong tea "
            "from the leaves. Pine needle tea prevents scurvy as well as "
            "lemon juice. Willow bark tea reduces fever and eases pain -- "
            "strip bark from young branches and steep it."
        ),
        teaches_plants=["yarrow", "wild_mint", "pine_needles"],
        teaches_skill_xp=("firstAid", 5.0),
    ),

    KnowledgeTopic(
        topic_id="identify_berries",
        keywords=["identify berries", "what berries", "unknown berries",
                  "these berries", "are these safe"],
        label="What are those berries",
        category="plants",
        occupations=["Trapper", "Scout", "Farmer"],
        response=(
            "Show me what you have. General rules: blue and black berries "
            "are usually safe. Red berries are fifty-fifty. White berries "
            "are almost always poisonous. If the berry has a crown like a "
            "tiny rose on the bottom, it is in the rose family and safe. "
            "Crush one and smell it -- anything bitter or soapy, leave it "
            "alone. If you must test an unknown berry, rub it on your wrist "
            "first, then your lip, then eat one and wait a full day."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="camas_root_detail",
        keywords=["camas", "camas root", "quamash", "camas cooking"],
        label="Camas root",
        category="plants",
        occupations=["Trapper", "Scout"],
        response=(
            "Camas has a blue flower and grows in wet mountain meadows. The "
            "Indians dig the bulbs after flowering. You MUST cook them: dig "
            "a pit, line it with hot rocks, layer the bulbs with wet grass, "
            "cover with earth, and let them steam for two full days. Raw "
            "camas is hard and tasteless; cooked camas is sweet like a "
            "chestnut. Never confuse it with death camas, which has WHITE "
            "or yellowish flowers growing in the same meadows."
        ),
        teaches_plants=["camas_root"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="pemmican_recipe",
        keywords=["pemmican", "make pemmican", "trail food", "preserved food",
                  "dry meat", "jerky pemmican"],
        label="How to make pemmican",
        category="plants",
        occupations=["Trapper", "Scout"],
        response=(
            "Cut lean meat -- elk, deer, or buffalo -- into thin strips and "
            "dry it over a low smoky fire until it is hard and brittle. Pound "
            "the dried meat into shreds with a rock. Render animal fat until "
            "liquid. Mix equal parts pounded meat and hot fat, add dried "
            "berries -- serviceberries or chokecherries -- and press the "
            "mixture into rawhide bags. Pemmican keeps for years and a "
            "handful will fuel you through a day of hard travel."
        ),
        teaches_skill_xp=("cooking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="rose_hips",
        keywords=["rose hips", "rose hip", "wild rose"],
        label="Rose hips",
        category="plants",
        occupations=[],
        response=(
            "After wild roses drop their petals in fall, the red seed pods "
            "left behind are rose hips. They are tart and full of the same "
            "curative as citrus fruit. Eat them raw, brew them as tea, or "
            "mash them into jam. Cut each one open and scrape out the hairy "
            "seeds inside before eating. Rose hips hang on the bush well "
            "into winter and are one of the best scurvy preventives on the "
            "frontier."
        ),
        teaches_plants=["rose_hips"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="wild_onion",
        keywords=["wild onion", "onion", "onions"],
        label="Wild onion",
        category="plants",
        occupations=[],
        response=(
            "Wild onions grow in grassy clearings and smell just like garden "
            "onions when you crush the leaves. The bulb is small but edible "
            "raw or cooked. They add flavor to any camp stew and have some "
            "scurvy-preventing properties. Be sure it smells like onion -- "
            "death camas bulbs look similar but have no onion scent. If it "
            "does not smell like onion, do not eat it."
        ),
        teaches_plants=["wild_onion"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="acorns",
        keywords=["acorn", "acorns", "oak nuts", "oak tree food"],
        label="Eating acorns",
        category="plants",
        occupations=[],
        response=(
            "Acorns from white oaks are milder, but all acorns need the "
            "tannin leached out or they will make you sick. Crack the shells, "
            "grind the nutmeat, and soak it in running water or change the "
            "water repeatedly for a day or two until the bitterness is gone. "
            "The resulting mush can be dried into flour for bread or "
            "porridge. The Indians rely on acorn flour as a staple food."
        ),
        teaches_plants=["acorns"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="watercress",
        keywords=["watercress", "water cress", "cress"],
        label="Watercress",
        category="plants",
        occupations=[],
        response=(
            "Watercress grows in clean, cold, running streams. It has small "
            "round leaves and a peppery bite. Eat it raw as a salad green "
            "or toss it into soup. It is excellent against scurvy. Only "
            "gather it from clear running water, never stagnant pools, as "
            "it can carry sickness from bad water."
        ),
        teaches_plants=["watercress"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="nuts_foraging",
        keywords=["nuts", "walnut", "hickory nut", "pinon", "pine nut"],
        label="Gathering nuts",
        category="plants",
        occupations=[],
        response=(
            "Black walnuts fall in autumn -- crack the tough green husks off "
            "and dry the nuts before cracking the inner shell. Hickory nuts "
            "are rich and sweet; look for shagbark hickories. Pinon pines "
            "in dry country drop small, oily nuts that are excellent roasted. "
            "Nuts are the best calorie source you can forage -- a pocket of "
            "nuts has more sustenance than a pound of berries."
        ),
        teaches_plants=["black_walnut", "hickory_nut", "pinon_nuts"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="prickly_pear",
        keywords=["prickly pear", "cactus", "cactus fruit", "nopal"],
        label="Prickly pear cactus",
        category="plants",
        occupations=[],
        response=(
            "The red or purple fruits of prickly pear ripen in late summer. "
            "Roll them on the ground with a stick to knock off the tiny "
            "hair-like spines, then peel and eat the sweet pulp. The flat "
            "pads can be peeled, sliced, and roasted -- they taste like "
            "green beans. In dry country, prickly pear is both food and "
            "water. The juice stains everything it touches."
        ),
        teaches_plants=["prickly_pear"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="ramps_foraging",
        keywords=["ramp", "ramps", "wild leek", "wild garlic"],
        label="Ramps and wild leeks",
        category="plants",
        occupations=[],
        response=(
            "Ramps come up in early spring in rich forest soil, before most "
            "other greens. They have broad, smooth leaves and a powerful "
            "garlic-onion smell. Eat the leaves and the small white bulb. "
            "They are the first fresh green of the year and will cure early "
            "scurvy symptoms. Cook them into any stew or eat them raw if you "
            "can stand the bite."
        ),
        teaches_plants=["ramps"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="oyster_mushroom",
        keywords=["oyster mushroom", "shelf mushroom", "tree mushroom"],
        label="Oyster mushrooms",
        category="plants",
        occupations=["Trapper", "Scout", "Farmer"],
        response=(
            "Oyster mushrooms grow in overlapping shelves on dead hardwood "
            "trees and logs, mostly in fall and spring. They are white to "
            "pale gray with a short off-center stem. The edges curl down "
            "when young -- that is when they taste best. Slice and fry them "
            "in grease or add them to stew. They are one of the safest "
            "wild mushrooms to learn because nothing truly dangerous looks "
            "like them."
        ),
        teaches_plants=["oyster_mushroom"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="wild_carrot",
        keywords=["wild carrot", "queen anne", "carrot"],
        label="Wild carrot",
        category="plants",
        occupations=["Trapper", "Scout"],
        response=(
            "Wild carrot -- Queen Anne's lace -- has a white root that "
            "smells and tastes like garden carrot. Dig it in the first year "
            "when the plant is just a low rosette of ferny leaves. By the "
            "second year when it flowers, the root is woody and useless. "
            "WARNING: water hemlock and poison hemlock look very similar. "
            "Always smell the root -- true wild carrot smells like carrot. "
            "If it smells like parsnip or musty, drop it and wash your hands."
        ),
        teaches_plants=["wild_carrot"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="sage_uses",
        keywords=["sage", "wild sage", "sagebrush"],
        label="Wild sage",
        category="plants",
        occupations=[],
        response=(
            "Wild sage grows thick in dry, open country. The leaves make a "
            "strong tea that settles the stomach and clears the head. Burn "
            "dried sage in camp to drive off mosquitoes. It also makes a "
            "fair seasoning for game meat. The woody stems burn hot and fast "
            "for starting fires where other kindling is scarce."
        ),
        teaches_plants=["wild_sage"],
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="thimbleberry",
        keywords=["thimbleberry", "thimbleberries"],
        label="Thimbleberries",
        category="plants",
        occupations=[],
        response=(
            "Thimbleberries have large maple-shaped leaves and soft red "
            "berries that look like flat raspberries. They grow in the "
            "mountains of the Pacific coast and northern Rockies. The "
            "berries are delicate and crush easily, so eat them fresh -- "
            "they do not travel well. The large leaves make good wrapping "
            "for other foraged food."
        ),
        teaches_plants=["thimbleberry"],
        teaches_skill_xp=("survival", 3.0),
    ),

    # =========================================================================
    #  ANIMALS / TRAPPING  (15+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="trap_beaver",
        keywords=["trap beaver", "beaver trap", "beaver trapping", "catch beaver",
                  "set beaver trap"],
        label="How to trap beaver",
        category="animals",
        occupations=["Trapper"],
        response=(
            "Set your steel trap in four inches of water near a beaver "
            "slide -- that is the muddy path where they climb out. Drive a "
            "stout stake through the trap chain ring into deep water so the "
            "beaver drowns quickly. Bait a stick with castoreum and set it "
            "above the trap so the beaver must step on the pan to reach the "
            "scent. Check traps every morning. A good trapper takes no more "
            "than half the beaver from a pond -- leave the rest to breed."
        ),
        teaches_skill_xp=("trapping", 10.0),
    ),

    KnowledgeTopic(
        topic_id="find_beaver",
        keywords=["find beaver", "beaver dam", "beaver sign", "where beaver",
                  "beaver pond", "beaver lodge"],
        label="Where to find beaver",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Follow small to medium streams and look for dams -- piles of "
            "sticks and mud blocking the flow. Chewed aspens and willows "
            "with cone-shaped stumps are sure sign. Look for mud slides on "
            "the banks where they drag branches. The lodge is a dome of "
            "sticks in the pond. Beaver are most active at dusk and dawn. "
            "Fresh wood chips and green-cut branches mean an active colony."
        ),
        teaches_skill_xp=("trapping", 5.0),
    ),

    KnowledgeTopic(
        topic_id="best_bait",
        keywords=["bait", "trap bait", "best bait", "lure", "castoreum", "scent bait"],
        label="Best bait for traps",
        category="animals",
        occupations=["Trapper"],
        response=(
            "For beaver, nothing beats castoreum -- the musk from beaver "
            "glands. Mix it with a little oil and smear it on a stick above "
            "the trap. For marten and fisher, use a chunk of bloody meat or "
            "a fish head in a cubby set. Mink come to fish guts. Wolves and "
            "coyotes come to rotting meat. For rabbit snares, no bait is "
            "needed -- just set them on well-used runs between feeding and "
            "bedding areas."
        ),
        teaches_skill_xp=("trapping", 5.0),
    ),

    KnowledgeTopic(
        topic_id="skin_animal",
        keywords=["skin", "skinning", "skin animal", "butcher", "field dress",
                  "how to skin"],
        label="How to skin an animal",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Use a sharp knife and keep the blade edge facing outward, away "
            "from the pelt. Start with cuts around each leg above the paws, "
            "then slit from paw to paw along the belly. Peel the hide off "
            "by pulling and using the knife only to cut connective tissue. "
            "Work slowly around the head. The less you cut, the fewer holes "
            "in the pelt. Keep meat and fat off the skin -- they cause rot."
        ),
        teaches_skill_xp=("trapping", 5.0),
    ),

    KnowledgeTopic(
        topic_id="stretch_pelt",
        keywords=["stretch pelt", "pelt", "pelts", "dry pelt", "cure pelt",
                  "prepare pelt", "fur"],
        label="How to stretch a pelt",
        category="animals",
        occupations=["Trapper"],
        response=(
            "Stretch the pelt flesh-side-out on a frame or hoop made from "
            "bent willow. Scrape off all fat and membrane with a dull blade "
            "-- a sharp one cuts the skin. Lace it tight to the frame with "
            "rawhide cord. Dry it in the shade, not in sun or by fire, which "
            "makes the leather stiff and brittle. A well-stretched beaver "
            "plew should be round, about two feet across. Grade counts for "
            "everything at rendezvous."
        ),
        teaches_skill_xp=("furriery", 5.0),
    ),

    KnowledgeTopic(
        topic_id="pelt_quality",
        keywords=["pelt quality", "fur quality", "best pelts", "winter fur",
                  "prime fur", "pelt season", "when to trap"],
        label="Pelt quality and seasons",
        category="animals",
        occupations=["Trapper", "Merchant"],
        response=(
            "Winter pelts are prime -- the fur is thick and dense from "
            "November through February. Spring pelts start to shed and lose "
            "value fast. Summer pelts are worthless for trade. Beaver plews "
            "are graded: a full winter prime fetches top dollar, a spring "
            "pelt maybe half. Mink and marten are the same way. Time your "
            "trapping season right and your take is worth three times as much."
        ),
        teaches_skill_xp=("trapping", 5.0),
    ),

    KnowledgeTopic(
        topic_id="dangerous_animals",
        keywords=["dangerous animal", "predator", "wolf", "wolves", "mountain lion",
                  "cougar", "panther", "wild animals"],
        label="Dangerous animals",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Grizzly bears are the worst -- give them space, make noise, and "
            "never get between a sow and her cubs. Wolves rarely attack a "
            "man alone, but a pack will follow you if hungry enough -- keep "
            "a fire burning at night. Mountain lions ambush from above: "
            "watch ledges and overhanging branches. If one stalks you, face "
            "it, make yourself big, and do not turn your back. Rattlesnakes "
            "warn with their rattle -- freeze, find it, back away."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="track_game",
        keywords=["track", "tracking", "tracks", "game trail", "animal sign",
                  "scat", "follow tracks"],
        label="How to track game",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Fresh tracks have sharp edges; old ones are rounded by wind and "
            "rain. Deer tracks are pointed hearts; elk are larger and rounder. "
            "Look for disturbed leaves, broken twigs at body height, and "
            "fresh scat. Game trails funnel toward water at dawn and dusk. "
            "Rubs on trees mean deer or elk marking territory. In snow, "
            "tracking is easy -- follow the freshest prints. Check the track "
            "depth to judge the animal's size and speed."
        ),
        teaches_skill_xp=("tracking", 8.0),
    ),

    KnowledgeTopic(
        topic_id="elk_hunting",
        keywords=["elk", "elk hunting", "hunt elk", "wapiti"],
        label="Elk hunting",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Elk feed in high meadows at dawn and dusk, then bed down in "
            "thick timber during the day. In fall, bulls bugle to challenge "
            "rivals -- follow the sound. Approach from downwind always. Set "
            "up an ambush on a game trail between bedding and feeding areas. "
            "Aim behind the front shoulder for the lungs. An elk is big -- "
            "bring a pack animal or be ready to butcher and cache meat on "
            "site."
        ),
        teaches_skill_xp=("tracking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="buffalo_hunting",
        keywords=["buffalo", "bison", "hunt buffalo", "buffalo hunt"],
        label="Buffalo hunting",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Buffalo have poor eyesight but a keen nose -- always approach "
            "from downwind. They graze in herds on open prairie. A stand "
            "hunt works best: shoot the lead cow first and the herd often "
            "mills in confusion, letting you take several. Aim just behind "
            "the shoulder, angling forward. A buffalo is twice an elk's "
            "weight -- you need pack animals to haul the meat and hide. "
            "The tongue and hump are the best eating."
        ),
        teaches_skill_xp=("tracking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="set_snares",
        keywords=["snare", "snares", "rabbit snare", "set snare", "wire trap",
                  "loop trap"],
        label="How to set snares",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "A snare is a loop of wire or strong cord set on a game trail "
            "at head height for your target animal. For rabbits, set the "
            "loop four fingers wide and three fingers above the ground on a "
            "well-used run between brush and feeding areas. Anchor it to a "
            "stout stake or springy sapling. Use natural funnels -- gaps in "
            "brush or between rocks -- so the animal has to pass through "
            "your loop. Check snares twice daily."
        ),
        teaches_skill_xp=("trapping", 8.0),
    ),

    KnowledgeTopic(
        topic_id="fish_methods",
        keywords=["fish", "fishing", "catch fish", "how to fish", "trout",
                  "angling"],
        label="How to catch fish",
        category="animals",
        occupations=[],
        response=(
            "Trout lie in pools behind rocks where the current brings food "
            "to them. Use a hook baited with grasshoppers, worms, or grubs. "
            "No hook? Carve a gorge from bone -- a straight piece sharpened "
            "on both ends that catches crosswise in the fish's throat. You "
            "can also weave a basket trap and set it in a stream narrowing. "
            "In winter, chop a hole in the ice and jig a small bright lure."
        ),
        teaches_skill_xp=("fishing", 5.0),
    ),

    KnowledgeTopic(
        topic_id="deer_hunting",
        keywords=["deer", "deer hunting", "hunt deer", "venison",
                  "whitetail", "mule deer"],
        label="Deer hunting",
        category="animals",
        occupations=["Trapper", "Scout"],
        response=(
            "Deer feed at dawn and dusk in clearings near cover. Find their "
            "trails between bedding thickets and feeding areas. Set up "
            "downwind and wait. Move slow -- deer see movement before "
            "anything else. A whistle or grunt can freeze a moving deer for "
            "a clean shot. Aim just behind the front leg. Field dress "
            "immediately: cut the belly open, remove the guts, and prop the "
            "cavity open to cool the meat."
        ),
        teaches_skill_xp=("tracking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="trap_types",
        keywords=["trap types", "kinds of trap", "steel trap", "deadfall",
                  "leg hold", "what trap"],
        label="Types of traps",
        category="animals",
        occupations=["Trapper"],
        response=(
            "Steel leg-hold traps are the standard for beaver, mink, and "
            "marten -- set them in water when possible so the animal drowns "
            "quickly. Deadfalls use a heavy log triggered by a bait stick: "
            "good for marten and fisher in timber country. Cubby sets funnel "
            "the animal into a box-like enclosure where it steps on the trap "
            "pan. Snares are the simplest -- a loop of wire on a trail. Each "
            "fur animal has a set that works best for it."
        ),
        teaches_skill_xp=("trapping", 5.0),
    ),

    # =========================================================================
    #  CRAFTING  (10+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="tan_hide",
        keywords=["tan", "tanning", "tan hide", "brain tan", "hide tanning",
                  "cure hide"],
        label="How to tan a hide",
        category="crafting",
        occupations=["Trapper"],
        response=(
            "Scrape all flesh and fat from the hide while it is fresh. Mash "
            "the animal's brain with warm water into a paste -- every animal "
            "has enough brain to tan its own hide. Work the brain mixture "
            "into the skin, fold it up, and let it soak overnight. Next day, "
            "wring it out and stretch and pull the hide as it dries until "
            "it stays soft. Finally, smoke it over a smoldering fire of "
            "punky wood to waterproof it. Smoked buckskin stays soft even "
            "after getting wet."
        ),
        teaches_skill_xp=("furriery", 8.0),
    ),

    KnowledgeTopic(
        topic_id="make_leather",
        keywords=["leather", "make leather", "rawhide", "leather working"],
        label="How to make leather",
        category="crafting",
        occupations=["Trapper", "Blacksmith"],
        response=(
            "Raw hide becomes rawhide by stretching and drying -- it is "
            "stiff and hard, good for parfleche containers, snowshoe lacing, "
            "and mending. For soft leather, you need to tan it: brain "
            "tanning for buckskin, or bark tanning for heavier leather. "
            "Soak the hide in a solution of oak or hemlock bark for weeks, "
            "turning it daily. Bark-tanned leather is stiffer but more "
            "water-resistant than brain-tanned buckskin."
        ),
        teaches_skill_xp=("furriery", 5.0),
    ),

    KnowledgeTopic(
        topic_id="make_moccasins",
        keywords=["moccasin", "moccasins", "make moccasins", "shoe", "footwear"],
        label="How to make moccasins",
        category="crafting",
        occupations=["Trapper"],
        response=(
            "Use brain-tanned buckskin. Stand on the leather, trace your "
            "foot with a finger's width of margin, and cut the sole piece. "
            "Cut a second piece for the upper. Punch holes with an awl and "
            "stitch with sinew -- it swells when wet and seals the holes. "
            "For rough country, add a second sole of thicker rawhide. "
            "Moccasins wear out fast on rocks, so carry spare soles. They "
            "are quieter than boots for stalking game."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="make_arrows",
        keywords=["arrow", "arrows", "make arrows", "fletch", "arrowhead",
                  "bow and arrow"],
        label="How to make arrows",
        category="crafting",
        occupations=["Trapper", "Scout"],
        response=(
            "Find straight shoots of dogwood, willow, or serviceberry, about "
            "as thick as your little finger. Scrape off bark and straighten "
            "them over a fire, bending gently. Attach a stone or iron point "
            "with sinew wrapping and pine pitch glue. For fletching, split "
            "turkey or hawk feathers lengthwise, cut them to three inches, "
            "and bind three vanes evenly spaced around the shaft with fine "
            "sinew. A good arrow flies true to forty yards."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="repair_tools",
        keywords=["repair", "fix tool", "repair tool", "sharpen", "broken handle",
                  "maintenance"],
        label="How to repair tools",
        category="crafting",
        occupations=["Blacksmith"],
        response=(
            "Keep your knife sharp with a whetstone -- a dull blade is "
            "dangerous because you force it and it slips. Sharpen axes with "
            "a file, then finish with a stone. A cracked axe handle can be "
            "replaced: split a green hickory or ash billet, shape it with "
            "a knife, and wedge it tight into the head. Rub linseed oil "
            "into wooden handles to prevent drying and cracking. Treat "
            "your tools well and they will last years."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="make_rope",
        keywords=["rope", "cordage", "make rope", "string", "twine", "cord"],
        label="How to make rope",
        category="crafting",
        occupations=[],
        response=(
            "Strong cord can be made from plant fibers: inner bark of "
            "basswood or elm, stinging nettle stalks, or yucca leaves. "
            "Strip the fibers, let them dry slightly, then twist two "
            "bundles in the same direction while wrapping them around each "
            "other in the opposite direction -- this is called a reverse "
            "twist and it locks the fibers together. Rawhide cut in a "
            "spiral from a round piece of hide also makes serviceable rope."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="make_canoe",
        keywords=["canoe", "make canoe", "birch bark canoe", "boat", "build boat"],
        label="How to make a canoe",
        category="crafting",
        occupations=["Trapper", "Scout"],
        response=(
            "A bull boat is the simplest: bend willow saplings into a round "
            "frame and stretch a fresh buffalo hide over it, hair side out. "
            "Let it dry tight on the frame. It is ugly but floats gear "
            "across rivers. A proper bark canoe takes weeks: build a cedar "
            "frame, sew birch bark sheets together with spruce root, and "
            "seal every seam with heated spruce pitch. Best left to someone "
            "who has built one before."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="make_snowshoes",
        keywords=["snowshoe", "snowshoes", "make snowshoes", "walk on snow",
                  "deep snow"],
        label="How to make snowshoes",
        category="crafting",
        occupations=["Trapper", "Scout"],
        response=(
            "Bend a green ash or birch sapling into a teardrop frame, about "
            "three feet long and a foot wide, and lash the ends together. "
            "Weave a mesh of rawhide strips across the frame in a tight "
            "pattern, leaving a slot for your toe. Bind your moccasin or "
            "boot to the frame with rawhide thongs so your heel lifts free. "
            "Without snowshoes, you sink to your waist in deep powder and "
            "cannot travel at all."
        ),
        teaches_skill_xp=("survival", 5.0),
    ),

    KnowledgeTopic(
        topic_id="smoking_meat",
        keywords=["smoke meat", "smoking", "preserve meat", "jerky", "dry meat",
                  "cure meat"],
        label="How to smoke and dry meat",
        category="crafting",
        occupations=[],
        response=(
            "Cut meat into thin strips no thicker than your little finger. "
            "Build a rack of green sticks over a low, smoky fire -- use "
            "hardwood or willow, never pine, which gives a bitter resin "
            "taste. Dry the strips until they are hard and brittle, turning "
            "them as needed. This takes a full day at least. Well-dried "
            "jerky keeps for months. Store it in a dry bag away from "
            "moisture and it will sustain you through lean times."
        ),
        teaches_skill_xp=("cooking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="make_charcoal",
        keywords=["charcoal", "make charcoal", "forge fuel"],
        label="How to make charcoal",
        category="crafting",
        occupations=["Blacksmith"],
        response=(
            "Stack hardwood in a tight pile and cover it with earth, leaving "
            "a small draft hole at the base and a vent at the top. Light it "
            "from the bottom and let it burn slowly for two days, adjusting "
            "the vents to keep it smoldering, not flaming. When the smoke "
            "turns thin and blue, seal the vents and let it cool completely. "
            "Good charcoal burns hotter than raw wood and is essential for "
            "forge work and smelting."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    # =========================================================================
    #  MINING / PROSPECTING  (10+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="pan_for_gold",
        keywords=["pan", "panning", "pan gold", "gold pan", "how to pan",
                  "wash gold"],
        label="How to pan for gold",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Fill your pan with gravel from a likely spot and submerge it "
            "in water. Break up clay lumps with your fingers. Shake the pan "
            "side to side to settle heavy material, then tilt it and wash "
            "lighter sand over the rim with a gentle circular motion. Keep "
            "working until only heavy black sand and gold remain in the "
            "crease. Pick out the flakes with a wet fingertip. The gold "
            "always sinks to the bottom -- be patient and do not rush the "
            "wash or you will lose fine gold over the rim."
        ),
        teaches_skill_xp=("placer", 8.0),
    ),

    KnowledgeTopic(
        topic_id="placer_gold",
        keywords=["placer", "placer gold", "alluvial", "stream gold",
                  "creek gold", "placer deposit"],
        label="What is placer gold",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Placer gold is free gold that has eroded out of hard rock veins "
            "and been carried by water. It settles wherever the current "
            "slows: inside bends of streams, behind large boulders, in "
            "bedrock cracks, and where tributaries join a main creek. The "
            "heavier the gold, the less distance it travels -- nuggets are "
            "found close to the source. Fine flour gold can travel miles. "
            "To find the mother lode, work upstream, panning as you go, "
            "until the gold runs out."
        ),
        teaches_skill_xp=("placer", 5.0),
    ),

    KnowledgeTopic(
        topic_id="read_geology",
        keywords=["geology", "rock", "quartz", "read geology", "iron staining",
                  "black sand", "mineral", "vein"],
        label="How to read geology",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Gold loves quartz. Look for white quartz veins in exposed rock "
            "faces, especially where they are stained rusty red or orange "
            "from iron oxide -- that means the rock has been mineralized. "
            "Black sand in your pan is magnetite and indicates heavy mineral "
            "concentration; where you find black sand, gold often follows. "
            "Contact zones where two different rock types meet are promising. "
            "Granite intruding into older slate or schist is a classic gold "
            "setting."
        ),
        teaches_skill_xp=("geology", 8.0),
    ),

    KnowledgeTopic(
        topic_id="where_gold",
        keywords=["where gold", "find gold", "gold location", "best spot",
                  "where to dig", "gold deposit"],
        label="Where to find gold",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "In a stream, work the inside of bends where the current slows "
            "and drops heavy material. Check behind large boulders that "
            "create eddies. Dig into bedrock crevices -- gold works its way "
            "down into cracks over centuries. Gravel bars at the confluence "
            "of two creeks are always worth panning. On dry ground, look for "
            "old stream channels above the current water level -- ancient "
            "rivers left gold deposits on benches and terraces."
        ),
        teaches_skill_xp=("placer", 5.0),
    ),

    KnowledgeTopic(
        topic_id="build_sluice",
        keywords=["sluice", "build sluice", "sluice box", "long tom",
                  "make sluice"],
        label="How to build a sluice",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Build a wooden trough about ten feet long and a foot wide with "
            "sides six inches high. Set riffles across the bottom -- cross "
            "bars or slats spaced a few inches apart. Place burlap or "
            "wool blanket under the riffles to catch fine gold. Set the "
            "sluice in the stream at a gentle angle so water flows through "
            "steadily. Shovel gravel in at the top and the water does the "
            "work -- heavy gold catches behind the riffles while waste "
            "washes out the end. Clean up the riffles and blanket twice daily."
        ),
        teaches_skill_xp=("placer", 8.0),
    ),

    KnowledgeTopic(
        topic_id="assay_ore",
        keywords=["assay", "assaying", "test ore", "ore quality", "ore value",
                  "gold content"],
        label="How to assay ore",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "A proper assay requires a furnace, crucible, and lead flux -- "
            "take a sample to an assay office in town. For field testing, "
            "crush your rock and pan the dust: visible gold in panned "
            "concentrates means the ore is worth pursuing. Streak testing "
            "helps too -- scratch gold on a dark stone; real gold leaves a "
            "yellow streak, while pyrite leaves black or greenish. An assayer "
            "will give you dollars-per-ton, and anything over $20 per ton is "
            "worth working in 1850s money."
        ),
        teaches_skill_xp=("assaying", 8.0),
    ),

    KnowledgeTopic(
        topic_id="hard_rock_mining",
        keywords=["hard rock", "hardrock", "tunnel", "shaft", "mine tunnel",
                  "dig mine", "underground"],
        label="Hard rock mining",
        category="mining",
        occupations=["Miner"],
        response=(
            "Follow the quartz vein into the hillside. Timber your tunnel "
            "as you go -- never work under unsupported rock. Set posts and "
            "a cap beam every four feet. Drill blast holes with a hand "
            "steel and sledge, pack them with black powder, and clear the "
            "tunnel before you light the fuse. Ventilation is critical: "
            "smoke and bad air kill more miners than cave-ins. Always work "
            "with a partner and tell someone on the surface where you are."
        ),
        teaches_skill_xp=("hardRock", 8.0),
    ),

    KnowledgeTopic(
        topic_id="claim_staking",
        keywords=["claim", "stake claim", "mining claim", "file claim",
                  "claim right", "claim law"],
        label="How to stake a claim",
        category="mining",
        occupations=["Prospector", "Miner", "Lawyer"],
        response=(
            "Under the mining district rules, mark your claim boundaries "
            "with corner stakes or rock cairns. Post a notice with your "
            "name, the date, and the dimensions of the claim at the "
            "discovery point. Record the claim at the nearest recorder's "
            "office or mining district book. You must work the claim "
            "regularly -- most districts require a certain number of days "
            "per season or the claim is considered abandoned and open to "
            "relocation by anyone."
        ),
        teaches_skill_xp=("law", 5.0),
    ),

    KnowledgeTopic(
        topic_id="gold_nuggets",
        keywords=["nugget", "nuggets", "big gold", "large gold", "specimen"],
        label="Finding nuggets",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Nuggets are found close to the source vein because they are "
            "too heavy to travel far in water. Dig deep into bedrock "
            "crevices and clean out every crack with a spoon or knife. "
            "Check behind large boulders in the streambed and under "
            "waterfalls. Old river benches above the current stream level "
            "sometimes hold nuggets from ancient placer deposits. Coarse "
            "gold and small nuggets in your pan mean bigger ones may be "
            "close by -- work the area thoroughly."
        ),
        teaches_skill_xp=("placer", 5.0),
    ),

    KnowledgeTopic(
        topic_id="pyrite_vs_gold",
        keywords=["pyrite", "fool's gold", "fools gold", "is this gold",
                  "fake gold", "iron pyrite"],
        label="Pyrite vs real gold",
        category="mining",
        occupations=["Prospector", "Miner"],
        response=(
            "Pyrite -- fool's gold -- is brassy yellow and forms sharp "
            "crystals. Real gold is deeper yellow, soft, and malleable. "
            "Hit it with a hammer: gold flattens, pyrite shatters. Scratch "
            "it on a dark stone: gold leaves a yellow streak, pyrite leaves "
            "black or greenish. Gold is much heavier -- it sinks fast in "
            "your pan while pyrite washes out with the lighter material. "
            "If it is still in the pan after a thorough wash, it is real."
        ),
        teaches_skill_xp=("geology", 5.0),
    ),

    # =========================================================================
    #  TRADING  (8+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="pelt_prices",
        keywords=["pelt worth", "fur price", "pelt price", "what pelts worth",
                  "fur value", "beaver price", "sell pelts"],
        label="What are pelts worth",
        category="trading",
        occupations=["Trapper", "Merchant"],
        response=(
            "A prime winter beaver plew fetches four to six dollars -- less "
            "if it is poorly stretched or off-season. Mink and marten run "
            "two to four dollars for prime. Otter is valuable, five dollars "
            "or more for a good one. Buffalo robes bring three to five "
            "dollars each. Prices change with the market back East and how "
            "many furs are coming in that season. Trading posts charge a "
            "heavy markup -- you get better prices at rendezvous or in town."
        ),
        teaches_skill_xp=("trading", 5.0),
    ),

    KnowledgeTopic(
        topic_id="where_trade",
        keywords=["where trade", "trading post", "sell goods", "buy supplies",
                  "nearest store", "nearest town", "merchant"],
        label="Where can I trade",
        category="trading",
        occupations=["Merchant", "Freighter"],
        response=(
            "Trading posts are scattered along the main trails and rivers. "
            "Towns have general stores with better selection and fairer "
            "prices. Rendezvous in summer is where trappers sell their year's "
            "catch and buy supplies for the next season. Army forts sometimes "
            "have sutlers who trade. In a pinch, any camp of trappers or "
            "emigrants will swap goods. Prices go up the further you get "
            "from supply routes."
        ),
        teaches_skill_xp=("trading", 3.0),
    ),

    KnowledgeTopic(
        topic_id="haggle_tips",
        keywords=["haggle", "haggling", "bargain", "negotiate", "better price",
                  "trade tips", "deal"],
        label="How to haggle",
        category="trading",
        occupations=["Merchant"],
        response=(
            "Know what your goods are worth before you start talking price. "
            "Let the other man name his price first. Act like you do not "
            "need the deal -- a desperate man gets poor terms. Bundle items "
            "together: a man who will not budge on one thing may throw in "
            "extras to close the deal. Trading skill improves with practice. "
            "Your reputation matters too -- a known cheat gets worse prices "
            "from everyone."
        ),
        teaches_skill_xp=("trading", 5.0),
    ),

    KnowledgeTopic(
        topic_id="indian_trade",
        keywords=["indian trade", "native trade", "trade with indians",
                  "tribal trade", "trade goods"],
        label="Trading with Indians",
        category="trading",
        occupations=["Trapper", "Scout", "Merchant"],
        response=(
            "Gift-giving comes before trading -- it is a sign of respect. "
            "Tobacco, blankets, knives, and metal tools are valued trade "
            "goods. Beads and vermillion paint are prized. Never cheat on "
            "a trade: word travels fast between bands and a dishonest trader "
            "will find every camp closed to him. Learn a few words of the "
            "local tongue or use sign language. Different tribes have "
            "different customs -- ask someone who knows the local people "
            "before you approach."
        ),
        teaches_skill_xp=("trading", 5.0),
        requires_friendly=True,
    ),

    KnowledgeTopic(
        topic_id="supply_prices",
        keywords=["prices", "cost", "how much", "expensive", "supply cost",
                  "flour price", "coffee price"],
        label="Current supply prices",
        category="trading",
        occupations=["Merchant"],
        response=(
            "Prices in the gold fields run high because everything is "
            "freighted in. Expect to pay a dollar a pound for flour in "
            "the diggings, twice what it costs in Sacramento. Coffee and "
            "sugar run fifty cents a pound or more. A good pair of boots "
            "is ten dollars. Ammunition is dear -- a dollar for a box of "
            "caps and ball. The further from a supply town, the worse the "
            "prices. Buy in bulk when you can and cache supplies."
        ),
        teaches_skill_xp=("trading", 3.0),
    ),

    KnowledgeTopic(
        topic_id="gold_value",
        keywords=["gold value", "gold price", "gold worth", "sell gold",
                  "ounce gold", "dust value"],
        label="What is gold worth",
        category="trading",
        occupations=["Prospector", "Miner", "Merchant"],
        response=(
            "The official mint price is about $20.67 per troy ounce for "
            "pure gold. Dust and flakes sell for less because they contain "
            "impurities -- figure $16 to $18 an ounce at most buying "
            "offices. Nuggets sometimes fetch a premium from collectors. "
            "A pinch of gold dust between thumb and finger is roughly a "
            "dollar. Many merchants in the diggings weigh gold on their own "
            "scales, and those scales often favor the merchant. Carry your "
            "own scale if you can."
        ),
        teaches_skill_xp=("trading", 3.0),
    ),

    KnowledgeTopic(
        topic_id="freight_business",
        keywords=["freight", "freighting", "haul goods", "pack train",
                  "supply run", "teamster"],
        label="The freighting business",
        category="trading",
        occupations=["Freighter", "Merchant"],
        response=(
            "Hauling supplies to remote camps pays well -- a mule train can "
            "earn more than a good claim. Pack mules carry about 200 pounds "
            "each over mountain trails. Ox-drawn wagons haul more on flat "
            "roads but cannot handle steep passes. Buy goods cheap in town "
            "and sell at markup in the camps. The trick is knowing what men "
            "need most: flour, coffee, tobacco, nails, and ammunition are "
            "always in demand."
        ),
        teaches_skill_xp=("trading", 5.0),
    ),

    KnowledgeTopic(
        topic_id="barter_system",
        keywords=["barter", "swap", "exchange", "trade goods for goods",
                  "no cash", "no money"],
        label="Bartering without cash",
        category="trading",
        occupations=[],
        response=(
            "In the back country, cash is scarce and barter is common. "
            "Gold dust serves as currency almost everywhere. Ammunition, "
            "tobacco, coffee, and whiskey are good as money. Pelts have "
            "a known value and trade easily. Offer something the other "
            "man needs but cannot get easily -- a fresh-killed deer to a "
            "miner is worth more than its weight in flour. Fair dealing "
            "builds your reputation and makes future trades easier."
        ),
        teaches_skill_xp=("trading", 3.0),
    ),

    # =========================================================================
    #  COMBAT  (5+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="fight_basics",
        keywords=["fight", "fighting", "combat", "how to fight", "self defense",
                  "defend"],
        label="How to fight",
        category="combat",
        occupations=["Scout", "Drifter"],
        response=(
            "Use cover -- never stand in the open when someone is shooting "
            "at you. Trees, rocks, and wagons stop bullets. Crouch or go "
            "prone to make yourself a smaller target. Aimed shots take time "
            "but hit where they need to. Panic fire wastes ammunition. In "
            "a scrap, keep moving between cover and do not let the enemy "
            "flank you. Fighting from higher ground gives you the advantage."
        ),
        teaches_skill_xp=("firearms", 5.0),
    ),

    KnowledgeTopic(
        topic_id="reload_faster",
        keywords=["reload", "loading", "reload faster", "muzzleloader",
                  "charge", "ram rod", "load gun"],
        label="How to reload faster",
        category="combat",
        occupations=["Scout", "Drifter"],
        response=(
            "Practice the steps until they are habit: half-cock, pour powder "
            "from a measured charge, seat the ball with a patch, ram it firm "
            "but not too tight, prime the pan or set the cap. Pre-cut your "
            "patches and pre-measure your charges into paper cartridges for "
            "speed. Keep your ramrod where you can grab it fast. A good man "
            "can fire three aimed shots a minute with a rifle. In a fight, "
            "slow is smooth and smooth is fast."
        ),
        teaches_skill_xp=("firearms", 5.0),
    ),

    KnowledgeTopic(
        topic_id="knife_fighting",
        keywords=["knife fight", "knife", "close combat", "blade", "bowie",
                  "knife fighting"],
        label="Knife fighting",
        category="combat",
        occupations=["Scout", "Drifter", "Trapper"],
        response=(
            "A knife fight is ugly business -- avoid it if you can. Keep "
            "your blade between you and the other man. Use your free arm to "
            "guard and deflect. Slash at the forearm and wrist -- a man "
            "cannot hold a weapon with cut tendons. Stay on the balls of "
            "your feet and keep moving. If you must close, go for the belly "
            "or the side. A heavy Bowie knife can chop as well as stab. "
            "Better to avoid the fight entirely if you have any way out."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="ambush_tactics",
        keywords=["ambush", "surprise attack", "outlaw attack", "bushwhack",
                  "avoid ambush"],
        label="Avoiding ambushes",
        category="combat",
        occupations=["Scout"],
        response=(
            "Travel unpredictably -- do not use the same trail at the same "
            "time every day. Watch for places where the trail narrows between "
            "rocks or thick brush: those are natural ambush sites. If your "
            "horse or mule acts nervous, trust the animal. Keep your rifle "
            "loaded and accessible, not buried in your pack. Travel with a "
            "partner when possible. If you suspect trouble, swing wide around "
            "the danger point even if it costs you time."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="gunfight_advice",
        keywords=["gunfight", "shootout", "duel", "pistol fight", "shooting"],
        label="Surviving a gunfight",
        category="combat",
        occupations=["Scout", "Drifter"],
        response=(
            "The first rule is do not get in one. The second rule is shoot "
            "first if you have to. Take cover immediately -- do not stand "
            "and trade shots like a fool. Aim for center mass, not the head. "
            "At close range a shotgun is the most devastating weapon there "
            "is. After firing, move -- do not stay in the spot where the "
            "enemy saw your muzzle flash. Reload behind cover. Most fights "
            "are decided in the first few seconds."
        ),
        teaches_skill_xp=("firearms", 5.0),
    ),

    # =========================================================================
    #  LOCAL / REGIONAL  (5+ topics)
    # =========================================================================

    KnowledgeTopic(
        topic_id="area_description",
        keywords=["this area", "around here", "this region", "local area",
                  "what's here", "terrain", "land here"],
        label="What's in this area",
        category="local",
        occupations=[],
        response=(
            "This country has its own character. Look at the trees and the "
            "rock to understand what you are working with. Streams with "
            "gravel bars are worth panning. Pine forests have game and "
            "forage. Open prairie means buffalo and pronghorn but little "
            "cover. High meadows are good summer range but deadly in winter. "
            "Talk to the locals about specific conditions -- every drainage "
            "is different."
        ),
    ),

    KnowledgeTopic(
        topic_id="danger_nearby",
        keywords=["danger", "warning", "threats", "hostile", "bandits",
                  "outlaws", "trouble", "safe"],
        label="Any danger nearby",
        category="local",
        occupations=[],
        response=(
            "Keep your wits about you. Road agents work the main trails, "
            "especially near the diggings where men carry gold. Some tribal "
            "bands are unfriendly to prospectors on their land. Grizzlies "
            "are common in the mountain drainages. Flash floods in narrow "
            "canyons kill men every season. Ask around before heading into "
            "unfamiliar territory -- the men who have been there know "
            "what to watch for."
        ),
    ),

    KnowledgeTopic(
        topic_id="nearest_town_info",
        keywords=["nearest town", "closest town", "settlement", "nearest store",
                  "supply town", "civilization"],
        label="Where's the nearest town",
        category="local",
        occupations=[],
        response=(
            "Depends on where we are standing. Most mining districts have "
            "a camp or settlement within a few days' walk. Follow the main "
            "streams downhill to find trails, and trails lead to camps. "
            "A column of smoke on the horizon usually means people. Look "
            "for wagon ruts, blazed trees, and mule trails. If you see "
            "freight wagons, follow their tracks -- they always lead to a "
            "supply point."
        ),
    ),

    KnowledgeTopic(
        topic_id="weather_reading",
        keywords=["weather", "forecast", "rain coming", "storm coming",
                  "weather sign", "weather predict"],
        label="Reading the weather",
        category="local",
        occupations=[],
        response=(
            "A ring around the moon means rain or snow within a day. Clouds "
            "building up on the peaks in the afternoon mean thunderstorms by "
            "evening. When the wind shifts to the south or southwest, "
            "warm wet weather follows. If campfire smoke rises straight, "
            "the weather holds; if it curls down, a storm is coming. "
            "Animals feeding heavily and birds flying low are signs of "
            "approaching bad weather. In the mountains, weather changes "
            "fast -- always carry shelter."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="trail_conditions",
        keywords=["trail", "road", "pass", "route", "path", "travel route",
                  "way through"],
        label="Trail conditions",
        category="local",
        occupations=["Scout", "Freighter"],
        response=(
            "Mountain passes close with the first heavy snow, usually by "
            "November, and do not open until May or June. River crossings "
            "are most dangerous during spring snowmelt when the water is "
            "high and cold and fast. Summer trails are generally passable "
            "but watch for washouts after heavy rain. Pack trails that "
            "follow ridgelines are drier but more exposed to lightning. "
            "Valley routes are easier but may be boggy in wet weather."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    # =========================================================================
    #  LEGAL  (topics about mining law, frontier justice, etc.)
    # =========================================================================

    KnowledgeTopic(
        topic_id="mining_law",
        keywords=["mining law", "claim law", "legal", "right to mine",
                  "mining rules", "district rules"],
        label="Mining district laws",
        category="legal",
        occupations=["Lawyer", "Prospector", "Miner"],
        response=(
            "Each mining district sets its own rules. Typically a claim is "
            "limited in size -- often 100 feet along the stream for placer, "
            "or a set footage along a vein for lode. You must post a notice "
            "of discovery and record it. Most districts require you to work "
            "the claim a minimum number of days per season or forfeit it. "
            "Disputes go before the district miners' court. Know your "
            "district's rules before you dig."
        ),
        teaches_skill_xp=("law", 5.0),
    ),

    KnowledgeTopic(
        topic_id="water_rights",
        keywords=["water right", "water rights", "divert water", "ditch",
                  "water claim"],
        label="Water rights",
        category="legal",
        occupations=["Lawyer", "Prospector", "Miner"],
        response=(
            "Water is essential for placer mining and the man who controls "
            "the water controls the diggings. Prior appropriation rules "
            "apply: first to use the water has the senior right. You can "
            "dig ditches to bring water to your claim, but you cannot "
            "divert water away from a senior claimant. Water rights can be "
            "bought and sold. In dry country, a water right is sometimes "
            "worth more than the claim itself."
        ),
        teaches_skill_xp=("law", 5.0),
    ),

    KnowledgeTopic(
        topic_id="frontier_justice",
        keywords=["justice", "law enforcement", "sheriff", "vigilante",
                  "crime", "punishment", "hang"],
        label="Frontier justice",
        category="legal",
        occupations=["Lawyer", "Preacher"],
        response=(
            "Where there is no judge or sheriff, miners form their own "
            "courts. Theft of gold or supplies is taken very seriously -- "
            "punishment ranges from banishment to hanging. Killing in self-"
            "defense is generally accepted if witnesses back your account. "
            "Vigilance committees spring up when crime gets bad. Stay on "
            "the right side of the community and keep witnesses to your "
            "dealings. A good reputation is your best legal protection."
        ),
        teaches_skill_xp=("law", 3.0),
    ),

    # =========================================================================
    #  ADDITIONAL MISCELLANEOUS TOPICS
    # =========================================================================

    KnowledgeTopic(
        topic_id="pack_animals_care",
        keywords=["mule", "horse", "pack animal", "animal care", "feed horse",
                  "feed mule", "donkey", "burro"],
        label="Caring for pack animals",
        category="survival",
        occupations=["Freighter", "Scout"],
        response=(
            "A mule eats less than a horse and is surer of foot on rough "
            "trails, but a horse is faster on good ground. Never load more "
            "than a third of the animal's weight. Check hooves daily and "
            "pick out stones. Water them at every stream but do not let them "
            "drink too much when overheated. Let them graze when possible "
            "and supplement with grain in poor country. A lame or starved "
            "pack animal is worse than none -- you end up carrying its load."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="first_aid_basics",
        keywords=["first aid", "wound care", "bandage", "bleeding", "injury",
                  "hurt", "broken bone"],
        label="Basic first aid",
        category="survival",
        occupations=["Doctor"],
        response=(
            "For bleeding: press a clean cloth hard on the wound and hold "
            "it. If blood soaks through, add more cloth on top, do not "
            "remove the first layer. Elevate the wound above the heart if "
            "possible. For a broken bone: splint it with straight sticks "
            "padded with cloth, tied firmly but not so tight it stops "
            "circulation. Keep wounds clean -- wash with boiled water. "
            "Yarrow packed on a wound slows bleeding. Get to a doctor for "
            "anything deep or internal."
        ),
        teaches_skill_xp=("firstAid", 8.0),
    ),

    KnowledgeTopic(
        topic_id="cooking_camp",
        keywords=["cook", "cooking", "campfire cooking", "camp food", "recipe",
                  "stew", "bake"],
        label="Camp cooking",
        category="survival",
        occupations=[],
        response=(
            "Build a good bed of coals, not a roaring fire -- flames char "
            "the outside and leave the inside raw. A flat rock next to the "
            "fire makes a griddle for flapjacks. Stew is the easiest trail "
            "meal: cut meat and whatever vegetables or roots you have into "
            "a pot with water and boil it slow for hours. Bannock bread is "
            "just flour, water, a pinch of salt, and a little grease, "
            "cooked on a stick or in a pan. Season game meat with wild sage "
            "or onion to cut the strong taste."
        ),
        teaches_skill_xp=("cooking", 5.0),
    ),

    KnowledgeTopic(
        topic_id="horse_riding",
        keywords=["ride", "riding", "horseback", "horse riding", "saddle"],
        label="Horseback riding tips",
        category="survival",
        occupations=["Scout", "Rancher"],
        response=(
            "Keep your heels down and your weight in the stirrups. Sit up "
            "straight -- leaning forward throws the horse off balance. Use "
            "your legs more than the reins to guide the horse. Never tie "
            "the reins to the saddle horn while riding. On steep downhill, "
            "lean back and give the horse its head to pick the footing. "
            "Cool down a hot horse gradually: walk it until it stops "
            "breathing hard before you unsaddle and water it."
        ),
        teaches_skill_xp=("survival", 3.0),
    ),

    KnowledgeTopic(
        topic_id="tobacco_uses",
        keywords=["tobacco", "smoke", "chew", "pipe"],
        label="Tobacco as trade and medicine",
        category="trading",
        occupations=[],
        response=(
            "Tobacco is currency on the frontier -- it trades as readily "
            "as gold dust. A plug of tobacco soothes the nerves on a hard "
            "trail. Wet tobacco pressed on a bee sting or insect bite draws "
            "out the pain. Tobacco smoke blown into the ear was the old "
            "remedy for earache. For trade with Indians, tobacco is always "
            "welcome and is part of proper protocol before any parley."
        ),
        teaches_skill_xp=("trading", 3.0),
    ),

    KnowledgeTopic(
        topic_id="gambling_advice",
        keywords=["gamble", "gambling", "cards", "poker", "faro", "dice",
                  "monte", "bet"],
        label="Gambling advice",
        category="local",
        occupations=["Gambler", "Saloon Keeper"],
        response=(
            "Most games in camp saloons favor the house. Faro is the most "
            "popular but the dealer sets the odds. Poker is the fairest "
            "game if you are at a straight table -- but watch for marked "
            "cards and cold decks. Never gamble more than you can afford to "
            "lose, and never gamble drunk. Accusations of cheating start "
            "gunfights. If you must play, start small and watch the table "
            "for a few hands before you sit in."
        ),
    ),

    KnowledgeTopic(
        topic_id="religion_frontier",
        keywords=["church", "god", "pray", "religion", "bible", "preacher",
                  "sermon", "faith"],
        label="Religion on the frontier",
        category="local",
        occupations=["Preacher"],
        response=(
            "Sunday services happen wherever a preacher can gather folks -- "
            "under a tree, in a tent, or at a saloon table. Circuit riders "
            "travel between camps. Most men out here carry a Bible even if "
            "they do not read it regular. A preacher can help with marriages, "
            "funerals, settling disputes, and just keeping morale up. Pray "
            "if it gives you comfort -- the Lord knows this is hard country."
        ),
    ),

    KnowledgeTopic(
        topic_id="disease_prevention",
        keywords=["disease", "sickness", "cholera", "dysentery", "fever",
                  "illness", "sick", "diarrhea"],
        label="Preventing disease",
        category="survival",
        occupations=["Doctor"],
        response=(
            "Cholera and dysentery kill more prospectors than all the "
            "grizzlies and outlaws combined. Boil your drinking water if "
            "you have any doubt about the source. Do not camp downstream "
            "of a large camp or town -- their waste fouls the water. Keep "
            "your hands clean before eating. Dig your latrine well away from "
            "any water source and downhill from camp. If a man in camp gets "
            "cholera, isolate him and boil everything he touches."
        ),
        teaches_skill_xp=("firstAid", 5.0),
    ),

]


# =============================================================================
#  LOOKUP & MATCHING
# =============================================================================

def match_topic(text: str) -> Optional[KnowledgeTopic]:
    """Match free-typed text against keyword lists.

    Returns the best-matching topic, or None if no keywords match.
    Scoring: +1 per keyword found in text, +1 bonus for keywords longer
    than 4 characters (rewards more specific matches).
    """
    text_lower = text.lower()
    best: Optional[KnowledgeTopic] = None
    best_score = 0
    for topic in KNOWLEDGE_DB:
        score = 0
        for kw in topic.keywords:
            if kw in text_lower:
                score += 1
                # Bonus for longer, more specific keyword matches
                if len(kw) > 4:
                    score += 1
        if score > best_score:
            best_score = score
            best = topic
    return best if best_score > 0 else None


def get_npc_response(topic: KnowledgeTopic,
                     npc_occupation: str,
                     npc_name: str,
                     npc_traits: List[str] = None) -> str:
    """Format an NPC's response to a knowledge topic.

    - If the NPC's occupation is in the topic's occupation list (or the list is
      empty), they give the full detailed answer.
    - If the occupation is restricted and the NPC does not match, they give a
      redirect message suggesting whom to ask.
    - npc_traits adds personality-flavored suffixes for variety.
    """
    import random as _krng

    # No occupation restriction, or NPC matches -- give full answer.
    if not topic.occupations or npc_occupation in topic.occupations:
        # Add personality suffix for variety
        suffix = ""
        if npc_traits:
            try:
                from src.npc_speech import PERSONALITY_SUFFIXES
                traits_lower = [t.lower() for t in npc_traits]
                for trait in traits_lower:
                    if trait in PERSONALITY_SUFFIXES:
                        suffix = _krng.choice(PERSONALITY_SUFFIXES[trait])
                        break
            except ImportError:
                pass

        # Vary the attribution format
        attrib = _krng.choice([
            f" — {npc_name}",
            f" *{npc_name} nods.*",
            f" *says {npc_name}.*",
            f" *{npc_name} explains.*",
        ])
        return f'"{topic.response}{suffix}"{attrib}'

    # NPC does not match the required occupation.
    suggestions = topic.occupations[:2]  # suggest up to 2 relevant occupations
    if len(suggestions) == 1:
        who = f"a {suggestions[0].lower()}"
    else:
        who = f"a {suggestions[0].lower()} or a {suggestions[1].lower()}"
    redirects = [
        f'"I don\'t know much about that. You\'d be better off asking {who}." — {npc_name}',
        f'*{npc_name} shakes their head.* "Ask {who}. They\'d know."',
        f'"That ain\'t my area. Try {who}." — {npc_name}',
        f'"Couldn\'t tell you. {who.capitalize()} would know better." — {npc_name}',
    ]
    return _krng.choice(redirects)


def get_topic_menu(npc_occupation: str) -> List[Tuple[str, str]]:
    """Return (label, category) tuples for topics this NPC can answer.

    Topics are returned grouped by category.  An NPC can answer a topic if
    the topic's occupation list is empty (anyone can answer) or if the NPC's
    occupation is in the list.
    """
    results: List[Tuple[str, str]] = []
    for topic in KNOWLEDGE_DB:
        if not topic.occupations or npc_occupation in topic.occupations:
            results.append((topic.label, topic.category))

    # Sort by category then by label for clean menu grouping.
    results.sort(key=lambda t: (t[1], t[0]))
    return results
