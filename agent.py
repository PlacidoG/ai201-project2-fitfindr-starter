"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
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

from tools import search_listings, suggest_outfit, create_fit_card, relax_search


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "relaxed": None,             # adjusted filters, if the search was loosened
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

# Conversational words to drop from the description so only item keywords remain.
_FILLER = {
    "looking", "for", "the", "want", "wanted", "need", "find",
    "some", "please", "searching", "mostly", "wear", "in",
}


def _parse_query(query: str) -> dict:
    """
    Extract {description, size, max_price} from a short natural-language query.

    Uses regex (deterministic, no extra LLM call) — handles the
    "<item> [size X] [under $N]" shape used by the UI examples and CLI.
    """
    q = query.lower()

    # max_price: "under $30" / "below 30" / "less than $40", else a bare "$30".
    m = re.search(r"(?:under|below|less than|max|<)\s*\$?\s*(\d+(?:\.\d+)?)", q) \
        or re.search(r"\$\s*(\d+(?:\.\d+)?)", q)
    max_price = float(m.group(1)) if m else None

    # size: "size M" / "size 8" / "size S/M".
    s = re.search(r"size\s+([a-z0-9/]+)", q)
    size = s.group(1).upper() if s else None

    # description: drop the matched price/size phrases and stray $amounts, then
    # filter out short tokens and conversational filler words.
    desc = q
    if m:
        desc = desc.replace(m.group(0), " ")
    if s:
        desc = desc.replace(s.group(0), " ")
    desc = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", desc)  # only $-amounts; keep "90s" etc.
    tokens = [t for t in re.findall(r"[a-z0-9]+", desc) if len(t) > 1 and t not in _FILLER]

    return {"description": " ".join(tokens), "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: initialize the session.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search filters.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: search, with one relax-and-retry on empty results (per the diagram).
    results = search_listings(**parsed)
    if not results:
        relaxed = relax_search(**parsed)
        if relaxed is None:
            session["error"] = (
                f"No listings found for '{query}', and the search couldn't be "
                "loosened further. Try a broader description or a higher budget."
            )
            return session
        session["relaxed"] = relaxed
        results = search_listings(**relaxed)
        if not results:
            session["error"] = (
                f"No listings found for '{query}', even after broadening the search. "
                "Try a different item or fewer filters."
            )
            return session
    session["search_results"] = results

    # Step 4: select the top result.
    session["selected_item"] = results[0]

    # Step 5: suggest an outfit (handles an empty wardrobe internally).
    session["outfit_suggestion"] = suggest_outfit(results[0], wardrobe)

    # Step 6: create the shareable fit card.
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], results[0])

    # Step 7: return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
