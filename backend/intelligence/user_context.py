"""
Ask VJ — Per-User Context & Preferences Manager

Allows users to have their own interpretations of business terms
that override the global glossary. Tracks corrections for learning.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.intelligence.glossary import GlossaryEntry

logger = logging.getLogger(__name__)


@dataclass
class UserPreference:
    term: str
    definition: str
    sql_hint: str | None
    source: str  # "manual" or "learned"
    confidence: float


@dataclass
class SuggestedPreference:
    term: str
    suggested_definition: str
    occurrence_count: int


class UserContextManager:
    """Manages per-user business term overrides and learned corrections."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def load_preferences(self, user_id: int) -> list[UserPreference]:
        """Load all preferences for a user from app.user_preferences."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT term, definition, sql_hint, source, confidence "
                    "FROM app.user_preferences "
                    "WHERE user_id = :user_id "
                    "ORDER BY term"
                ),
                {"user_id": user_id},
            ).fetchall()
        return [
            UserPreference(
                term=row[0],
                definition=row[1],
                sql_hint=row[2],
                source=row[3],
                confidence=row[4],
            )
            for row in rows
        ]

    def merge_with_glossary(
        self,
        global_entries: list[GlossaryEntry],
        user_prefs: list[UserPreference],
    ) -> list[GlossaryEntry]:
        """
        For each user pref, if a matching term exists in global_entries,
        replace it with a new GlossaryEntry using the user's definition/sql_hint.
        If no match, append as new entry. Return the merged list.
        """
        override_map = {
            p.term.lower(): GlossaryEntry(
                term=p.term,
                definition=p.definition,
                sql_hint=p.sql_hint,
                category="user_override",
            )
            for p in user_prefs
        }

        result = []
        for entry in global_entries:
            key = entry.term.lower()
            if key in override_map:
                result.append(override_map.pop(key))
            else:
                result.append(entry)

        # Append any remaining overrides that weren't replacements
        result.extend(override_map.values())
        return result

    def format_user_context_for_prompt(
        self, user_prefs: list[UserPreference]
    ) -> str:
        """Format user preferences as a prompt section."""
        if not user_prefs:
            return ""

        lines = ["=== USER-SPECIFIC DEFINITIONS ==="]
        for p in user_prefs:
            lines.append(f"**{p.term}** (user override): {p.definition}")
            if p.sql_hint:
                lines.append(f"  SQL hint: {p.sql_hint}")
        return "\n".join(lines)

    def record_correction(
        self,
        user_id: int,
        session_id: str | None,
        original_term: str,
        corrected_to: str,
        question: str,
    ) -> None:
        """Insert a correction into app.conversation_corrections."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.conversation_corrections "
                    "(user_id, session_id, original_term, corrected_to, question) "
                    "VALUES (:user_id, :session_id, :original_term, :corrected_to, :question)"
                ),
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "original_term": original_term,
                    "corrected_to": corrected_to,
                    "question": question,
                },
            )
            conn.commit()

    def check_learned_patterns(self, user_id: int) -> list[SuggestedPreference]:
        """
        Query conversation_corrections, group by (user_id, original_term, corrected_to),
        and return entries with count >= 3 as suggested preferences.
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT original_term, corrected_to, COUNT(*) as cnt "
                    "FROM app.conversation_corrections "
                    "WHERE user_id = :user_id "
                    "GROUP BY original_term, corrected_to "
                    "HAVING COUNT(*) >= 3 "
                    "ORDER BY cnt DESC"
                ),
                {"user_id": user_id},
            ).fetchall()
        return [
            SuggestedPreference(
                term=row[0],
                suggested_definition=row[1],
                occurrence_count=row[2],
            )
            for row in rows
        ]

    def save_preference(
        self,
        user_id: int,
        term: str,
        definition: str,
        sql_hint: str | None = None,
        source: str = "manual",
    ) -> None:
        """Upsert a preference into app.user_preferences."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.user_preferences "
                    "(user_id, term, definition, sql_hint, source) "
                    "VALUES (:user_id, :term, :definition, :sql_hint, :source) "
                    "ON CONFLICT (user_id, term) DO UPDATE SET "
                    "definition = EXCLUDED.definition, "
                    "sql_hint = EXCLUDED.sql_hint, "
                    "source = EXCLUDED.source, "
                    "updated_at = NOW()"
                ),
                {
                    "user_id": user_id,
                    "term": term,
                    "definition": definition,
                    "sql_hint": sql_hint,
                    "source": source,
                },
            )
            conn.commit()

    def delete_preference(self, user_id: int, term: str) -> None:
        """Delete a preference from app.user_preferences."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "DELETE FROM app.user_preferences "
                    "WHERE user_id = :user_id AND term = :term"
                ),
                {"user_id": user_id, "term": term},
            )
            conn.commit()
