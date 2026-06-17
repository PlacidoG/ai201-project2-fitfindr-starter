import re
import types

import pytest

import tools
from tools import search_listings, suggest_outfit, create_fit_card, relax_search
from utils.data_loader import (
    get_example_wardrobe,
    get_empty_wardrobe,
    load_listings,
)


# ── fixtures / helpers ──────────────────────────────────────────────────────

@pytest.fixture
def sample_item():
    """A real listing dict (has every field the tools expect)."""
    return load_listings()[0]


def _fake_groq_client(captured, content):
    """
    Build a stand-in for the Groq client that mirrors the real call chain
    client.chat.completions.create(...).choices[0].message.content, recording
    the call kwargs into `captured` so tests can assert on them.
    """
    def create(**kwargs):
        captured.update(kwargs)
        message = types.SimpleNamespace(content=content)
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])

    completions = types.SimpleNamespace(create=create)
    chat = types.SimpleNamespace(completions=completions)
    return types.SimpleNamespace(chat=chat)


@pytest.fixture
def mock_groq(monkeypatch):
    """
    Patch _get_groq_client so the LLM-backed tools never hit the network or
    read GROQ_API_KEY. Returns the dict of kwargs the tool passed to create().
    The mocked content has surrounding whitespace to verify the tools strip it.
    """
    captured = {}
    monkeypatch.setattr(
        tools,
        "_get_groq_client",
        lambda: _fake_groq_client(captured, "  Mocked LLM response.  "),
    )
    return captured


# ── Tool 1: search_listings ─────────────────────────────────────────────────

def test_search_returns_nonempty_list_of_dicts():
    results = search_listings("tee")
    assert isinstance(results, list)
    assert results, "expected at least one match for 'tee'"
    assert all(isinstance(r, dict) for r in results)


def test_search_respects_max_price():
    results = search_listings("jacket", max_price=50)
    assert results, "expected some jackets under $50"
    assert all(r["price"] <= 50 for r in results)


def test_search_respects_size_filter():
    results = search_listings("shirt", size="M")
    assert all("m" in r["size"].lower() for r in results)


def test_search_no_match_returns_empty_list():
    # Must return [] rather than raising.
    assert search_listings("zzzznotarealitem999") == []


def test_search_sorted_by_relevance_descending():
    query = "vintage leather jacket"
    keywords = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    results = search_listings(query)
    assert results

    def overlap(item):
        haystack = " ".join([
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
            " ".join(item["colors"]),
            item["category"],
            item["brand"] or "",
        ]).lower()
        tokens = set(re.findall(r"[a-z0-9]+", haystack))
        return sum(1 for kw in keywords if kw in tokens)

    scores = [overlap(r) for r in results]
    assert scores == sorted(scores, reverse=True)
    assert min(scores) >= 1  # zero-overlap listings are dropped


# ── Tool 4: relax_search ────────────────────────────────────────────────────

def test_relax_drops_size_bumps_price_and_broadens():
    assert relax_search("vintage graphic tee", "M", 30) == {
        "description": "tee",
        "size": None,
        "max_price": 45.0,
    }


def test_relax_price_only_bump():
    assert relax_search("tee", None, 20) == {
        "description": "tee",
        "size": None,
        "max_price": 30.0,
    }


def test_relax_exhausted_returns_none():
    # Single-word description, no size, no price → nothing left to loosen.
    assert relax_search("tee", None, None) is None


def test_relax_output_feeds_search_listings():
    relaxed = relax_search("leather bomber", size="XXL", max_price=10)
    assert relaxed is not None
    results = search_listings(**relaxed)
    assert isinstance(results, list)


# ── Tool 2: suggest_outfit ──────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe(mock_groq, sample_item):
    out = suggest_outfit(sample_item, get_example_wardrobe())

    assert out == "Mocked LLM response."  # whitespace stripped
    assert mock_groq["model"] == tools._GROQ_MODEL
    assert mock_groq["temperature"] == 0.7

    # Populated branch should name a real wardrobe piece in the user prompt.
    user_msg = mock_groq["messages"][-1]["content"]
    first_name = get_example_wardrobe()["items"][0]["name"]
    assert first_name in user_msg


def test_suggest_outfit_empty_wardrobe_does_not_crash(mock_groq, sample_item):
    out = suggest_outfit(sample_item, get_empty_wardrobe())
    assert isinstance(out, str) and out  # non-empty, no exception


# ── Tool 3: create_fit_card ─────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string(sample_item):
    # Guard path: no LLM call, no exception.
    msg = create_fit_card("", sample_item)
    assert isinstance(msg, str)
    assert "fit card" in msg.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string(sample_item):
    msg = create_fit_card("   ", sample_item)
    assert "fit card" in msg.lower()


def test_create_fit_card_happy_path(mock_groq, sample_item):
    out = create_fit_card("baggy jeans + chunky sneakers", sample_item)

    assert out  # non-empty caption
    assert mock_groq["model"] == tools._GROQ_MODEL
    assert mock_groq["temperature"] == 1.0  # higher temp for caption variety
