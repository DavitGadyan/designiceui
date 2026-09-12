"""The tag vocabulary, and the synonym map that makes matching feel semantic.

Two jobs:

1. **Auto-tagging.** A design folder ships a plain-English description. We read
   it and attach controlled tags so the library stays browsable and filterable.

2. **Query expansion.** A user says "landing page for my crypto lending startup".
   Nothing in that sentence is the literal token "fintech", but the design we
   want is tagged `fintech`. Expanding both sides through this map is what lets
   even the zero-dependency lexical backend behave semantically. Dense
   embeddings get the same expansion appended, which measurably helps on short
   prompts where there is little else to embed.

The vocabulary is deliberately opinionated and finite. An open-ended tag soup
cannot be filtered on, and the whole point of facets is that `industry=fintech
AND motion=scroll-driven` is a question you can actually ask.
"""

from __future__ import annotations

import re
from typing import Iterable

# facet -> {tag: [trigger phrases]}
# The tag itself is always an implicit trigger; don't repeat it in the list.
FACETS: dict[str, dict[str, list[str]]] = {
    # What the site is *for*. This is the "which field / website for a ___" axis.
    "industry": {
        "saas": ["software as a service", "b2b platform", "subscription software", "product suite", "workspace tool"],
        "fintech": ["bank", "banking", "finance", "financial", "payments", "invoicing", "lending", "loan",
                    "wealth", "investing", "trading", "neobank", "accounting", "insurance", "insurtech"],
        "crypto-web3": ["crypto", "web3", "blockchain", "defi", "nft", "token", "wallet", "onchain", "dao"],
        "ai": ["artificial intelligence", "machine learning", "llm", "ai agent", "copilot", "language model",
               "foundation model", "inference", "neural", "automation", "genai", "chatbot", "prompt"],
        "developer-tools": ["developer", "devtool", "api platform", "sdk", "cli", "open source", "ci/cd",
                            "observability", "infrastructure", "database", "devops"],
        "agency": ["studio", "creative agency", "design agency", "consultancy", "freelance collective", "branding shop"],
        "portfolio": ["personal site", "my work", "case studies", "showreel", "designer portfolio",
                      "photographer", "resume site", "cv site"],
        "ecommerce": ["shop", "store", "retail", "checkout", "product page", "dtc", "marketplace", "cart", "brand store"],
        "healthcare": ["health", "medical", "clinic", "patient", "telehealth", "diagnostics", "pharma", "dental", "hospital"],
        "wellness": ["meditation", "mindfulness", "yoga", "fitness", "gym", "nutrition", "therapy", "spa", "mental health"],
        "travel": ["hotel", "resort", "booking", "destination", "tourism", "flights", "itinerary", "airbnb", "vacation"],
        "fashion": ["apparel", "clothing", "streetwear", "luxury brand", "lookbook", "runway", "jewelry", "beauty", "cosmetics"],
        "real-estate": ["property", "listings", "realtor", "architecture firm", "interior design", "housing", "apartments"],
        "education": ["course", "school", "university", "learning", "bootcamp", "curriculum", "edtech", "academy", "tutoring"],
        "food-drink": ["restaurant", "cafe", "coffee", "bakery", "menu", "recipe", "brewery", "bar", "catering", "dining"],
        "gaming": ["game studio", "esports", "player", "arcade", "console", "twitch", "gaming"],
        "media": ["magazine", "publication", "newsroom", "editorial site", "podcast", "streaming", "film", "news"],
        "music": ["band", "album", "artist site", "label", "concert", "festival", "dj", "record"],
        "events": ["conference", "summit", "meetup", "ticketing", "webinar", "expo", "wedding"],
        "nonprofit": ["charity", "ngo", "donation", "foundation", "volunteer", "fundraising", "cause"],
        "environmental": ["sustainability", "climate", "green energy", "carbon", "renewable", "solar", "eco", "conservation"],
        "space": ["aerospace", "satellite", "orbital", "rocket", "cosmic", "astronomy", "planetary", "launch"],
        "automotive": ["car", "vehicle", "ev", "motorcycle", "dealership", "mobility", "autonomous driving"],
        "logistics": ["shipping", "freight", "supply chain", "fleet", "warehouse", "delivery", "3pl"],
        "security": ["cybersecurity", "infosec", "zero trust", "threat", "encryption", "compliance", "soc2", "firewall"],
        "hardware": ["robotics", "device", "iot", "chip", "semiconductor", "manufacturing", "industrial", "drone", "sensor"],
        "social": ["community", "creator", "social network", "forum", "messaging", "dating", "influencer"],
        "sports": ["team", "athletics", "league", "training", "running", "cycling", "outdoor gear"],
        "legal": ["law firm", "attorney", "counsel", "compliance firm", "paralegal", "litigation"],
        "hospitality": ["hotel group", "hostel", "guesthouse", "concierge", "venue"],
    },
    # The shape of the thing being built.
    "page_type": {
        "landing-page": ["landing", "marketing page", "one pager", "single page site", "homepage", "splash"],
        "marketing-site": ["multi page site", "full website", "company site", "corporate site", "brochure site"],
        "hero": ["hero section", "above the fold", "header section", "opening section"],
        "dashboard": ["admin panel", "analytics view", "control panel", "internal tool", "metrics screen", "console"],
        "app-shell": ["product ui", "web app", "application chrome", "sidebar layout", "workspace ui"],
        "docs": ["documentation", "developer docs", "knowledge base", "guide site", "reference site"],
        "pricing-page": ["plans page", "pricing tiers", "subscription page"],
        "blog": ["articles", "posts", "writing", "journal", "newsletter site"],
        "portfolio-page": ["work index", "project grid", "gallery site", "case study page"],
        "product-detail": ["pdp", "product page", "item page", "shop detail"],
        "auth": ["login", "sign in", "sign up", "onboarding screen", "register"],
        "error-page": ["404", "500", "not found", "empty state page"],
        "component": ["ui component", "single block", "widget", "reusable block"],
    },
    # Named blocks the design demonstrates well. Lets an agent pull one section.
    "section": {
        "hero": ["hero", "above the fold"],
        "features": ["feature grid", "capabilities", "what you get", "benefits"],
        "bento": ["bento grid", "bento box layout", "modular grid"],
        "pricing": ["pricing table", "plan cards", "tiers"],
        "testimonials": ["reviews", "social proof", "quotes", "customer stories"],
        "logos": ["logo cloud", "trusted by", "customer logos", "logo bar"],
        "stats": ["metrics", "numbers", "kpi row", "by the numbers"],
        "cta": ["call to action", "closing section", "sign up block", "final cta"],
        "footer": ["footer", "site foot", "bottom section"],
        "nav": ["navbar", "navigation", "header bar", "menu"],
        "faq": ["frequently asked", "questions", "accordion"],
        "gallery": ["image grid", "photo grid", "carousel", "slider", "lightbox"],
        "timeline": ["roadmap", "process steps", "how it works", "journey"],
        "team": ["about us", "people", "founders", "staff"],
        "contact": ["contact form", "get in touch", "enquiry"],
        "marquee": ["ticker", "scrolling text", "infinite scroll strip"],
        "comparison": ["vs table", "compare plans", "feature matrix"],
        "integrations": ["integration grid", "connects with", "app directory"],
    },
    # The visual register. This is what people usually mean by "make it look like X".
    "style": {
        "minimal": ["clean", "understated", "restrained", "whitespace", "sparse", "simple and elegant"],
        "swiss-editorial": ["swiss", "grid system", "editorial", "typographic", "magazine layout", "international style"],
        "brutalist": ["raw", "brutalism", "unstyled", "harsh", "concrete", "utilitarian"],
        "neo-brutalist": ["thick borders", "hard shadows", "chunky", "offset blocks", "sticker style"],
        "glassmorphic": ["glass", "frosted", "blur panels", "translucent", "liquid glass", "backdrop blur"],
        "luxury": ["premium", "high end", "elegant", "sophisticated", "refined", "boutique", "expensive looking"],
        "playful": ["fun", "friendly", "whimsical", "quirky", "bouncy", "cheerful", "cute"],
        "corporate": ["professional", "enterprise", "trustworthy", "conservative", "buttoned up"],
        "dark-tech": ["dark mode", "terminal aesthetic", "developer dark", "midnight", "hacker"],
        "retro-futurist": ["retrofuturism", "80s future", "chrome", "vhs", "synthwave", "analog future"],
        "cyberpunk": ["neon noir", "dystopian", "glitch", "hud", "blade runner"],
        "y2k": ["2000s", "bubble", "chrome text", "early web", "millennium"],
        "vintage": ["retro", "nostalgic", "aged paper", "classic", "heritage", "old school", "grain"],
        "organic": ["natural", "hand drawn", "soft shapes", "earthy", "botanical", "flowing"],
        "maximalist": ["busy", "layered", "loud", "dense", "collage", "expressive"],
        "claymorphic": ["clay", "soft 3d", "puffy", "squishy"],
        "editorial-photo": ["photography led", "image first", "full bleed photo", "art directed"],
    },
    # How it moves. The differentiator for anything MotionSites-adjacent.
    "motion": {
        "scroll-driven": ["scroll animation", "scrolly", "on scroll", "scroll triggered", "scrubbed"],
        "pinned-sections": ["pinned", "sticky sections", "page doesn't scroll", "scene to scene", "scrollytelling"],
        "parallax": ["depth on scroll", "layered scroll", "parallax"],
        "3d-webgl": ["3d", "three.js", "threejs", "webgl", "3d model", "glb", "r3f", "react three fiber",
                     "3d scene", "shader", "spline"],
        "reveal-on-scroll": ["fade in", "stagger in", "appear on scroll", "entrance animation"],
        "marquee": ["infinite scroll text", "ticker", "looping strip"],
        "magnetic-cursor": ["custom cursor", "cursor follow", "magnetic button", "hover magnet"],
        "hover-tilt": ["3d tilt", "card tilt", "hover depth"],
        "gradient-mesh": ["animated gradient", "mesh gradient", "aurora", "flowing gradient", "gradient blob"],
        "particle-field": ["particles", "starfield", "dot field", "noise field"],
        "text-effects": ["text scramble", "letter animation", "split text", "kinetic type", "typewriter"],
        "morphing": ["blob", "shape morph", "svg morph", "liquid"],
        "video-background": ["background video", "looping video", "video hero"],
        "static": ["no animation", "still", "no motion"],
    },
    "palette": {
        "dark": ["dark background", "black", "near black", "night"],
        "light": ["light background", "white", "bright", "airy"],
        "monochrome": ["black and white", "greyscale", "one colour", "achromatic"],
        "high-contrast": ["bold contrast", "stark", "punchy contrast"],
        "pastel": ["soft colours", "muted tones", "washed"],
        "neon": ["glow", "electric", "vivid", "fluorescent", "acid"],
        "earth-tone": ["warm neutrals", "sand", "clay", "terracotta", "olive", "beige"],
        "gradient-heavy": ["gradients everywhere", "colour wash", "duotone gradient"],
        "duotone": ["two colour", "split colour"],
        "jewel-tone": ["deep blue", "emerald", "burgundy", "rich colour"],
    },
    "layout": {
        "bento-grid": ["bento", "modular cards", "mosaic"],
        "split-screen": ["two column", "half and half", "side by side"],
        "centered": ["centred", "middle aligned", "symmetrical"],
        "asymmetric": ["off balance", "offset", "irregular", "broken grid"],
        "full-bleed": ["edge to edge", "full width", "immersive"],
        "sidebar": ["left nav", "fixed sidebar", "rail"],
        "magazine": ["multi column", "editorial grid", "spread"],
        "single-column": ["stacked", "narrow column", "reading column"],
        "horizontal-scroll": ["sideways scroll", "horizontal gallery"],
    },
}

