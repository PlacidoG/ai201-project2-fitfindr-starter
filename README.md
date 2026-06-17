# FitFindr

FitFindr is a thrift-shopping assistant that takes a natural-language query, searches mock secondhand listings, and returns an outfit suggestion plus a shareable social-media caption. It is built as an agentic planning loop using four Python tools and a Gradio web interface backed by the Groq (llama-3.3-70b-versatile) LLM.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

---

## Tool Inventory

### `search_listings`

# 2. Find me a cool vintage denim jacket under $60 to go with my grey hoodie


# 1.Find me an authentic White Balenciaga leather jacket in size Small for under $15 to wear over my grey hoodie.


# 3. 

```python
search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]
```

| Parameter | Type | Description |
|---|---|---|
| `description` | `str` | Keywords describing the item (e.g., "vintage graphic tee") |
| `size` | `str \| None` | Size filter; case-insensitive substring match — "M" matches "S/M" |
| `max_price` | `float \| None` | Inclusive price ceiling; omit to skip price filtering |

**Returns:** `list[dict]` — matching listing dicts sorted by keyword relevance score, highest first. Returns an empty list on no match; never raises.

**Purpose:** Deterministic keyword-score search over `data/listings.json`. Tokenizes `description`, scores each listing by counting how many distinct keywords appear in its title, description, style tags, colors, category, and brand fields. No LLM involved.

---

### `suggest_outfit`

```python
suggest_outfit(new_item: dict, wardrobe: dict) -> str
```

| Parameter | Type | Description |
|---|---|---|
| `new_item` | `dict` | A listing dict (the thrifted item the user is considering) |
| `wardrobe` | `dict` | Wardrobe dict with an `items` key containing a list of wardrobe item dicts; may be empty |

**Returns:** `str` — non-empty outfit suggestion. Returns general styling advice if the wardrobe is empty, or 1–2 specific outfit combinations using named wardrobe pieces if populated.

**Purpose:** Groq LLM call (temperature 0.7) that acts as a personal stylist. Branches on wardrobe state: empty wardrobe → general pairing advice; populated wardrobe → specific outfits referencing named pieces by name.

---

### `create_fit_card`

```python
create_fit_card(outfit: str, new_item: dict) -> str
```

| Parameter | Type | Description |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit` |
| `new_item` | `dict` | The listing dict for the thrifted item |

**Returns:** `str` — 2–4 sentence Instagram/TikTok caption that mentions the item name, price, and platform naturally (once each). Returns a descriptive error string (no LLM call) if `outfit` is empty or whitespace.

**Purpose:** Groq LLM call (temperature 1.0, higher than `suggest_outfit`) that generates a casual OOTD-style caption. Higher temperature keeps captions varied rather than formulaic across repeated calls.

---

### `relax_search`

```python
relax_search(description: str, size: str | None = None, max_price: float | None = None) -> dict | None
```

| Parameter | Type | Description |
|---|---|---|
| `description` | `str` | Original search description |
| `size` | `str \| None` | Original size filter |
| `max_price` | `float \| None` | Original max price ceiling |

**Returns:** `dict | None` — a new filter dict `{"description", "size", "max_price"}` ready to unpack into `search_listings(**relaxed)`, or `None` if no loosening is possible (all three relaxation moves are already exhausted).

**Purpose:** Loosens over-constrained filters in this order: (1) drop the size filter, (2) raise the price ceiling by 50%, (3) narrow the description to its last keyword. Enables the agent to retry after an empty search result before giving up.

---

## How the Planning Loop Works

The main entry point is `run_agent(query, wardrobe)` in `agent.py`. It runs a 7-step pipeline with one conditional retry branch on the search step — there is no unbounded loop.

**Step 1 — Initialize**
`_new_session(query, wardrobe)` creates the session dict with all output fields set to `None`.

**Step 2 — Parse**
`_parse_query(query)` uses regex to extract `description`, `size`, and `max_price` from the natural-language query. It strips conversational filler words ("looking for", "want", "please", etc.) and drops single-character tokens. No LLM call — fully deterministic.

**Step 3 — Search with relax-and-retry**
```
call search_listings(**parsed)
  └─ results empty?
       ├─ yes → call relax_search(**parsed)
       │         ├─ returns None  → set session["error"], return early
       │         └─ returns dict  → store in session["relaxed"]
       │                            retry search_listings(**relaxed)
       │                              └─ still empty → set session["error"], return early
       └─ no  → store results in session["search_results"], continue
