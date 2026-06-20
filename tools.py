"""
tools.py

FitFindr tools — required core tools plus stretch-feature helpers.
Each function can be tested independently before wiring into agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe, ...)         → str
    create_fit_card(outfit, new_item)               → str
    compare_price(item)                             → str
    check_trends(size)                              → dict
"""

import json
import os
import re
import statistics

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_groq(system: str, user: str, temperature: float = 0.7) -> str:
    """Send a chat completion request to Groq and return the assistant text."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _listing_search_text(listing: dict) -> str:
    """Combine searchable listing fields into one lowercase string."""
    tags = " ".join(listing.get("style_tags", []))
    return f"{listing['title']} {listing['description']} {tags}".lower()


def _score_listing(listing: dict, keywords: list[str]) -> int:
    """Score a listing by keyword overlap across title, description, and tags."""
    if not keywords:
        return 1

    text = _listing_search_text(listing)
    score = 0
    for keyword in keywords:
        if keyword in text:
            score += 1
        if keyword in listing["title"].lower():
            score += 1
    return score


def _matches_size(listing: dict, size: str) -> bool:
    """Case-insensitive substring match for size filtering."""
    return size.upper() in listing["size"].upper()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    keywords = re.findall(r"\w+", description.lower())
    scored: list[tuple[int, dict]] = []

    for listing in load_listings():
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and not _matches_size(listing, size):
            continue

        score = _score_listing(listing, keywords)
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def _format_wardrobe_items(items: list[dict]) -> str:
    lines = []
    for item in items:
        tags = ", ".join(item.get("style_tags", []))
        notes = item.get("notes") or ""
        note_text = f" Notes: {notes}" if notes else ""
        lines.append(
            f"- {item['name']} ({item['category']}, colors: {', '.join(item['colors'])}, "
            f"tags: {tags}){note_text}"
        )
    return "\n".join(lines)


def suggest_outfit(
    new_item: dict,
    wardrobe: dict,
    style_profile: dict | None = None,
    trends: dict | None = None,
) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.
        style_profile: Optional saved preferences from prior sessions.
        trends: Optional trend snapshot from check_trends().

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    item_summary = (
        f"Title: {new_item['title']}\n"
        f"Description: {new_item['description']}\n"
        f"Category: {new_item['category']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Condition: {new_item['condition']}\n"
        f"Price: ${new_item['price']:.2f} on {new_item['platform']}"
    )

    items = wardrobe.get("items", [])
    context_blocks = []

    if style_profile and (style_profile.get("preferences") or style_profile.get("favorite_tags")):
        tag_text = ", ".join(style_profile.get("favorite_tags") or [])
        pref_text = style_profile.get("preferences") or ""
        context_blocks.append(
            "Saved style profile (from prior sessions):\n"
            f"- Preferences: {pref_text or 'none'}\n"
            f"- Favorite tags: {tag_text or 'none'}"
        )

    if trends and trends.get("summary"):
        tag_text = ", ".join(trends.get("trending_tags") or [])
        context_blocks.append(
            "Current trends for this size range:\n"
            f"- {trends['summary']}\n"
            f"- Hot tags: {tag_text}"
        )

    context_text = "\n\n".join(context_blocks)
    trend_instruction = (
        " Weave in at least one currently trending style element when it fits naturally."
        if trends and trends.get("trending_tags")
        else ""
    )
    profile_instruction = (
        " Honor the user's saved style preferences when choosing vibes and pairings."
        if style_profile and style_profile.get("preferences")
        else ""
    )

    if not items:
        system = (
            "You are a personal stylist for secondhand fashion. "
            "Give practical, specific outfit advice in 2–6 sentences."
            f"{profile_instruction}{trend_instruction}"
        )
        user = (
            f"The user has no wardrobe saved yet. Suggest 1–2 general outfit ideas "
            f"for this thrift find — describe what kinds of pieces would pair well "
            f"and the overall vibe, but do NOT reference items they already own.\n\n"
            f"New item:\n{item_summary}"
        )
    else:
        wardrobe_text = _format_wardrobe_items(items)
        system = (
            "You are a personal stylist for secondhand fashion. "
            "Suggest 1–2 complete outfits using the new thrift find plus specific "
            "pieces from the user's wardrobe. Name wardrobe items by their exact names."
            f"{profile_instruction}{trend_instruction}"
        )
        user = (
            f"New thrift find:\n{item_summary}\n\n"
            f"User's wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest 1–2 outfits that combine the new item with pieces from the wardrobe. "
            f"Keep it to 2–6 sentences."
        )

    if context_text:
        user = f"{context_text}\n\n{user}"

    result = _call_groq(system, user, temperature=0.7)
    if not result:
        raise RuntimeError("Groq returned an empty outfit suggestion.")
    return result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return "Can't create a fit card without an outfit suggestion."

    system = (
        "You write casual, authentic outfit captions for Instagram or TikTok. "
        "Sound like a real person sharing an OOTD — not a product listing."
    )
    user = (
        f"Write a 2–4 sentence fit card caption for this thrift find and outfit.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']:.2f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit suggestion: {outfit}\n\n"
        f"Requirements:\n"
        f"- Mention the item name, price, and platform naturally (once each)\n"
        f"- Capture the outfit vibe in specific terms\n"
        f"- Keep it casual and shareable"
    )

    result = _call_groq(system, user, temperature=0.9)
    if not result:
        raise RuntimeError("Groq returned an empty fit card caption.")
    return result


# ── Tool 4: compare_price (stretch) ───────────────────────────────────────────

def _find_comparables(item: dict) -> list[dict]:
    """Return listings comparable to item by category or overlapping style tags."""
    item_tags = set(item.get("style_tags") or [])
    comparables = []

    for listing in load_listings():
        if listing["id"] == item["id"]:
            continue

        same_category = listing["category"] == item["category"]
        shared_tags = item_tags & set(listing.get("style_tags") or [])
        if same_category or shared_tags:
            comparables.append(listing)

    return comparables


def compare_price(item: dict) -> str:
    """
    Estimate whether a listing's price is fair using comparable items in the dataset.

    Args:
        item: A listing dict from search_listings().

    Returns:
        A human-readable price assessment with reasoning. Never raises.
    """
    comparables = _find_comparables(item)
    if not comparables:
        return (
            f"No comparable listings in the dataset for '{item['title']}'. "
            "Can't assess whether ${:.2f} is fair.".format(item["price"])
        )

    prices = sorted(c["price"] for c in comparables)
    low, high = prices[0], prices[-1]
    median = statistics.median(prices)
    average = statistics.mean(prices)
    price = item["price"]

    if price <= median * 0.85:
        verdict = "Good deal"
    elif price <= median * 1.15:
        verdict = "Fair price"
    else:
        verdict = "Above typical"

    sample_titles = ", ".join(c["title"][:40] for c in comparables[:3])
    return (
        f"{verdict} — ${price:.2f} vs. ${median:.2f} median among {len(comparables)} "
        f"comparable {item['category']} listings (${low:.2f}–${high:.2f} range, "
        f"avg ${average:.2f}). Based on similar items like: {sample_titles}."
    )


# ── Tool 5: check_trends (stretch) ────────────────────────────────────────────

def _load_trends_data() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "trends.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _size_bucket(size: str | None) -> str:
    """Map a free-form size string to a trends.json bucket key."""
    if not size:
        return "default"

    upper = size.upper()
    for bucket in ("XL", "XS", "S", "M", "L"):
        if re.search(rf"\b{bucket}\b", upper):
            return bucket

    numeric = re.search(r"\b(\d+(?:\.\d+)?)\b", size)
    if numeric and numeric.group(1) in ("6", "7", "8", "9", "10", "11", "12"):
        return numeric.group(1)

    return "default"


def check_trends(size: str | None = None) -> dict:
    """
    Surface trending styles for the user's size range.

    Uses mock trend data in data/trends.json (simulated Depop/Instagram tag snapshot).

    Args:
        size: Optional size string from the user's query or listing.

    Returns:
        dict with keys: trending_tags (list[str]), summary (str), source (str), size_bucket (str)
    """
    data = _load_trends_data()
    bucket = _size_bucket(size)

    if bucket == "default":
        entry = data["default"]
    else:
        entry = data.get("size_buckets", {}).get(bucket, data["default"])

    return {
        "trending_tags": list(entry.get("trending_tags") or []),
        "summary": entry.get("summary", ""),
        "source": data.get("source", "mock trend data"),
        "size_bucket": bucket,
    }


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_empty_wardrobe, get_example_wardrobe

    print("=== search_listings tests ===\n")

    r1 = search_listings("vintage graphic tee", max_price=30.0)
    print(f"Test 1 — vintage graphic tee under $30: {len(r1)} results")
    if r1:
        print(f"  Top: {r1[0]['title']} (${r1[0]['price']})")

    r2 = search_listings("90s track jacket", size="M")
    print(f"\nTest 2 — 90s track jacket size M: {len(r2)} results")
    if r2:
        print(f"  Top: {r2[0]['title']} (size {r2[0]['size']})")

    r3 = search_listings("designer ballgown", size="XXS", max_price=5.0)
    print(f"\nTest 3 — designer ballgown XXS under $5: {len(r3)} results (expect 0)")

    print("\n=== suggest_outfit + create_fit_card (requires GROQ_API_KEY) ===\n")
    if r1:
        item = r1[0]
        outfit = suggest_outfit(item, get_example_wardrobe())
        print(f"Outfit suggestion:\n{outfit}\n")
        fit_card = create_fit_card(outfit, item)
        print(f"Fit card:\n{fit_card}\n")

        empty_outfit = suggest_outfit(item, get_empty_wardrobe())
        print(f"Empty wardrobe suggestion:\n{empty_outfit}\n")

        error_card = create_fit_card("", item)
        print(f"Empty outfit guard: {error_card}")

        print(f"\nPrice check:\n{compare_price(item)}")
        print(f"\nTrends (size L):\n{check_trends('L')}")
