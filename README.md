# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── agent.py                   # Planning loop and query parsing
├── app.py                     # Gradio UI
├── tools.py                   # search_listings, suggest_outfit, create_fit_card
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Agent spec and architecture diagram
└── requirements.txt           # Python dependencies
```

## Setup

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Note:** On some Macs, `python` points to an older version (e.g. 3.9). Use `python3` to create the venv — Gradio 6.x requires Python 3.10+.

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Tool Inventory

Your README submission must document each tool's name, inputs, and return value. **These must exactly match your actual function signatures in `tools.py`.** Your documented interfaces will be checked against your actual function signatures in `tools.py` — if the parameter count or types contradict what's in the code, you may not receive full credit for that tool.

### `search_listings(description, size=None, max_price=None) → list[dict]`

- **`description`** (`str`): Keywords describing what the user wants (e.g., `"vintage graphic tee"`).
- **`size`** (`str | None`): Optional size filter; case-insensitive substring match. `None` skips size filtering.
- **`max_price`** (`float | None`): Optional maximum price (inclusive). `None` skips price filtering.
- **Returns:** `list[dict]` — matching listings sorted by relevance (best first). Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` if nothing matches.

### `suggest_outfit(new_item, wardrobe) → str`

- **`new_item`** (`dict`): A listing dict (the thrift find the user is considering).
- **`wardrobe`** (`dict`): Wardrobe object with an `items` key (list of wardrobe item dicts). May be empty.
- **Returns:** `str` — 1–2 outfit suggestions in plain prose. Always non-empty; uses general styling advice when the wardrobe is empty.

### `create_fit_card(outfit, new_item) → str`

- **`outfit`** (`str`): Outfit suggestion text from `suggest_outfit()`.
- **`new_item`** (`dict`): The listing dict for the thrift find.
- **Returns:** `str` — 2–4 sentence social-media caption. Returns an error message string (not an exception) if `outfit` is empty or whitespace-only.

---

## Planning Loop

The agent runs a **fixed sequential pipeline** in `run_agent(query, wardrobe)` — tool order never changes. Decisions are made by checking return values and session state, not by an LLM planner.

1. **Parse the query** — `parse_query()` uses regex to extract `description`, optional `size`, and optional `max_price` from natural language (e.g. `"vintage graphic tee under $30"` → description + `max_price=30.0`). Stored in `session["parsed"]`.

2. **Search first** — Always call `search_listings()` with parsed parameters. Results stored in `session["search_results"]`.

3. **Branch on search results** — If the list is empty, set `session["error"]` with a helpful message and **return immediately**. Do not call `suggest_outfit` or `create_fit_card`.

4. **Select top match** — If results exist, set `session["selected_item"] = search_results[0]` (highest relevance score).

5. **Suggest outfit** — Call `suggest_outfit(selected_item, wardrobe)`. Store string in `session["outfit_suggestion"]`. On Groq API failure, set error and return.

6. **Create fit card** — Call `create_fit_card(outfit_suggestion, selected_item)`. Store in `session["fit_card"]`. If outfit was blank or API fails, set error and return.

7. **Done** — Return session. Success means `error` is `None` and all three outputs are populated.

The loop is complete when the session dict is returned — either early (error set) or with listing, outfit, and fit card filled in.

---

## State Management

All state for one user interaction lives in a single **session dict** (`_new_session()` in `agent.py`). Tools are stateless; the planning loop passes data between them via session fields:

| Field | Purpose |
|-------|---------|
| `query` | Original user input (reference) |
| `parsed` | `{description, size, max_price}` from regex parsing |
| `search_results` | Full list from `search_listings()` |
| `selected_item` | Top listing dict — input to steps 2 and 3 |
| `wardrobe` | User's wardrobe dict — input to `suggest_outfit()` |
| `outfit_suggestion` | String from `suggest_outfit()` — input to `create_fit_card()` |
| `fit_card` | Final caption string |
| `error` | User-facing message if interaction ended early; check this first |

