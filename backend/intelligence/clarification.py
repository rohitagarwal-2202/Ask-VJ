"""
Clarification Engine — Follow-up disambiguation for low-confidence queries.

When the pipeline detects a query with low confidence, this engine generates
multiple-choice options for the user to pick from, ensuring the right question
gets answered.
"""

import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.config import LLMConfig
from backend.intelligence.llm_client import call_llm
from backend.intelligence.query_parser import ParsedQuery, QueryIntent

logger = logging.getLogger(__name__)


@dataclass
class ClarificationOption:
    """A single disambiguation option presented to the user."""
    label: str            # e.g. "Total booking count this month"
    description: str      # brief explanation
    refined_query: str    # the unambiguous question to run


# Intents that are actual data queries (eligible for clarification)
_QUERY_INTENTS = {
    QueryIntent.METRIC_QUERY,
    QueryIntent.LIST_QUERY,
    QueryIntent.COMPARISON,
    QueryIntent.TREND,
    QueryIntent.DRILL_DOWN,
}

CLARIFICATION_PROMPT = """The user asked an ambiguous question about VJ real estate data. Generate 3-4 specific \
interpretations as multiple-choice options.

User question: "{question}"
Confidence: {confidence}
Detected intent: {intent}
Available data: {schema_summary}
{user_context}

Generate a JSON array of options. Each option should be a specific, unambiguous query:
[
  {{"label": "Total booking count this month", "description": "Count of active bookings in the current month", "refined_query": "How many active bookings were made this month?"}},
  ...
]

Return ONLY the JSON array, no other text."""


class ClarificationEngine:
    """Generates and manages disambiguation options for ambiguous queries."""

    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config

    def should_clarify(self, parsed: ParsedQuery, threshold: float = 0.7) -> bool:
        """Return True if confidence is below threshold and intent is a query type."""
        if parsed.intent not in _QUERY_INTENTS:
            return False
        return parsed.confidence < threshold

    async def generate_options(
        self,
        question: str,
        parsed: ParsedQuery,
        schema_context: str,
        user_context: str = "",
    ) -> list[ClarificationOption]:
        """Call LLM to generate 2-4 disambiguation options."""
        prompt = CLARIFICATION_PROMPT.format(
            question=question,
            confidence=parsed.confidence,
            intent=parsed.intent.value,
            schema_summary=schema_context,
            user_context=user_context,
        )

        try:
            response_text = await call_llm(
                self.config, prompt, role="reasoning", temperature=0.4
            )
            return self._parse_options(response_text)
        except Exception as e:
            logger.error("Failed to generate clarification options: %s", e)
            return []

    def _parse_options(self, response_text: str) -> list[ClarificationOption]:
        """Parse LLM JSON response into ClarificationOption list."""
        text_clean = response_text.strip()
        # Handle potential markdown wrapping
        if text_clean.startswith("```"):
            text_clean = text_clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text_clean)
        if not isinstance(data, list):
            logger.warning("Clarification LLM response is not a list")
            return []

        options = []
        for item in data[:4]:  # Cap at 4 options
            if all(k in item for k in ("label", "description", "refined_query")):
                options.append(ClarificationOption(
                    label=item["label"],
                    description=item["description"],
                    refined_query=item["refined_query"],
                ))
        return options

    def store_session(
        self,
        engine: Engine,
        user_id: int,
        session_id: str,
        question: str,
        parsed: ParsedQuery,
        options: list[ClarificationOption],
    ) -> str:
        """Store in app.clarification_sessions, return clarification_id (UUID)."""
        clarification_id = str(uuid.uuid4())
        options_json = json.dumps([
            {"label": o.label, "description": o.description, "refined_query": o.refined_query}
            for o in options
        ])

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.clarification_sessions
                        (clarification_id, user_id, session_id, original_question,
                         parsed_intent, parsed_confidence, options, status)
                    VALUES
                        (:cid, :uid, :sid, :question, :intent, :confidence, :options::jsonb, 'pending')
                """),
                {
                    "cid": clarification_id,
                    "uid": user_id,
                    "sid": session_id,
                    "question": question,
                    "intent": parsed.intent.value,
                    "confidence": parsed.confidence,
                    "options": options_json,
                },
            )

        logger.info("Stored clarification session %s with %d options", clarification_id, len(options))
        return clarification_id

    def resolve_session(
        self, engine: Engine, clarification_id: str, option_index: int
    ) -> ClarificationOption:
        """Mark session resolved, return the chosen option."""
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    SELECT options, status FROM app.clarification_sessions
                    WHERE clarification_id = :cid
                """),
                {"cid": clarification_id},
            ).fetchone()

            if not row:
                raise ValueError(f"Clarification session {clarification_id} not found")

            if row[1] != "pending":
                raise ValueError(f"Clarification session {clarification_id} is already {row[1]}")

            options_data = row[0] if isinstance(row[0], list) else json.loads(row[0])

            if option_index < 0 or option_index >= len(options_data):
                raise ValueError(
                    f"Invalid option index {option_index}, must be 0-{len(options_data) - 1}"
                )

            conn.execute(
                text("""
                    UPDATE app.clarification_sessions
                    SET selected_option = :idx, status = 'resolved', resolved_at = NOW()
                    WHERE clarification_id = :cid
                """),
                {"idx": option_index, "cid": clarification_id},
            )

        chosen = options_data[option_index]
        return ClarificationOption(
            label=chosen["label"],
            description=chosen["description"],
            refined_query=chosen["refined_query"],
        )