# Tags within a facet that cannot both be true of one design. Prose routinely
# implies both - a light page whose description says "near-black text", a dark
# one that says "never pure white" - and without this the palette facet ends up
# carrying dark AND light on most designs, which makes filtering on it useless.
EXCLUSIVE_GROUPS: dict[str, list[set[str]]] = {
    "palette": [{"dark", "light"}],
}


def resolve_exclusives(facet: str, tags: Iterable[str], preferred: Iterable[str] = ()) -> list[str]:
    """Drop tags that contradict a preferred (authored) choice within a facet.

    When nothing is preferred the conflict is left alone: guessing which of two
    contradictory signals is right would be worse than admitting we cannot tell.
    """
    result = list(dict.fromkeys(tags))
    preferred_set = set(preferred)
    for group in EXCLUSIVE_GROUPS.get(facet, []):
        chosen = preferred_set & group
        if len(chosen) == 1:
            result = [t for t in result if t not in (group - chosen)]
    return result


# Words that carry no signal for design matching. Kept short on purpose: an
# aggressive stoplist throws away the adjectives that actually distinguish
# one design from another.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that", "these", "those",
    "as", "by", "from", "into", "about", "we", "our", "you", "your", "i", "my", "me", "us", "they",
    "them", "their", "he", "she", "his", "her", "will", "would", "can", "could", "should", "have",
    "has", "had", "do", "does", "did", "not", "no", "so", "than", "too", "very", "just", "also",
    "make", "made", "want", "need", "like", "using", "use", "get", "build", "create", "please",
}

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'+.#-]*")