**Data flow:** `query` → `parsed` → `search_results` → `selected_item` → `outfit_suggestion` → `fit_card`

The Gradio UI (`handle_query()` in `app.py`) calls `run_agent()`, checks `session["error"]`, and maps the three success fields to the three output panels.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"` (Example wardrobe selected in the UI)

**Pre-step — Query parsing (in `agent.py`, not a tool):**
- `parse_query()` extracts `description="vintage graphic tee"`, `max_price=30.0`, `size=None` via regex and stores them in `session["parsed"]`.

**Step 1 — Tool called:**
- **Tool:** `search_listings`
- **Input:** `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- **Why this tool:** The user wants to see available secondhand listings before any styling advice. Search must run first.
- **Output:** List of matching listings. Top result selected: **Graphic Tee — 2003 Tour Bootleg Style** (`lst_006`) — $24.00, Depop, good condition, size L, style tags include `vintage`, `graphic tee`, `band tee`.

**Step 2 — Tool called:**
- **Tool:** `suggest_outfit`
- **Input:** `new_item=<lst_006 dict>`, `wardrobe=get_example_wardrobe()` (10 items including baggy jeans, combat boots, denim jacket)
- **Why this tool:** User asked what to buy; once a listing is found, the agent pairs it with pieces from the user's wardrobe.
- **Output:** Styling suggestion naming specific wardrobe pieces, e.g. pairing the tee with baggy straight-leg jeans, black combat boots, and a vintage black denim jacket for a grunge look.

**Step 3 — Tool called:**
- **Tool:** `create_fit_card`
- **Input:** `outfit=<styling text from step 2>`, `new_item=<lst_006 dict>`
- **Why this tool:** Produces a shareable caption summarizing the find and outfit for the fit card panel.
- **Output:** Casual caption mentioning the item name, $24.00 price, and Depop platform, e.g. *"Just scored this epic Graphic Tee for $24.00 on Depop… paired it with my fave baggy straight-leg jeans and black combat boots for a grunge-inspired look."*

**Final output to user:** Three Gradio panels — (1) formatted listing details for `lst_006`, (2) outfit styling advice, (3) fit card caption. All three populated; `session["error"]` is `None`.

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match after filtering/scoring (returns `[]`) | Sets `session["error"]` to *"No listings matched your search. Try broadening your keywords, raising your price limit, or removing the size filter."* Returns immediately. UI shows the message in the listing panel; outfit and fit card panels stay empty. Does **not** call `suggest_outfit` or `create_fit_card`. |
| `suggest_outfit` | Wardrobe is empty (`items` is `[]`) | **Not treated as an error.** Tool switches to a general-styling prompt and returns normal advice. Agent proceeds to `create_fit_card`. |
| `suggest_outfit` | Groq API call fails (network error, rate limit, missing API key) | Sets `session["error"]` to *"Couldn't generate outfit suggestions right now. Please try again."* Returns without calling `create_fit_card`. |
| `create_fit_card` | Outfit input is empty or whitespace-only | Tool returns *"Can't create a fit card without an outfit suggestion."* Agent copies this into `session["error"]` and returns. |
| `create_fit_card` | Groq API call fails | Sets `session["error"]` to *"Couldn't generate your fit card right now. Please try again."* Returns session with partial results (listing and outfit may exist, but fit card generation failed). |

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing the tool specs with exact parameter types and return shapes before coding made it straightforward to implement `tools.py` without guessing at interfaces. The step-by-step planning loop pseudocode (especially the early-return when `search_results` is empty and the try/except blocks for Groq calls) mapped directly onto `run_agent()` in `agent.py`, so there was no ambiguity about control flow when wiring the three tools together.

**One divergence from your spec, and why:**

The spec listed `in size M` as an optional phrasing in examples but the original regex only documented `size M`. During implementation I extended the size pattern to also match `in size M` (as in the Gradio example query *"90s track jacket in size M"*) so natural-language queries from the UI parse correctly without requiring users to drop the word "in."

---

## AI Usage

### Instance 1 — Implementing `search_listings` in `tools.py`

- **Input given to AI:** Tool 1 block from `planning.md` (inputs, return value, failure mode) and the `load_listings()` docstring from `utils/data_loader.py`.
- **What AI produced:** A function that filters by price/size, scores listings by keyword overlap against title/description/style_tags, and sorts by score.
- **What I changed before using it:** Verified against three test queries from the AI Tool Plan (`vintage graphic tee under $30`, `90s track jacket size M`, impossible ballgown query). Confirmed title matches were weighted slightly higher for better ranking of `lst_006`.

### Instance 2 — Implementing `run_agent()` in `agent.py`

- **Input given to AI:** Planning Loop and State Management sections from `planning.md`, plus the Architecture diagram and `_new_session()` / `run_agent()` stubs.
- **What AI produced:** `parse_query()` with regex patterns and a `run_agent()` function matching the step-by-step conditional logic (early return on empty search, try/except for Groq calls).
- **What I changed before using it:** Extended the size regex to support `in size M` (not in the original spec). Ran `python agent.py` to confirm both happy path and no-results path before wiring `handle_query()` in `app.py`.

---

## Stretch Features

All four stretch features are implemented:

| Feature | Where | Demo tip |
|---------|-------|----------|
| **Price comparison** | `compare_price()` in `tools.py` | Shown under listing as "💰 Price check" |
| **Style profile memory** | `utils/style_profile.py` + Gradio textbox | Save prefs in first query; second query uses them without re-entry |
| **Trend awareness** | `check_trends()` + `data/trends.json` | Outfit panel shows trend summary; LLM prompt weaves in hot tags |
| **Retry with fallback** | `search_with_retry()` in `agent.py` | Try `vintage graphic tee size XXS under $30` — loosens size filter |

### `compare_price(item) → str`

Finds comparables in the dataset by matching **category** or **overlapping style_tags**, then compares the item's price to the median/average/range. Returns a verdict: **Good deal**, **Fair price**, or **Above typical**, with sample comparable titles.

### Style profile memory

Preferences persist in `data/style_profile.json` (gitignored). Updated when:
- The user fills in the **Style preferences** textbox in the UI, or
- A successful query contains *"I mostly wear / I like / my style is ..."* (auto-extracted).

On the next run, `run_agent()` loads the profile and passes it to `suggest_outfit()` even if the user leaves the textbox blank.

### `check_trends(size=None) → dict`

Reads mock trend snapshots from `data/trends.json` — labeled as a simulated Depop/Instagram tag feed. Maps the user's size to a bucket (`M`, `L`, `8`, etc.) and returns trending tags + a one-line summary. The outfit LLM prompt is instructed to incorporate trending elements when they fit naturally.

### Retry logic

`search_with_retry()` in `agent.py`:
1. Search with all parsed filters.
2. If empty and size was set → retry without size, note adjustment.
3. If still empty and price was set → retry without price (and size), note adjustments.
4. If still empty → set error and stop (no outfit/fit card).

---

## How to Run

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python app.py
```

Open the URL printed in the terminal (usually `http://localhost:7860`). Try example queries or:
- **Happy path:** `vintage graphic tee under $30` with Example wardrobe
- **Retry demo:** `vintage graphic tee size XXS under $30` — agent loosens size filter
- **Style memory:** enter prefs in the style box (or say "I mostly wear baggy jeans..."), then run a second query without re-describing style
- **No results:** `designer ballgown size XXS under $5`
- **Empty wardrobe:** any successful query with "Empty wardrobe (new user)" selected

CLI tests without the UI:
```bash
python tools.py    # search tests + optional Groq calls
python agent.py    # happy path + no-results path
```

---

## Demo Video

Record a 3–5 minute walkthrough covering:
- A complete interaction using all 3 tools (happy path)
- Narration of what the agent does at each step and how state passes between tools
- At least one failure (e.g. no-results query) and the graceful error response

**Script:** See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a timed, word-for-word recording guide (~4 min).

> **Status:** Record and submit separately — not included in the repo.

---
