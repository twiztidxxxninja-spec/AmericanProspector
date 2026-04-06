"""
src/newspaper.py

Newspaper system for American Prospector.

Towns with printing presses publish weekly newspapers containing articles
generated from game events (gold strikes, crimes, player actions) mixed
with era-appropriate filler headlines.  Players can buy and read issues
at general stores or newspaper offices.

Player-authored articles submitted through the writing system can appear
in newspapers, boosting reputation and writer fame.

Integration:
    engine.newspaper  — NewspaperSystem instance
    writing.py        — AuthoredWork, WritingManager (player submissions)
    economy.py        — ReputationTracker.adjust(region, delta)
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


# ============================================================================
#  FILLER HEADLINES — era-appropriate 1849 California Gold Rush
# ============================================================================

FILLER_HEADLINES: List[Dict[str, str]] = [
    # Gold strikes
    {"headline": "Rich Diggings Found on the American Fork",
     "body": "Several companies of miners report finding coarse gold in abundance along a new bar on the American Fork. One man is said to have taken out forty dollars in a single afternoon with nothing but a tin pan.",
     "category": "gold_strike"},
    {"headline": "New Placers Discovered Near Coloma",
     "body": "Fresh discoveries on a tributary of the South Fork have drawn hundreds of miners from surrounding camps. The richest claims are said to yield an ounce a day to the man.",
     "category": "gold_strike"},
    {"headline": "Rumors of Gold in the Northern Mines",
     "body": "Travelers arriving from the Feather River country bring word of extraordinarily rich diggings. Nuggets as large as pigeon eggs have been exhibited in several camps.",
     "category": "gold_strike"},
    {"headline": "Gold Dust Plentiful at Hangtown",
     "body": "The merchants of Hangtown report brisk trade, with miners paying for goods exclusively in gold dust. Several stores have taken in over a thousand dollars in a single week.",
     "category": "gold_strike"},

    # Shipping & arrivals
    {"headline": "Steamer 'California' Arrives with 300 Passengers",
     "body": "The Pacific Mail steamship California dropped anchor yesterday, disgorging three hundred eager gold-seekers upon our wharves. Many hail from New York and New England and appear wholly unprepared for the rigors ahead.",
     "category": "business"},
    {"headline": "Provisions Arrive by Sea — Prices Expected to Ease",
     "body": "A fleet of three merchant vessels has arrived laden with flour, salt pork, beans, and hardware. Merchants anticipate a welcome reduction in the extortionate prices that have prevailed.",
     "category": "business"},
    {"headline": "Clipper Ship Sets Record Passage Around the Horn",
     "body": "The clipper Sea Witch has arrived after a passage of only 97 days from New York, the fastest yet recorded. She brings a full cargo of mining supplies and dry goods.",
     "category": "business"},

    # Politics & statehood
    {"headline": "Convention Delegates Debate Statehood Constitution",
     "body": "Delegates meeting at Monterey continue to argue the boundaries and provisions of a proposed state constitution. The question of slavery remains the most contentious point of debate.",
     "category": "politics"},
    {"headline": "Military Governor Issues New Regulations on Claims",
     "body": "General Riley has published new orders governing the size and registration of mining claims. Each man is to be entitled to one claim of ten square feet, with forfeiture for abandonment exceeding three days.",
     "category": "politics"},
    {"headline": "Petition for California Statehood Gains Signatures",
     "body": "A petition urging Congress to admit California directly as a state, bypassing territorial status, has gathered over a thousand signatures. Proponents argue that the population already exceeds that of several existing states.",
     "category": "politics"},

    # Crime
    {"headline": "Desperadoes Rob Miner of His Season's Earnings",
     "body": "A lone miner returning from the diggings was set upon by three armed men near Sutter's Fort. He was relieved of nearly eight hundred dollars in dust and left bound to a tree.",
     "category": "crime"},
    {"headline": "Horse Thief Hanged by Vigilance Committee",
     "body": "A man found in possession of a stolen horse was tried by a committee of citizens and hanged from a live oak near the plaza. The proceedings occupied less than two hours from arrest to execution.",
     "category": "crime"},
    {"headline": "Gambling Den Brawl Leaves Two Men Wounded",
     "body": "A dispute over a game of monte at a canvas gambling house erupted into a knife fight last evening. Two men received serious wounds, though both are expected to recover under the surgeon's care.",
     "category": "crime"},

    # Human interest
    {"headline": "Woman Arrives Overland — Only Female in Camp",
     "body": "Mrs. Elizabeth Bayliss, having traveled the overland route from Missouri with her husband's company, has arrived at the diggings. She is believed to be the only woman within fifty miles and reports the journey was 'tolerable.'",
     "category": "social"},
    {"headline": "Preacher Holds Services Under the Oaks",
     "body": "The Reverend Mr. Colton held divine services beneath a spreading oak tree on Sunday last. A congregation of some forty miners attended, many visibly moved. A collection of gold dust was taken up for charitable purposes.",
     "category": "social"},
    {"headline": "Bear Sighted Near Camp — Miners Take Precautions",
     "body": "A large grizzly bear has been seen on several occasions near the lower diggings. Miners are advised to secure their provisions and avoid traveling alone after dark.",
     "category": "social"},

    # Supply prices
    {"headline": "Flour Now Five Dollars the Pound in the Mines",
     "body": "The scarcity of provisions in the mining camps has driven the price of common flour to five dollars per pound. Eggs, when available, command ten dollars the dozen, and a single onion may fetch a dollar.",
     "category": "business"},
    {"headline": "Lumber Scarce — Building Costs Soar",
     "body": "The demand for sawn lumber far exceeds the capacity of the few sawmills in operation. Common boards sell for four hundred dollars per thousand feet, making even a simple cabin an expensive proposition.",
     "category": "business"},

    # Weather & natural events
    {"headline": "Heavy Rains Flood the Diggings",
     "body": "Three days of continuous rain have swollen the rivers and flooded many claims along the bars. Several miners have lost their tools and provisions to the rising waters.",
     "category": "social"},
    {"headline": "Dry Season Sets In — Water for Sluicing Grows Scarce",
     "body": "The summer drought has reduced many streams to a trickle, forcing miners to abandon their sluices and long toms. Some companies have begun digging ditches to bring water from distant springs.",
     "category": "social"},

    # Native affairs
    {"headline": "Indian Troubles Reported on the Stanislaus",
     "body": "Several mining companies on the Stanislaus River report hostilities with the native inhabitants. A party of miners was attacked while prospecting a remote gulch, though no lives were lost.",
     "category": "politics"},
    {"headline": "Treaty Negotiations with Valley Tribes",
     "body": "Federal commissioners have opened negotiations with several tribes of the great central valley. The Indians are said to be willing to cede their lands in exchange for reserved tracts and annual provisions.",
     "category": "politics"},

    # Miscellaneous
    {"headline": "Mail Service Established to the Mines",
     "body": "A private express company has commenced weekly mail service between San Francisco and the principal mining camps. Letters are carried for one dollar each, with newspapers at fifty cents.",
     "category": "business"},
    {"headline": "Fire Destroys Canvas Hotel in Sacramento",
     "body": "A fire of unknown origin consumed the City Hotel, a large canvas structure on J Street, early yesterday morning. The proprietor estimates his loss at ten thousand dollars, with no insurance.",
     "category": "social"},

    # ── Wartime headlines (generated when war is active) ──────────
    {"headline": "Troops Massing on the Frontier",
     "body": "Military dispatches report the movement of regular troops toward the contested territory. Local militia units have been called to muster.",
     "category": "war"},
    {"headline": "Supplies Scarce — Military Requisitions Blamed",
     "body": "Merchants complain of shortages in powder, lead, and provisions. The Army has requisitioned large quantities for the campaign, leaving civilians to pay inflated prices.",
     "category": "war"},
    {"headline": "Refugees Arrive from the Fighting",
     "body": "A party of families arrived yesterday from the contested regions, having abandoned their homes and improvements. They report widespread destruction and little hope of returning soon.",
     "category": "war"},
    {"headline": "Deserters Sought by Military Police",
     "body": "The provost marshal has issued warrants for several men accused of deserting their posts. A reward of twenty dollars is offered for information leading to their capture.",
     "category": "war"},
    {"headline": "Powder Price Reaches Five Dollars per Pound",
     "body": "The cost of black powder has risen to unprecedented levels owing to military demand and disrupted supply lines. Miners and hunters alike feel the pinch.",
     "category": "war"},
    {"headline": "Victory Reported — Enemy in Retreat",
     "body": "Dispatches from the front report a decisive engagement in which our forces drove the enemy from the field. Casualties are said to be heavy on both sides.",
     "category": "war"},
    {"headline": "Heavy Casualties in Recent Action",
     "body": "A battle of some consequence was fought last week. The lists of killed and wounded are not yet complete, but surgeons report the hospitals full to overflowing.",
     "category": "war"},
    {"headline": "Treaty Signed — Hostilities to Cease",
     "body": "Peace commissioners report the signing of articles of agreement. Troops are expected to withdraw to their posts within the month. Whether the peace will hold remains to be seen.",
     "category": "war"},
    {"headline": "Conscription Patrols Active in the District",
     "body": "All able-bodied men between the ages of eighteen and forty-five are reminded of their obligation to serve when called. Those found evading the muster may face penalties.",
     "category": "war"},
    {"headline": "War Profiteers Denounced",
     "body": "A public meeting was held to condemn those merchants who have raised prices beyond all reason during the present conflict. Several were named and threatened with tar and feathers.",
     "category": "war"},
]


# Default newspaper names per town
DEFAULT_NEWSPAPERS: Dict[str, str] = {
    "San Francisco":  "The Alta California",
    "Sacramento":     "The Sacramento Bee",
    "Stockton":       "The Stockton Times",
    "Monterey":       "The Californian",
    "San Jose":       "The San Jose Tribune",
    "Sonora":         "The Sonora Herald",
    "Marysville":     "The Marysville Express",
    "Coloma":         "The Coloma Gazette",
    "Hangtown":       "The Hangtown Independent",
    "Nevada City":    "The Nevada Journal",
}


# ============================================================================
#  DATA CLASSES
# ============================================================================

@dataclass
class NewsArticle:
    """A single article within a newspaper issue."""
    article_id: int
    headline: str
    body: str
    author: str
    category: str       # gold_strike, crime, business, politics, player_work, social
    day_published: int
    source_event: str   # event key or "filler" for generated content


@dataclass
class NewspaperIssue:
    """A single published edition of a newspaper."""
    issue_id: int
    newspaper_name: str
    town: str
    day_published: int
    articles: List[NewsArticle] = field(default_factory=list)


# ============================================================================
#  NEWSPAPER SYSTEM
# ============================================================================

class NewspaperSystem:
    """
    Manages newspaper publication across all towns.

    Game events are queued via record_event().  Each week (every 7 days),
    generate_issue() builds an edition from queued events plus filler.
    Player-authored articles can be injected via player_article_published().
    """

    def __init__(self):
        self.newspapers: Dict[str, str] = dict(DEFAULT_NEWSPAPERS)
        self.issues: List[NewspaperIssue] = []
        self.event_queue: List[dict] = []
        self._article_counter: int = 0
        self._issue_counter: int = 0

    # ── Internal helpers ──────────────────────────────────────────────

    def _next_article_id(self) -> int:
        self._article_counter += 1
        return self._article_counter

    def _next_issue_id(self) -> int:
        self._issue_counter += 1
        return self._issue_counter

    def _newspaper_name(self, town: str) -> str:
        """Return the newspaper name for a town, creating one if needed."""
        if town not in self.newspapers:
            self.newspapers[town] = f"The {town} Gazette"
        return self.newspapers[town]

    # ── Event recording ───────────────────────────────────────────────

    def record_event(self, event_type: str, details: str,
                     wx: int, wy: int, day: int) -> None:
        """
        Queue a game event for potential newspaper coverage.

        Parameters:
            event_type: category key (gold_strike, crime, business, etc.)
            details:    human-readable description of what happened
            wx, wy:     world-map coordinates where the event occurred
            day:        game day the event happened
        """
        self.event_queue.append({
            "event_type": event_type,
            "details": details,
            "wx": wx,
            "wy": wy,
            "day": day,
        })

    # ── Issue generation ──────────────────────────────────────────────

    def _event_to_article(self, event: dict, day: int) -> NewsArticle:
        """Convert a queued event dict into a NewsArticle."""
        category = event["event_type"]
        details = event["details"]

        # Build a headline from the details (first sentence or truncated)
        headline = details.split(".")[0].strip()
        if len(headline) > 80:
            headline = headline[:77] + "..."

        return NewsArticle(
            article_id=self._next_article_id(),
            headline=headline,
            body=details,
            author="Our Correspondent",
            category=category,
            day_published=day,
            source_event=f"{category}_{event['day']}",
        )

    def _pick_filler(self, count: int, rng: random.Random,
                     used_headlines: set) -> List[NewsArticle]:
        """Select filler articles, avoiding duplicates within this issue."""
        available = [f for f in FILLER_HEADLINES
                     if f["headline"] not in used_headlines]
        if not available:
            available = list(FILLER_HEADLINES)

        chosen = rng.sample(available, min(count, len(available)))
        articles = []
        for fdata in chosen:
            articles.append(NewsArticle(
                article_id=self._next_article_id(),
                headline=fdata["headline"],
                body=fdata["body"],
                author="Staff Writer",
                category=fdata["category"],
                day_published=0,    # filled in by generate_issue
                source_event="filler",
            ))
        return articles

    def generate_issue(self, town: str, day: int,
                       rng: random.Random,
                       year: int = 1849) -> NewspaperIssue:
        """
        Create a newspaper issue for a town on the given day.
        Newspapers didn't exist on the frontier before ~1840.
        Returns None for pre-newspaper eras.
        """
        # No newspapers on the frontier before 1840
        if year < 1840:
            return None

        paper_name = self._newspaper_name(town)

        # Gather recent events (last 7 days)
        recent = [e for e in self.event_queue if day - e["day"] <= 7]

        # Build real articles from events
        real_articles: List[NewsArticle] = []
        consumed_indices: List[int] = []
        for i, event in enumerate(self.event_queue):
            if event in recent:
                real_articles.append(self._event_to_article(event, day))
                consumed_indices.append(self.event_queue.index(event))

        # Remove consumed events from the queue (oldest first)
        for idx in sorted(consumed_indices, reverse=True):
            self.event_queue.pop(idx)

        # Decide target article count: 4-6 per issue
        target_count = rng.randint(4, 6)
        filler_needed = max(0, target_count - len(real_articles))

        used_headlines = {a.headline for a in real_articles}
        # Also avoid headlines from the last 3 issues in this town
        for past_issue in self.issues[-10:]:
            if past_issue.town == town:
                for art in past_issue.articles:
                    used_headlines.add(art.headline)

        filler = self._pick_filler(filler_needed, rng, used_headlines)
        for art in filler:
            art.day_published = day

        all_articles = real_articles + filler

        issue = NewspaperIssue(
            issue_id=self._next_issue_id(),
            newspaper_name=paper_name,
            town=town,
            day_published=day,
            articles=all_articles,
        )
        self.issues.append(issue)
        return issue

    # ── Player article integration ────────────────────────────────────

    def player_article_published(self, work_title: str, author_name: str,
                                 town: str, day: int) -> NewspaperIssue:
        """
        Record that a player-authored article has been accepted and
        published in the local newspaper.

        Creates a special article in the next available issue.  If no
        issue exists for this town on this day, a mini-issue is created.

        Returns the issue containing the player's work.
        """
        paper_name = self._newspaper_name(town)

        player_article = NewsArticle(
            article_id=self._next_article_id(),
            headline=f"Correspondence: {work_title}",
            body=f"We are pleased to present to our readers the following "
                 f"contribution from {author_name}, lately of the diggings.",
            author=author_name,
            category="player_work",
            day_published=day,
            source_event="player_submission",
        )

        # Try to add to an existing issue published today in this town
        for issue in self.issues:
            if issue.town == town and issue.day_published == day:
                issue.articles.append(player_article)
                return issue

        # Otherwise create a new issue with the player article
        issue = NewspaperIssue(
            issue_id=self._next_issue_id(),
            newspaper_name=paper_name,
            town=town,
            day_published=day,
            articles=[player_article],
        )
        self.issues.append(issue)
        return issue

    # ── Reading / availability ────────────────────────────────────────

    def get_available(self, town: str, day: int) -> List[NewspaperIssue]:
        """
        Get newspaper issues available for purchase at a given town.

        Returns issues published in or near this town within the last
        14 days (papers stay on the shelf for two weeks).
        """
        available: List[NewspaperIssue] = []
        for issue in self.issues:
            age = day - issue.day_published
            if age < 0 or age > 14:
                continue
            # Papers from this town are always available;
            # papers from other towns arrive after a short delay
            if issue.town == town:
                available.append(issue)
            elif age >= 2:
                # Out-of-town papers arrive after 2 days
                available.append(issue)
        return available

    def read_issue(self, issue: NewspaperIssue) -> str:
        """
        Return formatted text of the newspaper issue for display.
        """
        lines: List[str] = []
        lines.append(f"{'=' * 52}")
        lines.append(f"  {issue.newspaper_name.upper()}")
        lines.append(f"  {issue.town} -- Day {issue.day_published}")
        lines.append(f"{'=' * 52}")
        lines.append("")

        for i, art in enumerate(issue.articles):
            lines.append(f"  {art.headline}")
            lines.append(f"  {'-' * len(art.headline)}")
            # Word-wrap the body at ~48 chars
            words = art.body.split()
            line = "  "
            for word in words:
                if len(line) + len(word) + 1 > 50:
                    lines.append(line)
                    line = "  " + word
                else:
                    line = line + " " + word if line.strip() else "  " + word
            if line.strip():
                lines.append(line)
            lines.append(f"    -- {art.author}")
            lines.append("")

        lines.append(f"{'=' * 52}")
        return "\n".join(lines)

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_counter": self._article_counter,
            "issue_counter": self._issue_counter,
            "newspapers": dict(self.newspapers),
            "event_queue": list(self.event_queue),
            "issues": [
                {
                    "issue_id": iss.issue_id,
                    "newspaper_name": iss.newspaper_name,
                    "town": iss.town,
                    "day_published": iss.day_published,
                    "articles": [
                        {
                            "article_id": a.article_id,
                            "headline": a.headline,
                            "body": a.body,
                            "author": a.author,
                            "category": a.category,
                            "day_published": a.day_published,
                            "source_event": a.source_event,
                        }
                        for a in iss.articles
                    ],
                }
                for iss in self.issues
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NewspaperSystem":
        ns = cls()
        ns._article_counter = d.get("article_counter", 0)
        ns._issue_counter = d.get("issue_counter", 0)
        ns.newspapers = d.get("newspapers", dict(DEFAULT_NEWSPAPERS))
        ns.event_queue = d.get("event_queue", [])
        for iss_data in d.get("issues", []):
            articles = []
            for a_data in iss_data.get("articles", []):
                articles.append(NewsArticle(
                    article_id=a_data["article_id"],
                    headline=a_data["headline"],
                    body=a_data["body"],
                    author=a_data["author"],
                    category=a_data["category"],
                    day_published=a_data["day_published"],
                    source_event=a_data["source_event"],
                ))
            ns.issues.append(NewspaperIssue(
                issue_id=iss_data["issue_id"],
                newspaper_name=iss_data["newspaper_name"],
                town=iss_data["town"],
                day_published=iss_data["day_published"],
                articles=articles,
            ))
        return ns
