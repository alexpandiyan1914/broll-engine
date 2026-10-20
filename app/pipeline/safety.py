import re

PEOPLE = {"people", "person", "man", "woman", "men", "women", "girl", "boy", "child",
          "children", "kid", "kids", "face", "faces", "crowd", "portrait", "couple",
          "family", "businessman", "businesswoman", "student", "students", "worker",
          "workers", "team", "friends", "human", "humans", "smiling"}
ALCOHOL = {"alcohol", "beer", "wine", "whiskey", "whisky", "cocktail", "champagne",
           "vodka", "pub", "bar", "liquor", "brewery"}
AVOID_MAP = {
    "face": PEOPLE, "faces": PEOPLE, "people": PEOPLE, "person": PEOPLE,
    "human": PEOPLE, "humans": PEOPLE,
    "alcohol": ALCOHOL, "alcoholic": ALCOHOL,
    "smoking": {"smoking", "cigarette", "cigar", "tobacco", "smoke", "vape"},
    "weapons": {"gun", "guns", "weapon", "weapons", "knife", "rifle", "pistol"},
    "violence": {"violence", "fight", "fighting", "blood", "war"},
}
ALWAYS_BLOCKED = {"logo", "logos", "brand", "watermark"}

SENSITIVE = {"died", "death", "dead", "dies", "killed", "kill", "murder", "murdered",
             "war", "tragedy", "tragic", "victim", "victims", "funeral", "attack",
             "attacked", "shooting", "massacre", "suicide", "cancer", "disaster",
             "earthquake", "flood", "floods", "crash", "abuse", "terror", "terrorist",
             "bomb", "grief", "mourn", "mourned", "mourning", "tsunami", "famine"}

CALM = ["quiet sunrise over calm lake", "candle flame dark room", "rain on window",
        "empty road foggy morning", "gentle waves shoreline", "clouds moving slowly sky",
        "autumn leaves falling", "still water reflection"]

COMMON = {"I", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
          "Sunday", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"}


def tag_set(tags: str) -> set:
    return set(re.findall(r"[a-z]+", (tags or "").lower()))


def is_sensitive(text: str) -> bool:
    low = text.lower()
    return bool(tag_set(low) & SENSITIVE) or "passed away" in low


def calm_query(i: int) -> str:
    return CALM[i % len(CALM)]


def named_entities(text: str) -> list:
    """Capitalised words that are not at the start of a sentence (names, brands)."""
    out, prev_end = [], True
    for w in text.split():
        core = re.sub(r"^\W+|\W+$", "", w)
        if core and not prev_end and core[0].isupper() and not core.isupper() and core not in COMMON:
            out.append(core)
        prev_end = w[-1] in ".!?"
    return out


def blocked_tags(avoid, sensitive: bool = False) -> set:
    blocked = set(ALWAYS_BLOCKED)
    for phrase in avoid or []:
        for tok in re.findall(r"[a-z]+", phrase.lower()):
            if tok in AVOID_MAP:
                blocked |= AVOID_MAP[tok]
            elif len(tok) > 3:
                blocked.add(tok)
    if sensitive:
        blocked |= PEOPLE
    return blocked