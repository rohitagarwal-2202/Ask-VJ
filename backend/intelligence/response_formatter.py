"""
Response Formatter — Stage 5 of the Intelligence Pipeline

Converts raw SQL results into clear, natural language business answers
using the reasoning LLM. Formats numbers in Indian notation (lakhs, crores).
"""

import json
import logging
from datetime import datetime

import httpx

from backend.config import LLMConfig
from backend.intelligence.executor import QueryResult
from backend.intelligence.verifier import VerificationResult

logger = logging.getLogger(__name__)


RESPONSE_PROMPT = """You are a business analyst for Vilas Javdekar (VJ), a real estate developer in India.
Convert these SQL results into a clear, concise business answer.

User question: "{question}"

Query results ({row_count} rows):
{results_text}

Confidence: {confidence_label}
{warnings_text}

Rules:
- Lead with the answer, not the methodology
- Format INR amounts in Indian numbering: use lakhs (1,00,000) and crores (1,00,00,000)
  - Example: ₹1,24,50,000 = ₹1.24 Cr, ₹85,00,000 = ₹85 L
  - For amounts under ₹1 lakh, show exact: ₹45,000
- Round percentages to 1 decimal place
- If results are a table with more than 1 row, format as a clean markdown table
- If results are a single number, lead with that number prominently
- If confidence is "medium", add a brief note about potential data limitations
- If confidence is "low", add "⚠ Please verify this data manually" with explanation
- Include the data freshness timestamp at the bottom
- Keep it under 200 words unless the user asked for details
- Do NOT expose raw SQL or column names to the user
- Do NOT use overly technical language — write for a business manager

Example output for "Collection efficiency for Phase 2?":
**87.3%** — Collection efficiency for Phase 2

- Total demanded: ₹12.4 Cr
- Total collected: ₹10.8 Cr
- Outstanding: ₹1.6 Cr

_Data as of {sync_time}_"""