```
The agent attempts exactly one retry. If both the original and relaxed searches return nothing, it sets `session["error"]` and exits — no further steps run.

**Step 4 — Select**
`session["selected_item"] = results[0]` — the top relevance-ranked listing.

**Step 5 — Outfit suggestion**
`suggest_outfit(selected_item, wardrobe)` → stored in `session["outfit_suggestion"]`. Empty wardrobe is handled internally; no branching needed here.

**Step 6 — Fit card**
`create_fit_card(outfit_suggestion, selected_item)` → stored in `session["fit_card"]`. Empty outfit is handled internally via guard string.

**Step 7 — Return**
The completed session dict is returned. The caller checks `session["error"]` first; if it is not `None`, the downstream fields (`outfit_suggestion`, `fit_card`) will be `None`.

---

## State Management

A single `session` dict is the sole source of truth for one user interaction. It is initialized by `_new_session()` and mutated in-place through each step.

| Key | Type | Populated in | Purpose |
|---|---|---|---|
| `query` | `str` | init | original user input, unchanged throughout |
| `parsed` | `dict` | Step 2 | `{"description", "size", "max_price"}` extracted by regex |
| `search_results` | `list[dict]` | Step 3 | all matching listings after search (original or relaxed) |
| `relaxed` | `dict \| None` | Step 3 (conditional) | loosened filter params; only set if a retry was needed |
| `selected_item` | `dict \| None` | Step 4 | the top-ranked listing, passed into Steps 5 and 6 |
| `wardrobe` | `dict` | init | user's wardrobe, passed through unchanged |
| `outfit_suggestion` | `str \| None` | Step 5 | text returned by `suggest_outfit` |
| `fit_card` | `str \| None` | Step 6 | caption returned by `create_fit_card` |
| `error` | `str \| None` | Step 3 | set on early exit; all downstream fields remain `None` |

State is passed between tool calls by reading directly from the session dict — for example, `suggest_outfit(session["selected_item"], session["wardrobe"])` — so each tool receives exactly what the previous step produced. There is no global state; each call to `run_agent()` gets a fresh session.

---

## Error Handling Strategy

**`search_listings`** — Returns `[]` on any non-match; never raises an exception. The agent catches an empty return and calls `relax_search()` before setting an error. Concrete example from testing: the query `"designer ballgown size XXS under $5"` returns no results on the first call. `relax_search()` drops the size filter and raises the ceiling to $7.50. If `search_listings(**relaxed)` is also empty, the agent sets `session["error"] = "No listings found … even after broadening the search."` and returns without calling the LLM tools.

**`suggest_outfit`** — Uses `wardrobe.get("items", [])` so a missing `items` key never raises a `KeyError`. An empty list routes to a different LLM prompt (general styling advice) rather than failing silently or erroring. Covered by `test_suggest_outfit_empty_wardrobe_does_not_crash` in `tests/test_tools.py`.

**`create_fit_card`** — Guards at the top: `if not outfit or not outfit.strip()` returns the descriptive string `"Can't create a fit card without an outfit suggestion. Try a different search or add items to your wardrobe."` — no LLM call is made. This prevents a wasted API call and a nonsense caption. Covered by `test_create_fit_card_empty_outfit_returns_error_string` and `test_create_fit_card_whitespace_outfit_returns_error_string`.

**`relax_search`** — Returns `None` when all three relaxation moves are already exhausted (single-word description, no size constraint, no price ceiling). The agent treats `None` as a terminal signal and immediately sets `session["error"]` with the message "the search couldn't be loosened further."

---

## Spec Reflection

**One way the spec helped:** The error-handling table in `planning.md` explicitly defined three failure modes — empty search results, empty wardrobe, empty outfit string — before any code was written. Having the contracts documented upfront meant each tool had a clear expectation for graceful degradation (return an empty list, fall back to a different prompt, return a descriptive error string) rather than raising exceptions. This made the agent loop significantly simpler to write because failure was never surprising.

**One way implementation diverged:** `relax_search` was listed as an optional extra tool in the original `planning.md` diagram. The initial spec showed the search step branching directly to an error message on any empty result. During implementation this was replaced with a mandatory relax-and-retry step: `relax_search()` loosens the filters and `search_listings()` is called a second time before giving up. The change was driven by practical usability — a single-shot search that errors on any over-specified filter (a common occurrence with thrift queries where size and budget are often too tight) would frustrate real users immediately.

---

## AI Usage

**Instance 1 — Adding the relax-and-retry loop**
The AI's initial planning diagram in `planning.md` showed the search step branching directly to an error message when no results were found. I overrode this by adding `relax_search` as a required tool and inserting the relax-and-retry step into the agent loop. The revised flow drops the size filter, raises the price ceiling by 50%, and narrows the description to its last keyword before retrying — so a real query like "vintage jacket size S under $20" gets a second chance before the agent gives up and asks the user to change their search.

**Instance 2 — Constraining fit card length**
The AI's initial `create_fit_card` prompt did not specify a length limit, and early test outputs produced multi-paragraph captions that did not resemble real social media posts. I overrode this by adding an explicit "2–4 sentence" constraint to the LLM prompt and raising the temperature to 1.0 to keep captions varied rather than formulaic. The constraint was grounded in real platform norms — Instagram and TikTok captions are short by convention, and a wall of text defeats the purpose of a shareable fit card.

---

## Dataset Reference

`data/listings.json` — 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

`data/wardrobe_schema.json` — wardrobe format definition, a 10-item example wardrobe, and an empty wardrobe template.

```python
from utils.data_loader import load_listings, get_example_wardrobe, get_empty_wardrobe
```
