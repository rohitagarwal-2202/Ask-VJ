"""
Query Parser — Stage 1 of the Intelligence Pipeline

Classifies user intent and extracts structured entities from natural language questions.
Uses the reasoning LLM (Mixtral) for classification.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

import httpx

from backend.config import LLMConfig

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    METRIC_QUERY = "METRIC_QUERY"       # "What's the collection efficiency?"
    LIST_QUERY = "LIST_QUERY"           # "Show me all cancelled bookings"
    COMPARISON = "COMPARISON"           # "Compare lead sources"
    TREND = "TREND"                     # "Revenue trend month-over-month"
    DRILL_DOWN = "DRILL_DOWN"           # "Break that down by sales person"
    CLARIFICATION = "CLARIFICATION"     # "What do you mean by collection efficiency?"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"       # "What's the weather?"


@dataclass
class ParsedFilter:
    field: str
    operator: str  # =, >, <, >=, <=, IN, LIKE
    value: str | list[str]


@dataclass
class ParsedQuery:
    intent: QueryIntent
    raw_question: str
    metric: str | None = None
    project: str | None = None
    phase: str | None = None
    time_range: str | None = None       # "this_month", "last_quarter", "FY2026", etc.
    time_start: str | None = None       # YYYY-MM-DD
    time_end: str | None = None         # YYYY-MM-DD
    group_by: str | None = None         # "sales_person", "project", "source", "month"
    filters: list[ParsedFilter] = field(default_factory=list)
    requires_previous_context: bool = False
    confidence: float = 0.0


INTENT_PROMPT = """You are a business intelligence assistant for Vilas Javdekar (VJ), a real estate developer in India.
Classify the user's question and extract structured parameters.

Available data domains (Phase 1 — Sales & CRM):
- Leads & pipeline stages (inquiry, site_visit, negotiation, booking, agreement, registered, cancelled)
- Bookings & agreements (unit details, agreement values, cancellations)
- Collections (demand letters, receipts, payment tracking)
- Sales person performance
- Lead source analysis (walk-in, referral, digital, channel partner)
- Project-level metrics

Intent categories:
- METRIC_QUERY: User wants a specific number or KPI (count, sum, average, rate, percentage)
- LIST_QUERY: User wants a list/table of records
- COMPARISON: User wants to compare groups (projects, sources, sales persons, time periods)
- TREND: User wants to see how something changes over time
- DRILL_DOWN: User wants to break down a previous answer by another dimension
- CLARIFICATION: User is asking about terminology or what data is available
- OUT_OF_SCOPE: Question is unrelated to VJ's business data

User question: "{question}"
{history_context}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "intent": "METRIC_QUERY|LIST_QUERY|COMPARISON|TREND|DRILL_DOWN|CLARIFICATION|OUT_OF_SCOPE",
  "metric": "the business metric being asked about, or null",
  "project": "project name mentioned, or null",
  "phase": "phase name mentioned, or null",
  "time_range": "this_month|last_month|this_quarter|last_quarter|this_year|last_year|FY2026|custom|null",
  "time_start": "YYYY-MM-DD or null (for custom ranges)",
  "time_end": "YYYY-MM-DD or null (for custom ranges)",
  "group_by": "sales_person|project|source|month|quarter|unit_type|null",
  "filters": [{{ "field": "field_name", "operator": "=", "value": "value" }}],
  "requires_previous_context": false,
  "confidence": 0.85
}}"""


class QueryParser:
    """Parses natural language questions into structured query representations."""

    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.conversation_history: list[dict] = []

    async def parse(self, question: str) -> ParsedQuery:
        """Parse a natural language question into a structured ParsedQuery."""
        # Build history context for drill-down support
        history_context = ""
        if self.conversation_history:
            recent = self.conversation_history[-3:]  # Last 3 exchanges
            history_lines = [f"- Q: {h['question']} → Intent: {h['intent']}" for h in recent]
            history_context = f"Recent conversation:\n" + "\n".join(history_lines)

        prompt = INTENT_PROMPT.format(
            question=question,
            history_context=history_context,
        )

        try:
            response_text = await self._call_llm(prompt)
            parsed = self._parse_llm_response(response_text, question)
        except Exception as e:
            logger.error("Query parsing failed: %s", e)
            # Fallback: treat as a metric query with low confidence
            parsed = ParsedQuery(
                intent=QueryIntent.METRIC_QUERY,
                raw_question=question,
                confidence=0.3,
            )

        # Update conversation history
        self.conversation_history.append({
            "question": question,
            "intent": parsed.intent.value,
        })
        # Keep history bounded
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-5:]

        return parsed

    async def _call_llm(self, prompt: str) -> str:
        """Call the local reasoning LLM via Ollama-compatible API."""
        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.reasoning_endpoint}/api/chat",
                json={
                    "model": self.config.reasoning_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": self.config.temperature,
                        "num_predict": self.config.max_tokens,
                    },
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _parse_llm_response(self, response_text: str, original_question: str) -> ParsedQuery:
        """Parse the LLM's JSON response into a ParsedQuery object."""
        # Extract JSON from response (handle potential markdown wrapping)
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)

        filters = []
        for f in data.get("filters") or []:
            filters.append(ParsedFilter(
                field=f["field"],
                operator=f.get("operator", "="),
                value=f["value"],
            ))

        return ParsedQuery(
            intent=QueryIntent(data["intent"]),
            raw_question=original_question,
            metric=data.get("metric"),
            project=data.get("project"),
            phase=data.get("phase"),
            time_range=data.get("time_range"),
            time_start=data.get("time_start"),
            time_end=data.get("time_end"),
            group_by=data.get("group_by"),
            filters=filters,
            requires_previous_context=data.get("requires_previous_context", False),
            confidence=data.get("confidence", 0.5),
        )

    def clear_history(self):
        """Clear conversation history (e.g., on session reset)."""
        self.conversation_history.clear()
