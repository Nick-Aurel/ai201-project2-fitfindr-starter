"""
agent.py

The FitFindr planning loop. Orchestrates tools in response to a natural language
user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import (
    check_trends,
    compare_price,
    create_fit_card,
    search_listings,
    suggest_outfit,
)
from utils.style_profile import load_style_profile, merge_style_profile

NO_RESULTS_ERROR = (
    "No listings matched your search, even after loosening filters. "
    "Try broadening your keywords or raising your price limit."
)
OUTFIT_ERROR = "Couldn't generate outfit suggestions right now. Please try again."
FIT_CARD_ERROR = "Couldn't generate your fit card right now. Please try again."

_STYLE_HINT_PATTERN = re.compile(
    r"(?:i (?:mostly )?(?:wear|like|love|prefer)|my style is)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

_PRICE_PATTERN = re.compile(
    r"(?:under|below|max)\s+\$?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(
    r"(?:in\s+)?size\s+(US\s+\d+(?:\.\d+)?|\d+(?:\.\d+)?|[A-Za-z]+(?:/[A-Za-z]+)?(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)
_PRICE_STRIP = re.compile(
    r"(?:under|below|max)\s+\$?\s*\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_SIZE_STRIP = re.compile(
    r"(?:in\s+)?size\s+(?:US\s+\d+(?:\.\d+)?|\d+(?:\.\d+)?|[A-Za-z]+(?:/[A-Za-z]+)?(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)


def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "search_adjustments": [],
        "selected_item": None,
        "price_assessment": None,
        "trends": None,
        "style_profile": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


def parse_query(query: str) -> dict:
    """Extract description, size, and max_price from a natural-language query."""
    max_price = None
    price_match = _PRICE_PATTERN.search(query)
    if price_match:
        max_price = float(price_match.group(1))

    size = None
    size_match = _SIZE_PATTERN.search(query)
    if size_match:
        size = size_match.group(1).strip()

    description = _PRICE_STRIP.sub("", query)
    description = _SIZE_STRIP.sub("", description)
    description = re.sub(r"\s+", " ", description).strip(" ,.-")
    if not description:
        description = query.strip()

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _extract_style_hint(query: str) -> str:
    """Pull free-text style preferences from phrases like 'I mostly wear ...'."""
    match = _STYLE_HINT_PATTERN.search(query)
    if not match:
        return ""
    return match.group(1).strip(" .")


def search_with_retry(
    description: str,
    size: str | None,
    max_price: float | None,
) -> tuple[list[dict], list[str]]:
    """
    Search listings, retrying with loosened constraints if nothing matches.

    Returns:
        (results, adjustments) where adjustments describes what changed.
    """
    results = search_listings(description, size=size, max_price=max_price)
    adjustments: list[str] = []

    if results:
        return results, adjustments

    if size is not None:
        results = search_listings(description, size=None, max_price=max_price)
        if results:
            adjustments.append(f"removed size filter (was '{size}')")
            return results, adjustments

    if max_price is not None:
        results = search_listings(description, size=None, max_price=None)
        if results:
            if size is not None:
                adjustments.append(f"removed size filter (was '{size}')")
            adjustments.append(f"removed price limit (was ${max_price:.2f})")
            return results, adjustments

    return [], adjustments


def run_agent(
    query: str,
    wardrobe: dict,
    style_profile: dict | None = None,
    save_style_from_query: bool = True,
) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single interaction.

    Args:
        query: Natural language user request.
        wardrobe: User's wardrobe dict.
        style_profile: Optional saved preferences; loads from disk if omitted.
        save_style_from_query: If True, merge style hints from the query after success.

    Returns:
        Completed session dict. Check session["error"] first on failure.
    """
    session = _new_session(query, wardrobe)
    session["parsed"] = parse_query(query)
    session["style_profile"] = style_profile if style_profile is not None else load_style_profile()

    session["search_results"], session["search_adjustments"] = search_with_retry(
        description=session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )

    if not session["search_results"]:
        session["error"] = NO_RESULTS_ERROR
        return session

    session["selected_item"] = session["search_results"][0]
    session["price_assessment"] = compare_price(session["selected_item"])

    trend_size = session["parsed"]["size"] or session["selected_item"].get("size")
    session["trends"] = check_trends(trend_size)

    try:
        session["outfit_suggestion"] = suggest_outfit(
            new_item=session["selected_item"],
            wardrobe=session["wardrobe"],
            style_profile=session["style_profile"],
            trends=session["trends"],
        )
    except Exception:
        session["error"] = OUTFIT_ERROR
        return session

    try:
        session["fit_card"] = create_fit_card(
            outfit=session["outfit_suggestion"],
            new_item=session["selected_item"],
        )
    except Exception:
        session["error"] = FIT_CARD_ERROR
        return session

    if session["fit_card"].startswith("Can't create"):
        session["error"] = session["fit_card"]
        return session

    if save_style_from_query:
        hint = _extract_style_hint(query)
        if hint:
            session["style_profile"] = merge_style_profile(hint)

    return session


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe
    from utils.style_profile import clear_style_profile

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        if session["search_adjustments"]:
            print(f"Search adjustments: {session['search_adjustments']}")
        print(f"\nPrice check: {session['price_assessment']}")
        print(f"\nTrends: {session['trends']['summary']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== Retry path: strict size, then loosen ===\n")
    session_retry = run_agent(
        query="vintage graphic tee size XXS under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session_retry["error"]:
        print(f"Error: {session_retry['error']}")
    else:
        print(f"Found: {session_retry['selected_item']['title']}")
        print(f"Adjustments: {session_retry['search_adjustments']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

    print("\n\n=== Style profile memory ===\n")
    clear_style_profile()
    run_agent(
        query="vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers.",
        wardrobe=get_example_wardrobe(),
    )
    session3 = run_agent(
        query="90s track jacket under $50",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Saved profile used: {session3['style_profile'].get('preferences')}")
