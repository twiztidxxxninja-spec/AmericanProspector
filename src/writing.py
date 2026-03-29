"""
src/writing.py

Writing, literature, and mail system for American Prospector.

Physical writing requires materials (ink + pen/quill/pencil + paper).
Letters go through the post office — sent from one town, picked up at
another.  Delivery takes real game-time based on distance.

Authored works (books, articles, sketches) are items that can be sold,
traded, or submitted for the Scholar win condition.

Key classes:
    WritingMaterials    — checks and consumes ink/pen/paper from inventory
    MailSystem          — post office letter routing with travel time
    AuthoredWork        — a book, article, sketch, or painting the player made
    WritingManager      — manages all writing state, mail, and works

Integration:
    Journal gets a "Write" tab for composing diary/letters/books.
    Post offices are buildings in towns (town_gen.py).
    LLM can generate letter content for NPC-sent mail.
    Literacy skill affects writing quality and options.
    Items: ink, quill, pen, pencil, paper, parchment, canvas, paints.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.items import Item
    from src.player import Player


# ============================================================================
#  WRITING MATERIAL REQUIREMENTS
# ============================================================================

# What you need to write different things
MATERIAL_REQS: Dict[str, dict] = {
    "diary_entry": {
        "writing_tool": True,    # pen, pencil, quill, or charcoal
        "surface": True,         # paper, parchment, or journal
        "ink": False,            # pencil doesn't need ink
        "time_minutes": 10,
    },
    "letter": {
        "writing_tool": True,
        "surface": True,
        "ink": False,
        "time_minutes": 20,
    },
    "article": {
        "writing_tool": True,
        "surface": True,
        "ink": True,             # articles need proper ink
        "time_minutes": 120,
    },
    "book_chapter": {
        "writing_tool": True,
        "surface": True,
        "ink": True,
        "time_minutes": 240,
    },
    "sketch": {
        "writing_tool": True,    # pencil or charcoal
        "surface": True,
        "ink": False,
        "time_minutes": 30,
    },
    "painting": {
        "paint": True,           # requires paints specifically
        "surface": True,         # canvas or paper
        "ink": False,
        "time_minutes": 180,
    },
}

# Items that count as writing tools
WRITING_TOOLS = {"Pen", "Quill", "Pencil", "Charcoal Stick", "Chalk"}

# Items that count as writing surfaces
WRITING_SURFACES = {"Paper", "Parchment", "Stationery", "Canvas"}

# Items that count as ink
INK_ITEMS = {"Ink", "Ink Bottle", "India Ink"}

# Items that count as paint
PAINT_ITEMS = {"Paints", "Paint Set", "Watercolors", "Oil Paints"}


def check_materials(inventory: list, work_type: str) -> Tuple[bool, List[str]]:
    """
    Check if the player has materials to write/draw something.
    Returns (has_all, list_of_missing).
    """
    reqs = MATERIAL_REQS.get(work_type, MATERIAL_REQS["diary_entry"])
    missing = []

    inv_names = {getattr(i, "name", "").strip() for i in inventory}

    if reqs.get("writing_tool"):
        if not any(n in WRITING_TOOLS for n in inv_names):
            missing.append("writing tool (pen, pencil, quill, or charcoal)")

    if reqs.get("surface"):
        if not any(n in WRITING_SURFACES for n in inv_names):
            missing.append("paper or parchment")

    if reqs.get("ink"):
        if not any(n in INK_ITEMS for n in inv_names):
            missing.append("ink")

    if reqs.get("paint"):
        if not any(n in PAINT_ITEMS for n in inv_names):
            missing.append("paints")

    return len(missing) == 0, missing


def consume_surface(inventory: list) -> Optional[str]:
    """Consume one sheet of paper/parchment. Returns name consumed or None."""
    for i, item in enumerate(inventory):
        name = getattr(item, "name", "")
        if name in WRITING_SURFACES:
            if getattr(item, "stackable", False) and getattr(item, "quantity", 1) > 1:
                item.quantity -= 1
                return name
            else:
                inventory.pop(i)
                return name
    return None


# ============================================================================
#  MAIL SYSTEM
# ============================================================================

@dataclass
class MailItem:
    """A letter in transit or waiting at a post office."""
    id: int
    sender: str              # NPC name or player name
    sender_npc_id: str       # "" if from player
    recipient: str           # player name or NPC name
    body: str
    sent_day: int            # game day sent
    arrival_day: int         # game day it arrives at destination
    origin_town: str         # town name where sent
    destination_town: str    # town name where it goes
    picked_up: bool = False
    read: bool = False
    replied: bool = False


class MailSystem:
    """
    Manages letters in transit between towns.

    Letters are sent from a post office and arrive at the destination
    post office after travel time based on distance.  Player picks up
    mail by visiting a post office in a town.

    NPC letters (from BackgroundSimulator) are routed to the nearest
    town to the player's last known location.
    """

    def __init__(self):
        self.mail: List[MailItem] = []
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    def send_letter(self, sender: str, recipient: str,
                     body: str, day: int,
                     origin: str, destination: str,
                     distance_tiles: int = 20,
                     sender_npc_id: str = "") -> MailItem:
        """
        Send a letter.  Travel time: ~1 day per 10 world tiles distance,
        minimum 2 days (nothing is instant on the frontier).
        """
        travel_days = max(2, distance_tiles // 10)

        mail = MailItem(
            id=self._next_id(),
            sender=sender, sender_npc_id=sender_npc_id,
            recipient=recipient, body=body,
            sent_day=day, arrival_day=day + travel_days,
            origin_town=origin, destination_town=destination,
        )
        self.mail.append(mail)
        return mail

    def check_mail(self, town_name: str, current_day: int,
                    recipient: str = "") -> List[MailItem]:
        """
        Check for available mail at a specific town's post office.
        Returns letters that have arrived and not been picked up.
        """
        available = []
        for m in self.mail:
            if m.picked_up:
                continue
            if m.destination_town.lower() != town_name.lower():
                continue
            if current_day < m.arrival_day:
                continue  # still in transit
            if recipient and m.recipient.lower() != recipient.lower():
                continue
            available.append(m)
        return available

    def pickup(self, mail_id: int) -> Optional[MailItem]:
        """Mark a letter as picked up."""
        for m in self.mail:
            if m.id == mail_id:
                m.picked_up = True
                return m
        return None

    def pending_count(self, recipient: str, current_day: int) -> int:
        """How many letters are waiting for pickup anywhere."""
        return sum(1 for m in self.mail
                   if not m.picked_up
                   and m.recipient.lower() == recipient.lower()
                   and current_day >= m.arrival_day)

    def in_transit_count(self, recipient: str, current_day: int) -> int:
        """How many letters are still being delivered."""
        return sum(1 for m in self.mail
                   if not m.picked_up
                   and m.recipient.lower() == recipient.lower()
                   and current_day < m.arrival_day)

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "mail": [
                {
                    "id": m.id, "sender": m.sender,
                    "sender_npc_id": m.sender_npc_id,
                    "recipient": m.recipient, "body": m.body,
                    "sent_day": m.sent_day, "arrival_day": m.arrival_day,
                    "origin_town": m.origin_town,
                    "destination_town": m.destination_town,
                    "picked_up": m.picked_up, "read": m.read,
                    "replied": m.replied,
                }
                for m in self.mail
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MailSystem":
        ms = cls()
        ms._counter = d.get("counter", 0)
        for md in d.get("mail", []):
            ms.mail.append(MailItem(**md))
        return ms


# ============================================================================
#  AUTHORED WORKS
# ============================================================================

class WorkType:
    DIARY_ENTRY = "diary_entry"
    LETTER      = "letter"
    ARTICLE     = "article"
    BOOK        = "book"
    SKILL_BOOK  = "skill_book"
    POEM        = "poem"
    SKETCH      = "sketch"
    PAINTING    = "painting"
    MAP         = "map"


@dataclass
class Submission:
    """A manuscript submitted to a publisher/newspaper."""
    id: int
    work_id: int
    work_title: str
    work_type: str
    work_quality: float
    work_chapters: int
    author_name: str            # real name or pen name
    pen_name: str               # "" if using real name
    recipient_name: str         # "New York Tribune", "Harper's", etc.
    recipient_type: str         # "newspaper"|"publisher"|"person"|"journal"
    sent_day: int
    response_day: int           # when the response arrives
    origin_town: str
    postage_paid: float = 0.25
    responded: bool = False
    accepted: bool = False
    payment: float = 0.0
    royalty_per_month: float = 0.0
    total_royalties: float = 0.0


@dataclass
class AuthoredWork:
    """A piece of writing or art created by the player."""
    id: int
    work_type: str          # WorkType
    title: str
    content: str            # the actual text or description
    author: str             # player name
    date_created: str       # game date string
    quality: float          # 0.0-1.0 based on literacy skill + INT
    chapters: int = 1       # for books, how many chapters written
    chapters_target: int = 1  # total chapters needed
    complete: bool = True
    base_value: float = 0.0   # dollars if sold

    # Skill book fields
    teaches_skill: str = ""     # skill name this book teaches ("geology", "placer", etc.)
    skill_depth: int = 0        # 0-4 knowledge level the book covers (0=intro, 4=mastery)
    about_subject: str = ""     # free text subject ("self", "geology", "local wildlife")

    @property
    def value(self) -> float:
        return self.base_value * self.quality


# ============================================================================
#  SKILL BOOKS — pre-made books that exist in the world
# ============================================================================

@dataclass
class SkillBookDef:
    """Template for a skill book that spawns in the world."""
    id: str
    title: str
    skill: str              # which skill this teaches
    depth: int              # 0-4 (intro to mastery)
    xp_per_read: float      # XP granted per reading session
    knowledge_grants: int   # knowledge level it can raise you to (0-4)
    weight: float = 1.0
    base_value: float = 2.0
    description: str = ""
    rarity: float = 0.5     # 0.0-1.0, lower = rarer


SKILL_BOOKS: Dict[str, SkillBookDef] = {}

def _skb(id, title, skill, depth, xp, knowledge, val, desc, rarity=0.5):
    SKILL_BOOKS[id] = SkillBookDef(
        id=id, title=title, skill=skill, depth=depth,
        xp_per_read=xp, knowledge_grants=knowledge,
        weight=1.0, base_value=val, description=desc, rarity=rarity,
    )

# Prospecting & Mining
_skb("book_placer_intro", "The Placer Miner's Guide", "placer", 1,
     8.0, 1, 1.50, "A practical guide to panning, rocking, and sluicing.", 0.7)
_skb("book_placer_adv", "Advanced Placer Techniques", "placer", 2,
     12.0, 2, 3.00, "Hydraulic methods, long toms, and dredging operations.", 0.3)
_skb("book_geology_intro", "Principles of Geology", "geology", 1,
     8.0, 1, 2.00, "Basic rock types, mineral identification, and formation.", 0.6)
_skb("book_geology_adv", "Geological Survey Methods", "geology", 2,
     12.0, 2, 4.00, "Reading outcrops, tracing float, and assessing deposits.", 0.2)
_skb("book_hardrock", "Hard Rock Mining Manual", "hardRock", 1,
     10.0, 1, 3.00, "Shaft sinking, timbering, drilling, and blasting.", 0.4)
_skb("book_assaying", "The Assayer's Handbook", "assaying", 2,
     15.0, 2, 5.00, "Fire assay, wet chemistry, and ore valuation.", 0.2)

# Survival & Outdoor
_skb("book_survival", "The Prairie Traveler", "survival", 1,
     8.0, 1, 1.00, "Frémont's guide to overland travel, camps, and provisions.", 0.8)
_skb("book_tracking", "The Tracker's Art", "tracking", 1,
     8.0, 1, 1.50, "Reading sign, trailing game, and wilderness navigation.", 0.5)
_skb("book_firstaid", "The Domestic Medicine", "firstAid", 1,
     10.0, 1, 2.00, "Common remedies, wound care, and frontier doctoring.", 0.6)
_skb("book_firstaid_adv", "Surgical Practice on the Frontier", "firstAid", 3,
     20.0, 3, 8.00, "Amputation, bone setting, and field surgery.", 0.1)

# Trade & Law
_skb("book_trading", "The Merchant's Companion", "trading", 1,
     8.0, 1, 1.50, "Weights, measures, pricing, and frontier commerce.", 0.6)
_skb("book_law", "Blackstone's Commentaries (abridged)", "law", 2,
     12.0, 2, 4.00, "Common law, property rights, and legal procedure.", 0.3)
_skb("book_law_mining", "Mining Law and the General Mining Act", "law", 1,
     8.0, 1, 2.00, "Claim filing, lode vs placer, patent procedures.", 0.4)

# Engineering & Chemistry
_skb("book_engineering", "The Mechanic's Handbook", "engineering", 1,
     10.0, 1, 2.00, "Basic carpentry, ironwork, and mechanical principles.", 0.5)
_skb("book_chemistry", "Elements of Chemistry", "chemistry", 2,
     15.0, 2, 5.00, "Chemical processes, amalgamation, and refining.", 0.2)

# Firearms
_skb("book_firearms", "The Rifleman's Guide", "firearms", 1,
     8.0, 1, 1.50, "Marksmanship, weapon care, and powder management.", 0.6)

# Literacy (meta — reading improves reading)
_skb("book_literacy", "McGuffey's Reader", "literacy", 0,
     5.0, 1, 0.50, "A basic reading primer. Common in frontier schools.", 0.9)
_skb("book_literature", "Works of Shakespeare (pocket edition)", "literacy", 2,
     10.0, 2, 3.00, "Collected plays and sonnets. Dense but rewarding reading.", 0.3)

# General interest (no specific skill, but raises literacy)
_skb("book_bible", "Holy Bible (King James)", "literacy", 1,
     6.0, 1, 0.25, "The most common book on the frontier.", 1.0)
_skb("book_almanac", "Farmer's Almanac", "farming", 0,
     4.0, 1, 0.30, "Planting seasons, weather signs, and practical wisdom.", 0.8)


# ============================================================================
#  READING MECHANICS
# ============================================================================

def read_book(player, book_item, reading_minutes: int = 30) -> Tuple[List[str], int]:
    """
    Player reads a book for reading_minutes.
    Returns (messages, time_cost_minutes).

    Effects:
    - Literacy XP always gained
    - If skill book: skill XP + possible knowledge gain
    - Reading speed scales with literacy skill
    """
    msgs = []
    literacy = player.skills.get("literacy", 0)
    intel = player.attributes.get("intelligence", 10)

    # Reading speed: higher literacy = faster, more XP per session
    speed_mult = 1.0 + literacy * 0.1
    effective_minutes = int(reading_minutes * speed_mult)

    # Always gain literacy XP from reading anything
    lit_xp = 2.0 + effective_minutes * 0.05
    player.gain_skill_xp("literacy", lit_xp)

    # Check if it's a skill book
    book_id = getattr(book_item, "id", "")
    extra = getattr(book_item, "extra", {})
    teaches = extra.get("teaches_skill", "")
    book_def = SKILL_BOOKS.get(book_id)

    if book_def:
        teaches = book_def.skill
        # Grant skill XP
        xp = book_def.xp_per_read * speed_mult
        player.gain_skill_xp(teaches, xp)
        msgs.append(f"You study {book_def.title}. (+{xp:.1f} {teaches} XP)")

        # Knowledge gain — can raise knowledge to book's depth level
        current_k = player.knowledge.get(teaches, 0)
        if current_k < book_def.knowledge_grants:
            # Chance to gain knowledge increases with reading time and INT
            gain_chance = min(0.8, effective_minutes / 120.0 + intel * 0.02)
            if random.random() < gain_chance:
                player.knowledge[teaches] = current_k + 1
                k_labels = {0: "None", 1: "Partial", 2: "Working",
                            3: "Expert", 4: "Mastery"}
                new_label = k_labels.get(current_k + 1, "?")
                msgs.append(f"Your understanding of {teaches} deepens to: {new_label}.")
        elif current_k >= book_def.knowledge_grants:
            msgs.append("You've already learned what this book can teach you.")
    elif teaches:
        # LLM-generated or player-written skill book via extra field
        xp = 5.0 * speed_mult
        player.gain_skill_xp(teaches, xp)
        msgs.append(f"You read about {teaches}. (+{xp:.1f} {teaches} XP)")
    else:
        # General reading — just literacy XP
        title = getattr(book_item, "name", "the book")
        msgs.append(f"You read {title}. (+{lit_xp:.1f} literacy XP)")

    return msgs, reading_minutes


def read_player_work(player, work: AuthoredWork,
                      reading_minutes: int = 30) -> Tuple[List[str], int]:
    """
    Read a player-authored or NPC-authored work.
    Skill books written by player/NPCs can teach skills too.
    """
    msgs = []
    literacy = player.skills.get("literacy", 0)
    speed_mult = 1.0 + literacy * 0.1

    # Literacy XP
    lit_xp = 2.0 + reading_minutes * 0.05
    player.gain_skill_xp("literacy", lit_xp)

    if work.teaches_skill:
        # Skill book — XP scales with author quality
        xp = 4.0 * work.quality * speed_mult
        player.gain_skill_xp(work.teaches_skill, xp)
        msgs.append(f"You study \"{work.title}\". "
                     f"(+{xp:.1f} {work.teaches_skill} XP)")

        # Knowledge gain from high-quality works
        current_k = player.knowledge.get(work.teaches_skill, 0)
        if current_k < work.skill_depth and work.quality > 0.5:
            if random.random() < work.quality * 0.3:
                player.knowledge[work.teaches_skill] = current_k + 1
                msgs.append(f"Your {work.teaches_skill} knowledge improves.")
    else:
        msgs.append(f"You read \"{work.title}\". (+{lit_xp:.1f} literacy XP)")

    return msgs, reading_minutes


# ============================================================================
#  WRITING XP — gained from writing anything
# ============================================================================

def grant_writing_xp(player, work_type: str, quality: float) -> List[str]:
    """
    Grant XP for the act of writing.
    Called after any successful write action.
    """
    msgs = []

    # Literacy XP from writing (always)
    lit_xp = {
        WorkType.DIARY_ENTRY: 1.0,
        WorkType.LETTER: 2.0,
        WorkType.POEM: 3.0,
        WorkType.ARTICLE: 5.0,
        WorkType.BOOK: 8.0,
        WorkType.SKILL_BOOK: 10.0,
    }.get(work_type, 2.0)
    lit_xp *= (1.0 + quality)
    player.gain_skill_xp("literacy", lit_xp)
    msgs.append(f"(+{lit_xp:.1f} literacy XP)")

    return msgs


def calculate_quality(literacy_skill: int, intelligence: int,
                       work_type: str) -> float:
    """
    Determine writing/art quality from player skills.
    Higher literacy + INT = better quality = more valuable.
    """
    base = 0.2 + literacy_skill * 0.06 + max(0, intelligence - 10) * 0.02
    # Art types benefit from wisdom too
    if work_type in (WorkType.SKETCH, WorkType.PAINTING):
        base += 0.02  # slight bonus for visual work variety

    return min(1.0, max(0.1, base))


def estimate_value(work_type: str, quality: float, chapters: int = 1) -> float:
    """Estimate dollar value of a completed work."""
    base_values = {
        WorkType.DIARY_ENTRY: 0.0,     # personal, no sale value
        WorkType.LETTER:      0.0,     # personal
        WorkType.ARTICLE:     2.0,     # newspaper might buy it
        WorkType.BOOK:        10.0,    # per chapter
        WorkType.SKETCH:      0.50,
        WorkType.PAINTING:    3.0,
        WorkType.MAP:         1.0,
    }
    base = base_values.get(work_type, 0.5)
    return round(base * quality * chapters, 2)


# ============================================================================
#  WRITING MANAGER
# ============================================================================

class WritingManager:
    """
    Manages all player writing, mail, and authored works.
    """

    def __init__(self):
        self.mail = MailSystem()
        self.works: List[AuthoredWork] = []
        self.submissions: List[Submission] = []
        self.book_in_progress: Optional[AuthoredWork] = None
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    # ── Writing actions ────────────────────────────────────────────────

    def write_diary(self, text: str, player_name: str,
                     date_str: str, literacy: int, intel: int,
                     inventory: list) -> Tuple[bool, str]:
        """Write a diary entry. Consumes paper if available."""
        has, missing = check_materials(inventory, "diary_entry")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.DIARY_ENTRY)

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.DIARY_ENTRY,
            title="Diary Entry", content=text, author=player_name,
            date_created=date_str, quality=quality,
        )
        self.works.append(work)
        return True, "You write in your journal."

    def write_letter(self, recipient: str, body: str,
                      player_name: str, date_str: str,
                      literacy: int, intel: int,
                      inventory: list,
                      origin_town: str = "",
                      destination_town: str = "",
                      current_day: int = 0,
                      distance: int = 20) -> Tuple[bool, str]:
        """
        Write and send a letter.  Must be at a post office to send.
        Returns (success, message).
        """
        has, missing = check_materials(inventory, "letter")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        if not origin_town:
            return False, "You need to be at a town with a post office to send mail."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.LETTER)

        # Create the mail item
        mail = self.mail.send_letter(
            sender=player_name, recipient=recipient,
            body=body, day=current_day,
            origin=origin_town, destination=destination_town,
            distance_tiles=distance,
        )

        # Also save as an authored work (for journal/records)
        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.LETTER,
            title=f"Letter to {recipient}", content=body,
            author=player_name, date_created=date_str, quality=quality,
        )
        self.works.append(work)

        travel_days = mail.arrival_day - mail.sent_day
        return True, (f"Letter to {recipient} sent from {origin_town}. "
                      f"Should arrive in ~{travel_days} days.")

    def write_article(self, title: str, content: str,
                       player_name: str, date_str: str,
                       literacy: int, intel: int,
                       inventory: list) -> Tuple[bool, str]:
        """Write a newspaper article or essay."""
        has, missing = check_materials(inventory, "article")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.ARTICLE)
        value = estimate_value(WorkType.ARTICLE, quality)

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.ARTICLE,
            title=title, content=content, author=player_name,
            date_created=date_str, quality=quality,
            base_value=value,
        )
        self.works.append(work)

        quality_word = ("poor" if quality < 0.3 else "decent" if quality < 0.5
                        else "good" if quality < 0.7 else "excellent")
        return True, (f"You finish the article: \"{title}\". "
                      f"Quality: {quality_word}. Worth ~${value:.2f} to a newspaper.")

    def start_book(self, title: str, chapters_target: int,
                    player_name: str, date_str: str,
                    literacy: int, intel: int) -> Tuple[bool, str]:
        """Begin writing a book (multi-session project)."""
        if self.book_in_progress:
            return False, (f"Already writing \"{self.book_in_progress.title}\". "
                          f"Finish or abandon it first.")
        if chapters_target < 1:
            chapters_target = 5

        quality = calculate_quality(literacy, intel, WorkType.BOOK)

        self.book_in_progress = AuthoredWork(
            id=self._next_id(), work_type=WorkType.BOOK,
            title=title, content="", author=player_name,
            date_created=date_str, quality=quality,
            chapters=0, chapters_target=chapters_target,
            complete=False,
        )
        return True, (f"You begin work on \"{title}\" — "
                      f"a {chapters_target}-chapter book.")

    def write_chapter(self, chapter_text: str,
                       literacy: int, intel: int,
                       inventory: list) -> Tuple[bool, str]:
        """Write one chapter of the book in progress."""
        if not self.book_in_progress:
            return False, "No book in progress."

        has, missing = check_materials(inventory, "book_chapter")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        book = self.book_in_progress
        book.chapters += 1
        book.content += f"\n\n--- Chapter {book.chapters} ---\n{chapter_text}"

        # Quality adjusts with each chapter (gets better with practice)
        new_q = calculate_quality(literacy, intel, WorkType.BOOK)
        book.quality = (book.quality * (book.chapters - 1) + new_q) / book.chapters

        if book.chapters >= book.chapters_target:
            book.complete = True
            book.base_value = estimate_value(WorkType.BOOK, book.quality, book.chapters)
            self.works.append(book)
            self.book_in_progress = None
            return True, (f"\"{book.title}\" is complete! "
                         f"{book.chapters} chapters. Worth ~${book.base_value:.2f}.")

        return True, (f"Chapter {book.chapters}/{book.chapters_target} of "
                      f"\"{book.title}\" written.")

    def create_sketch(self, subject: str, player_name: str,
                       date_str: str, literacy: int, intel: int,
                       inventory: list) -> Tuple[bool, str]:
        """Draw a sketch with pencil/charcoal."""
        has, missing = check_materials(inventory, "sketch")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.SKETCH)
        value = estimate_value(WorkType.SKETCH, quality)

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.SKETCH,
            title=f"Sketch: {subject}", content=f"A sketch of {subject}.",
            author=player_name, date_created=date_str,
            quality=quality, base_value=value,
        )
        self.works.append(work)
        return True, f"You sketch {subject}. Worth ~${value:.2f}."

    def create_painting(self, subject: str, player_name: str,
                         date_str: str, literacy: int, intel: int,
                         inventory: list) -> Tuple[bool, str]:
        """Paint on canvas."""
        has, missing = check_materials(inventory, "painting")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.PAINTING)
        value = estimate_value(WorkType.PAINTING, quality)

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.PAINTING,
            title=f"Painting: {subject}", content=f"A painting of {subject}.",
            author=player_name, date_created=date_str,
            quality=quality, base_value=value,
        )
        self.works.append(work)
        return True, f"You paint {subject}. Worth ~${value:.2f}."

    def write_skill_book(self, skill: str, title: str,
                          content: str, player_name: str,
                          date_str: str, literacy: int, intel: int,
                          skill_level: int, inventory: list,
                          llm=None) -> Tuple[bool, str]:
        """
        Write a book that teaches a specific skill.
        Author must have the skill at level 3+ to write about it.
        Content can be player-written or LLM-generated.
        """
        if skill_level < 3:
            return False, (f"You need at least level 3 in {skill} "
                          f"to write authoritatively about it.")

        has, missing = check_materials(inventory, "book_chapter")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.SKILL_BOOK)
        # Skill expertise improves teaching quality
        quality = min(1.0, quality + skill_level * 0.04)

        # LLM generates content if player didn't write it
        if not content and llm and llm.available:
            content = self._llm_generate_content(
                f"skill guide about {skill}", title, llm)
        elif not content:
            content = f"A practical guide to {skill}."

        depth = min(4, skill_level - 1)
        value = estimate_value(WorkType.SKILL_BOOK, quality)

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.SKILL_BOOK,
            title=title, content=content, author=player_name,
            date_created=date_str, quality=quality,
            base_value=value,
            teaches_skill=skill, skill_depth=depth,
            about_subject=skill,
        )
        self.works.append(work)

        return True, (f"You write \"{title}\" — a guide to {skill}. "
                      f"Quality: {quality:.0%}. Teaches up to depth {depth}.")

    def write_poem(self, title: str, content: str,
                    player_name: str, date_str: str,
                    literacy: int, intel: int,
                    inventory: list, llm=None) -> Tuple[bool, str]:
        """Write a poem. Content can be player-written or LLM-generated."""
        has, missing = check_materials(inventory, "diary_entry")
        if not has:
            return False, f"Need: {', '.join(missing)}."

        consume_surface(inventory)
        quality = calculate_quality(literacy, intel, WorkType.POEM)

        if not content and llm and llm.available:
            content = self._llm_generate_content("poem", title, llm)
        elif not content:
            content = f"A poem titled \"{title}\"."

        value = estimate_value(WorkType.ARTICLE, quality) * 0.5

        work = AuthoredWork(
            id=self._next_id(), work_type=WorkType.POEM,
            title=title, content=content, author=player_name,
            date_created=date_str, quality=quality,
            base_value=value, about_subject=title,
        )
        self.works.append(work)
        return True, (f"You write the poem \"{title}\". "
                      f"Quality: {quality:.0%}.")

    def _llm_generate_content(self, work_type_desc: str,
                                title: str, llm) -> str:
        """Generate written content via LLM when player doesn't write it."""
        system = (
            "You are a frontier writer in 1849 America. Write a short, "
            "authentic piece as requested. Use period-appropriate language "
            "and phrasing. Keep it under 200 words."
        )
        prompt = f"Write a {work_type_desc} titled \"{title}\"."
        try:
            return llm._chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompt}],
                temperature=0.75, max_tokens=400, json_mode=False,
            ).strip()
        except Exception:
            return f"A {work_type_desc} titled \"{title}\"."

    # ── Publishing / Submission ───────────────────────────────────────

    def submit_work(self, work_id: int, recipient_name: str,
                     recipient_type: str,
                     player_name: str, pen_name: str,
                     origin_town: str, current_day: int,
                     distance: int, postage_cost: float,
                     inventory: list) -> Tuple[bool, str]:
        """
        Submit an authored work to a publisher/newspaper/recipient.

        Removes the physical manuscript from works list (it's been mailed).
        Creates a Submission record tracking the pending response.
        Charges postage. Uses pen name if provided.

        recipient_type: "newspaper"|"publisher"|"person"|"journal"
        """
        work = None
        for w in self.works:
            if w.id == work_id:
                work = w
                break
        if not work:
            return False, "Can't find that manuscript."
        if not work.complete:
            return False, "It's not finished yet."
        if not origin_town:
            return False, "You need to be at a town with a post office."

        author_name = pen_name if pen_name else player_name

        # Create submission
        sub = Submission(
            id=self._next_id(),
            work_id=work.id,
            work_title=work.title,
            work_type=work.work_type,
            work_quality=work.quality,
            work_chapters=work.chapters,
            author_name=author_name,
            pen_name=pen_name,
            recipient_name=recipient_name,
            recipient_type=recipient_type,
            sent_day=current_day,
            response_day=current_day + max(14, distance // 5),
            origin_town=origin_town,
            postage_paid=postage_cost,
        )
        self.submissions.append(sub)

        # Remove manuscript from works (it's physically gone)
        self.works = [w for w in self.works if w.id != work_id]

        # Send the physical mail
        self.mail.send_letter(
            sender=author_name, recipient=recipient_name,
            body=f"[Manuscript: \"{work.title}\" by {author_name}]",
            day=current_day, origin=origin_town,
            destination=recipient_name,
            distance_tiles=distance,
        )

        return True, (f"Manuscript \"{work.title}\" mailed to {recipient_name} "
                      f"from {origin_town}. Postage: ${postage_cost:.2f}. "
                      f"Expect a response in {sub.response_day - current_day} days.")

    def check_responses(self, current_day: int,
                         player_name: str,
                         nearest_town: str,
                         llm=None) -> List[Tuple["Submission", str]]:
        """
        Check if any submission responses have arrived.
        Generates the response letter via LLM if available.
        Returns list of (submission, response_body).
        """
        responses = []
        for sub in self.submissions:
            if sub.responded or current_day < sub.response_day:
                continue
            sub.responded = True

            # Determine acceptance
            import random as _rng
            rng = _rng.Random(sub.id + current_day)

            # Base acceptance chance from quality
            accept_chance = sub.work_quality * 0.8
            if sub.work_type == WorkType.BOOK:
                accept_chance *= 0.7  # books are harder to publish
            sub.accepted = rng.random() < accept_chance

            # Calculate payment
            if sub.accepted:
                if sub.work_type == WorkType.ARTICLE:
                    sub.payment = round(2.0 + sub.work_quality * 8.0, 2)
                elif sub.work_type == WorkType.BOOK:
                    sub.payment = round(sub.work_chapters * 5.0 * sub.work_quality, 2)
                    sub.royalty_per_month = round(sub.payment * 0.15, 2)
                elif sub.work_type == WorkType.PAINTING:
                    sub.payment = round(3.0 + sub.work_quality * 12.0, 2)
                else:
                    sub.payment = round(1.0 + sub.work_quality * 4.0, 2)

            # Generate response letter
            response_body = self._generate_response(sub, llm)

            # Route response to mail system
            self.mail.send_letter(
                sender=sub.recipient_name,
                recipient=player_name,
                body=response_body,
                day=current_day,
                origin=sub.recipient_name,
                destination=nearest_town,
                distance_tiles=30,
            )

            responses.append((sub, response_body))

        return responses

    def collect_royalties(self, current_day: int) -> float:
        """
        Collect monthly royalties from published books.
        Call once per month (every 30 game days).
        Returns total royalties earned.
        """
        total = 0.0
        for sub in self.submissions:
            if not sub.accepted or sub.royalty_per_month <= 0:
                continue
            # Royalties decay over time (books sell less as months pass)
            months_since = max(1, (current_day - sub.response_day) // 30)
            decay = max(0.1, 1.0 / (1 + months_since * 0.3))
            royalty = sub.royalty_per_month * decay
            total += royalty
            sub.total_royalties += royalty
        return round(total, 2)

    def _generate_response(self, sub: "Submission", llm=None) -> str:
        """Generate a response letter from the recipient, via LLM or template."""
        if llm and llm.available:
            return self._llm_response(sub, llm)
        return self._template_response(sub)

    def _llm_response(self, sub: "Submission", llm) -> str:
        system = (
            "You are an editor at a newspaper or publishing house in 1850s America. "
            "A prospector has submitted a manuscript. Write a short response letter "
            "(3-5 sentences) in character. Be specific about the work's title and "
            "content. If accepting, mention payment. If rejecting, give a reason. "
            "Sign with a plausible editor name and publication name."
        )
        prompt = (
            f"WORK: \"{sub.work_title}\" ({sub.work_type})\n"
            f"AUTHOR: {sub.author_name}\n"
            f"QUALITY: {sub.work_quality:.0%}\n"
            f"RECIPIENT TYPE: {sub.recipient_type}\n"
            f"DECISION: {'ACCEPTED — payment ${:.2f}'.format(sub.payment) if sub.accepted else 'REJECTED'}\n"
            f"{'ROYALTIES: ${:.2f}/month'.format(sub.royalty_per_month) if sub.royalty_per_month > 0 else ''}\n"
            f"\nWrite the response letter."
        )
        try:
            return llm._chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompt}],
                temperature=0.72, max_tokens=300, json_mode=False,
            ).strip()
        except Exception:
            return self._template_response(sub)

    def _template_response(self, sub: "Submission") -> str:
        if sub.accepted:
            if sub.work_type == WorkType.BOOK:
                return (f"Dear {sub.author_name},\n\n"
                        f"We are pleased to accept your manuscript "
                        f"\"{sub.work_title}\" for publication. Enclosed "
                        f"please find payment of ${sub.payment:.2f}. "
                        f"Royalties of ${sub.royalty_per_month:.2f} per month "
                        f"will be forwarded to your account.\n\n"
                        f"Yours truly,\nThe Editor")
            return (f"Dear {sub.author_name},\n\n"
                    f"We have received your piece \"{sub.work_title}\" "
                    f"and are happy to publish it. Enclosed: ${sub.payment:.2f}.\n\n"
                    f"Regards,\nThe Editor")
        return (f"Dear {sub.author_name},\n\n"
                f"We regret that \"{sub.work_title}\" does not meet our "
                f"current needs. We wish you success placing it elsewhere.\n\n"
                f"Respectfully,\nThe Editor")

    # ── Query ──────────────────────────────────────────────────────────

    def get_works_by_type(self, work_type: str) -> List[AuthoredWork]:
        return [w for w in self.works if w.work_type == work_type]

    def total_works_value(self) -> float:
        return sum(w.value for w in self.works if w.complete)

    def published_count(self) -> int:
        return sum(1 for s in self.submissions if s.accepted)

    def total_royalties_earned(self) -> float:
        return sum(s.total_royalties for s in self.submissions)

    def writer_fame(self) -> float:
        """
        0-100 writer fame score based on published works.
        Feeds into reputation system.
        """
        fame = 0.0
        for s in self.submissions:
            if not s.accepted:
                continue
            if s.work_type == WorkType.BOOK:
                fame += 15 * s.work_quality
            elif s.work_type == WorkType.ARTICLE:
                fame += 5 * s.work_quality
            else:
                fame += 2 * s.work_quality
        return min(100, fame)

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "mail": self.mail.to_dict(),
            "works": [
                {
                    "id": w.id, "work_type": w.work_type,
                    "title": w.title, "content": w.content,
                    "author": w.author, "date_created": w.date_created,
                    "quality": w.quality, "chapters": w.chapters,
                    "chapters_target": w.chapters_target,
                    "complete": w.complete, "base_value": w.base_value,
                }
                for w in self.works
            ],
            "submissions": [
                {
                    "id": s.id, "work_id": s.work_id,
                    "work_title": s.work_title, "work_type": s.work_type,
                    "work_quality": s.work_quality,
                    "work_chapters": s.work_chapters,
                    "author_name": s.author_name, "pen_name": s.pen_name,
                    "recipient_name": s.recipient_name,
                    "recipient_type": s.recipient_type,
                    "sent_day": s.sent_day, "response_day": s.response_day,
                    "origin_town": s.origin_town,
                    "postage_paid": s.postage_paid,
                    "responded": s.responded, "accepted": s.accepted,
                    "payment": s.payment,
                    "royalty_per_month": s.royalty_per_month,
                    "total_royalties": s.total_royalties,
                }
                for s in self.submissions
            ],
            "book_in_progress": {
                "id": self.book_in_progress.id,
                "work_type": self.book_in_progress.work_type,
                "title": self.book_in_progress.title,
                "content": self.book_in_progress.content,
                "author": self.book_in_progress.author,
                "date_created": self.book_in_progress.date_created,
                "quality": self.book_in_progress.quality,
                "chapters": self.book_in_progress.chapters,
                "chapters_target": self.book_in_progress.chapters_target,
                "complete": False,
                "base_value": 0,
            } if self.book_in_progress else None,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "WritingManager":
        wm = cls()
        wm._counter = d.get("counter", 0)
        wm.mail = MailSystem.from_dict(d.get("mail", {}))
        for wd in d.get("works", []):
            wm.works.append(AuthoredWork(**wd))
        for sd in d.get("submissions", []):
            wm.submissions.append(Submission(**sd))
        bip = d.get("book_in_progress")
        if bip:
            wm.book_in_progress = AuthoredWork(**bip)
        return wm
