"""
Tests for backend.intelligence.glossary — Business glossary entries and lookup functions.
"""

import pytest

from backend.intelligence.glossary import (
    GLOSSARY,
    GlossaryEntry,
    find_relevant_terms,
    format_glossary_for_prompt,
    get_glossary_dict,
)


# ── Basic glossary structure ─────────────────────────────────────

def test_glossary_not_empty():
    """The glossary should contain entries."""
    assert len(GLOSSARY) > 0


def test_all_entries_have_required_fields():
    """Every entry must have a non-empty term, definition, and category."""
    for entry in GLOSSARY:
        assert isinstance(entry, GlossaryEntry)
        assert entry.term, f"Entry missing term: {entry}"
        assert entry.definition, f"Entry missing definition: {entry}"
        assert entry.category, f"Entry missing category: {entry}"


# ── get_glossary_dict ────────────────────────────────────────────

def test_get_glossary_dict_keys_match_terms():
    """Dictionary keys should match the term field of each entry."""
    d = get_glossary_dict()
    assert len(d) == len(GLOSSARY)
    for entry in GLOSSARY:
        assert entry.term in d
        assert d[entry.term] is entry


# ── find_relevant_terms ──────────────────────────────────────────

def test_find_relevant_terms_booking():
    """A question about bookings should find the 'booking' glossary entry."""
    results = find_relevant_terms("How many bookings this month?")
    term_names = [e.term for e in results]
    assert "booking" in term_names


def test_find_relevant_terms_outstanding():
    """A question about outstanding should find the 'outstanding' entry."""
    results = find_relevant_terms("What is the total outstanding amount?")
    term_names = [e.term for e in results]
    assert "outstanding" in term_names


def test_find_relevant_terms_typology():
    """A question about typology should find the 'typology' entry."""
    results = find_relevant_terms("Show typology breakdown for the project")
    term_names = [e.term for e in results]
    assert "typology" in term_names


def test_find_relevant_terms_no_match():
    """Gibberish input should return an empty list."""
    results = find_relevant_terms("xyzzy plugh zork")
    assert results == []


def test_find_relevant_terms_tenant_id():
    """Farvision-related questions should surface the 'tenant id' entry."""
    results = find_relevant_terms("What is the tenant id for Farvision queries?")
    term_names = [e.term for e in results]
    assert "tenant id" in term_names


def test_find_relevant_terms_collection_efficiency():
    """A question about collection efficiency should find that entry."""
    results = find_relevant_terms("What is the collection efficiency this quarter?")
    term_names = [e.term for e in results]
    assert "collection efficiency" in term_names


def test_find_relevant_terms_referral():
    """A question about referrals should find the 'referral' entry."""
    results = find_relevant_terms("How many referrals came through VJOP?")
    term_names = [e.term for e in results]
    assert "referral" in term_names


# ── format_glossary_for_prompt ───────────────────────────────────

def test_format_glossary_for_prompt_empty():
    """Formatting an empty list should return an empty string."""
    assert format_glossary_for_prompt([]) == ""


def test_format_glossary_for_prompt_includes_formula():
    """If an entry has a formula, the formatted output should include it."""
    entry = GlossaryEntry(
        term="collection efficiency",
        definition="Ratio of receipts to invoices.",
        formula="SUM(receipts) / SUM(invoices) * 100",
        category="collections",
    )
    output = format_glossary_for_prompt([entry])
    assert "BUSINESS RULES" in output
    assert "collection efficiency" in output
    assert "Formula:" in output
    assert "SUM(receipts) / SUM(invoices) * 100" in output


def test_format_glossary_for_prompt_includes_sql_hint():
    """If an entry has an sql_hint, the formatted output should include it."""
    entry = GlossaryEntry(
        term="tenant id",
        definition="All queries MUST include TenantId = 75.",
        sql_hint="Always include WHERE TenantId = 75",
        category="general",
    )
    output = format_glossary_for_prompt([entry])
    assert "SQL hint:" in output
    assert "TenantId = 75" in output


def test_format_glossary_for_prompt_includes_good_range():
    """If an entry has a good_range, the formatted output should include it."""
    entry = GlossaryEntry(
        term="collection efficiency",
        definition="Ratio of receipts to invoices.",
        good_range="80-100%",
        category="collections",
    )
    output = format_glossary_for_prompt([entry])
    assert "Expected range:" in output
    assert "80-100%" in output


def test_format_glossary_for_prompt_multiple_entries():
    """Multiple entries should each appear in the output."""
    entries = [
        GlossaryEntry(term="booking", definition="A committed purchase.", category="sales"),
        GlossaryEntry(term="receipt", definition="A payment received.", category="collections"),
    ]
    output = format_glossary_for_prompt(entries)
    assert "booking" in output
    assert "receipt" in output