class ResponseFormatter:
    """Formats SQL results into natural language answers."""

    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config

    async def format(
        self,
        question: str,
        result: QueryResult,
        verification: VerificationResult,
        last_sync: datetime | None = None,
    ) -> str:
        """Format query results into a natural language answer."""

        # Handle error cases directly (no LLM needed)
        if result.error:
            return self._format_error(result.error, verification)

        if result.is_empty:
            return self._format_empty(question, verification)

        # For simple scalar results, format directly without LLM
        if result.is_scalar and self._is_simple_number(result.rows[0][0]):
            return self._format_scalar(question, result, verification, last_sync)

        # Use LLM for complex results
        return await self._format_with_llm(question, result, verification, last_sync)

    def _format_error(self, error: str, verification: VerificationResult) -> str:
        """Format an error response."""
        return (
            "I wasn't able to retrieve that data. "
            f"The query encountered an issue: {error}\n\n"
            "Try rephrasing your question, or ask me what data is available."
        )

    def _format_empty(self, question: str, verification: VerificationResult) -> str:
        """Format a response for empty results."""
        return (
            f"No data found for your question: \"{question}\"\n\n"
            "This could mean:\n"
            "- The filters are too restrictive (try broadening the time range or project)\n"
            "- The data hasn't been synced yet for this period\n"
            "- The metric doesn't apply to the specified context"
        )

    def _format_scalar(
        self,
        question: str,
        result: QueryResult,
        verification: VerificationResult,
        last_sync: datetime | None,
    ) -> str:
        """Format a single-value result without LLM."""
        value = result.rows[0][0]
        col_name = result.columns[0].lower()

        # Format based on column type
        if "pct" in col_name or "rate" in col_name or "efficiency" in col_name:
            formatted = f"**{value:.1f}%**"
        elif isinstance(value, (int, float)) and (
            "amount" in col_name or "collected" in col_name or "demanded" in col_name
        ):
            formatted = f"**{self._format_inr(value)}**"
        elif isinstance(value, (int, float)):
            formatted = f"**{value:,.0f}**" if value == int(value) else f"**{value:,.2f}**"
        else:
            formatted = f"**{value}**"

        # Build response
        label = col_name.replace("_", " ").title()
        lines = [f"{formatted} — {label}"]

        if verification.confidence_label == "medium":
            lines.append("\n_Note: This result has moderate confidence. Consider cross-checking._")
        elif verification.confidence_label == "low":
            lines.append("\n⚠ **Please verify this data manually.** " +
                         "; ".join(verification.warnings[:2]))

        if last_sync:
            lines.append(f"\n_Data as of {last_sync.strftime('%d %b %Y, %I:%M %p IST')}_")

        return "\n".join(lines)

    async def _format_with_llm(
        self,
        question: str,
        result: QueryResult,
        verification: VerificationResult,
        last_sync: datetime | None,
    ) -> str:
        """Use the reasoning LLM to format complex results."""
        # Prepare results text (limit to first 20 rows for prompt size)
        display_rows = result.rows[:20]
        if result.row_count <= 5:
            results_text = json.dumps(result.to_dict_list()[:20], indent=2, default=str)
        else:
            # Format as a table for readability
            header = " | ".join(result.columns)
            separator = " | ".join("---" for _ in result.columns)
            rows_text = "\n".join(
                " | ".join(str(v) for v in row)
                for row in display_rows
            )
            results_text = f"{header}\n{separator}\n{rows_text}"
            if result.row_count > 20:
                results_text += f"\n... and {result.row_count - 20} more rows"

        warnings_text = ""
        if verification.warnings:
            warnings_text = "Warnings: " + "; ".join(verification.warnings[:3])

        sync_time = (
            last_sync.strftime("%d %b %Y, %I:%M %p IST")
            if last_sync else "latest sync"
        )

        prompt = RESPONSE_PROMPT.format(
            question=question,
            row_count=result.row_count,
            results_text=results_text,
            confidence_label=verification.confidence_label,
            warnings_text=warnings_text,
            sync_time=sync_time,
        )

        try:
            response = await self._call_llm(prompt)
            return response.strip()
        except Exception as e:
            logger.error("LLM formatting failed, using fallback: %s", e)
            return self._fallback_format(result, verification, last_sync)

    def _fallback_format(
        self,
        result: QueryResult,
        verification: VerificationResult,
        last_sync: datetime | None,
    ) -> str:
        """Fallback formatting when LLM is unavailable."""
        if result.row_count == 1:
            row_dict = dict(zip(result.columns, result.rows[0]))
            lines = []
            for key, val in row_dict.items():
                label = key.replace("_", " ").title()
                if isinstance(val, (int, float)):
                    lines.append(f"- **{label}**: {val:,.2f}")
                else:
                    lines.append(f"- **{label}**: {val}")
            return "\n".join(lines)

        # Multi-row: markdown table
        header = " | ".join(result.columns)
        separator = " | ".join("---" for _ in result.columns)
        rows = "\n".join(
            " | ".join(str(v) for v in row)
            for row in result.rows[:20]
        )
        table = f"| {header} |\n| {separator} |\n"
        table += "\n".join(
            "| " + " | ".join(str(v) for v in row) + " |"
            for row in result.rows[:20]
        )
        if result.row_count > 20:
            table += f"\n\n_Showing 20 of {result.row_count} results_"
        return table

    async def _call_llm(self, prompt: str) -> str:
        """Call the reasoning LLM."""
        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.reasoning_endpoint}/api/chat",
                json={
                    "model": self.config.reasoning_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 1024,
                    },
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    @staticmethod
    def _format_inr(amount: float) -> str:
        """Format an amount in Indian notation (lakhs/crores)."""
        if abs(amount) >= 1_00_00_000:
            return f"₹{amount / 1_00_00_000:.2f} Cr"
        elif abs(amount) >= 1_00_000:
            return f"₹{amount / 1_00_000:.2f} L"
        else:
            return f"₹{amount:,.0f}"

    @staticmethod
    def _is_simple_number(value) -> bool:
        """Check if a value is a simple number (not None, not string)."""
        return isinstance(value, (int, float)) and value is not None
