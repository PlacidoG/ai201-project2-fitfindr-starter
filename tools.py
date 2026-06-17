"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    relax_search(description, size, max_price)      → dict | None
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq model used by the LLM-backed tools (suggest_outfit, create_fit_card).
_GROQ_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _describe_listing(item: dict) -> str:
    """Format a listing dict into a single readable line for an LLM prompt."""
    tags = ", ".join(item.get("style_tags", []))
    colors = ", ".join(item.get("colors", []))
    brand = item.get("brand") or "unbranded"
    return (
        f'"{item["title"]}" — a {item["category"]} ({brand}, ${item["price"]:.2f}) '
        f"from {item['platform']}; colors: {colors}; style: {tags}"
    )


def _describe_wardrobe_item(item: dict) -> str:
    """Format a wardrobe item dict into a single readable line for an LLM prompt."""
    tags = ", ".join(item.get("style_tags", []))
    colors = ", ".join(item.get("colors", []))
    line = f'{item["name"]} (a {item["category"]}; colors: {colors}; style: {tags})'
    if item.get("notes"):
        line += f" — {item['notes']}"
    return line


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

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Tokenize the description into lowercase keywords, dropping 1-char tokens.
    keywords = [w for w in re.findall(r"[a-z0-9]+", description.lower()) if len(w) > 1]

    scored = []
    for listing in listings:
        # Price filter (inclusive).
        if max_price is not None and listing["price"] > max_price:
            continue
        # Size filter — case-insensitive substring (e.g. "M" matches "S/M").
        if size is not None and size.lower() not in listing["size"].lower():
            continue

        # Build a searchable token set from the relevant text fields.
        haystack = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing["category"],
            listing["brand"] or "",
        ]).lower()
        tokens = set(re.findall(r"[a-z0-9]+", haystack))

        # Score by how many distinct keywords appear; drop listings with no overlap.
        score = sum(1 for kw in keywords if kw in tokens)
        if score == 0:
            continue
        scored.append((score, listing))

    # Highest score first; stable sort preserves dataset order on ties.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    # .get() so a malformed or missing wardrobe never raises — empty just
    # routes to the general-advice branch below.
    items = wardrobe.get("items", [])
    item_desc = _describe_listing(new_item)

    system = (
        "You are a practical personal stylist for secondhand fashion. "
        "Give concrete, wearable outfit ideas in a friendly, concise tone."
    )

    if not items:
        # Empty wardrobe: general styling advice, no wardrobe references.
        user = (
            f"Someone is considering this thrifted item:\n{item_desc}\n\n"
            "They haven't shared their wardrobe yet. Suggest general styling ideas: "
            "what kinds of pieces pair well with it, and what vibe and occasions it "
            "suits. Keep it to a short paragraph or a few bullet points."
        )
    else:
        # Populated wardrobe: specific outfits using named pieces.
        wardrobe_lines = "\n".join(f"- {_describe_wardrobe_item(w)}" for w in items)
        user = (
            f"Someone is considering this thrifted item:\n{item_desc}\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that combine the new item with specific, "
            "named pieces from their wardrobe. Reference the wardrobe pieces by name "
            "and keep it concise."
        )

    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


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

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: empty or whitespace-only outfit → descriptive error string, no LLM call.
    if not outfit or not outfit.strip():
        return (
            "Can't create a fit card without an outfit suggestion. "
            "Try a different search or add items to your wardrobe."
        )

    client = _get_groq_client()
    item_desc = _describe_listing(new_item)

    system = (
        "You write short, punchy social-media captions for secondhand fashion finds. "
        "Your captions sound like a real OOTD post — casual, authentic, a little playful — "
        "never like a product listing."
    )
    user = (
        f"Item:\n{item_desc}\n\n"
        f"Outfit idea:\n{outfit}\n\n"
        "Write a 2-4 sentence Instagram/TikTok caption for this look. Mention the item "
        f"name, its price (${new_item['price']:.2f}), and where it's from "
        f"({new_item['platform']}) naturally — once each. Capture the vibe in specific terms."
    )

    # Higher temperature than suggest_outfit for caption variety.
    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=1.0,
    )
    return response.choices[0].message.content.strip()




# ── Tool 4: relax_search ──────────────────────────────────────────────────────

def relax_search(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> dict | None:
    """
    Loosen the original search filters so the agent can retry after an empty
    search_listings() result.

    Returns a new filter dict ({"description", "size", "max_price"}) ready to
    splat into search_listings(**relaxed). Returns None if nothing can be
    loosened further — the caller should then tell the user no matches were
    found and ask them to broaden or change their query.
    """
    relaxed = {"description": description, "size": size, "max_price": max_price}
    changed = False

    # 1. Drop the size filter — the most common over-constraint.
    if size is not None:
        relaxed["size"] = None
        changed = True

    # 2. Raise the price ceiling by 50%.
    if max_price is not None:
        relaxed["max_price"] = round(max_price * 1.5, 2)
        changed = True

    # 3. Broaden the description to its head noun (last keyword).
    tokens = re.findall(r"[a-z0-9]+", (description or "").lower())
    if len(tokens) > 1:
        relaxed["description"] = tokens[-1]
        changed = True

    return relaxed if changed else None
