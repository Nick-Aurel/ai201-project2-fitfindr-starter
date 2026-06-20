"""
Persist user style preferences across FitFindr sessions.

Stored locally in data/style_profile.json (gitignored).
"""

import json
import os
from datetime import datetime, timezone

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_PROFILE_PATH = os.path.join(_DATA_DIR, "style_profile.json")

_EMPTY_PROFILE = {
    "preferences": "",
    "favorite_tags": [],
    "updated_at": None,
}


def _profile_path() -> str:
    return _PROFILE_PATH


def load_style_profile() -> dict:
    """Load saved style preferences, or return an empty profile."""
    path = _profile_path()
    if not os.path.exists(path):
        return dict(_EMPTY_PROFILE)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = dict(_EMPTY_PROFILE)
    profile.update(data)
    profile["favorite_tags"] = list(profile.get("favorite_tags") or [])
    return profile


def save_style_profile(profile: dict) -> dict:
    """Write style preferences to disk and return the saved profile."""
    path = _profile_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload = {
        "preferences": (profile.get("preferences") or "").strip(),
        "favorite_tags": sorted(set(profile.get("favorite_tags") or [])),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload


def merge_style_profile(preferences_text: str, tags: list[str] | None = None) -> dict:
    """Merge new preference text/tags into the saved profile."""
    profile = load_style_profile()
    text = (preferences_text or "").strip()

    if text:
        if profile["preferences"]:
            if text.lower() not in profile["preferences"].lower():
                profile["preferences"] = f"{profile['preferences']}; {text}"
        else:
            profile["preferences"] = text

    for tag in tags or []:
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in profile["favorite_tags"]:
            profile["favorite_tags"].append(cleaned)

    return save_style_profile(profile)


def clear_style_profile() -> dict:
    """Reset saved preferences."""
    return save_style_profile(dict(_EMPTY_PROFILE))


def profile_summary(profile: dict | None) -> str:
    """One-line summary for UI display."""
    if not profile:
        return ""

    parts = []
    if profile.get("preferences"):
        parts.append(profile["preferences"])
    if profile.get("favorite_tags"):
        parts.append("tags: " + ", ".join(profile["favorite_tags"]))

    return " · ".join(parts)