# Built once at import: phrase -> set of "facet:tag" labels it implies.
_PHRASE_INDEX: dict[str, set[str]] = {}
for _facet, _tags in FACETS.items():
    for _tag, _phrases in _tags.items():
        label = f"{_facet}:{_tag}"
        for phrase in [_tag.replace("-", " "), _tag, *_phrases]:
            _PHRASE_INDEX.setdefault(phrase.lower(), set()).add(label)

# Longest phrases first so "machine learning" wins over "learning".
_PHRASES_BY_LEN: list[str] = sorted(_PHRASE_INDEX, key=lambda p: (-len(p.split()), -len(p)))

ALL_TAGS: list[str] = sorted({label for labels in _PHRASE_INDEX.values() for label in labels})


def facets() -> dict[str, list[str]]:
    """Facet -> its tag list. Used by `designice tags` and the MCP taxonomy tool."""
    return {facet: sorted(tags) for facet, tags in FACETS.items()}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens with stopwords removed."""
    return [t for t in _WORD_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def detect_tags(text: str) -> dict[str, list[str]]:
    """Read free text and return the controlled tags it implies, grouped by facet.

    Phrase matching is done on a space-padded lowercase string so that
    "ai" matches the word "ai" but not the "ai" inside "chair".
    """
    haystack = " " + re.sub(r"[^a-z0-9+#]+", " ", text.lower()).strip() + " "
    found: dict[str, set[str]] = {}
    for phrase in _PHRASES_BY_LEN:
        if f" {phrase} " in haystack:
            for label in _PHRASE_INDEX[phrase]:
                facet, tag = label.split(":", 1)
                found.setdefault(facet, set()).add(tag)
    return {facet: sorted(tags) for facet, tags in sorted(found.items())}


def flatten_tags(tags: dict[str, Iterable[str]]) -> list[str]:
    """{'industry': ['fintech']} -> ['industry:fintech']"""
    return sorted(f"{facet}:{tag}" for facet, vals in tags.items() for tag in vals)


def expansion_terms(text: str) -> list[str]:
    """Extra vocabulary implied by the text, for appending to an embedding input.

    Given "a site for my crypto lending startup" this yields the tag names
    (crypto-web3, fintech) plus their sibling trigger phrases, so the vector
    lands near designs that were described with entirely different words.
    """
    terms: list[str] = []
    for facet, tags in detect_tags(text).items():
        for tag in tags:
            terms.append(tag.replace("-", " "))
            terms.extend(FACETS[facet][tag][:6])
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
