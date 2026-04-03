"""
Ask VJ Intelligence Pipeline — End-to-End Orchestrator

Chains the 5 stages together:
  Question → Parse → Retrieve → Generate SQL → Execute & Verify → Format Response

This is the single entry point the API calls.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime

from backend.config import AppConfig
from backend.intelligence.query_parser import QueryParser, ParsedQuery, QueryIntent
from backend.intelligence.clarification import ClarificationEngine
from backend.intelligence.schema_retriever import SchemaRetriever
from backend.intelligence.sql_generator import SQLGenerator
from backend.intelligence.executor import SQLExecutor, QueryResult
from backend.intelligence.verifier import ResultVerifier, VerificationResult
from backend.intelligence.response_formatter import ResponseFormatter
from backend.intelligence.glossary import (
    GlossaryEntry,
    find_relevant_terms,
    format_glossary_for_prompt,
    get_glossary_dict,
    override_glossary,
)
from backend.intelligence.user_context import UserContextManager
from backend.auth.guardrails import DataGuardrails, UserPolicies

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete result from the intelligence pipeline."""
    answer: str
    confidence: str                    # "high", "medium", "low"
    confidence_score: float            # 0.0 to 1.0
    data_sources: list[str]            # Tables queried
    filters_applied: dict              # Extracted filters
    last_sync: str | None              # Last ETL sync time
    response_time_ms: int              # Total pipeline latency
    intent: str                        # Classified intent
    sql_hash: str | None = None        # For debugging
    warnings: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_id: str | None = None
    clarification_options: list[dict] | None = None


class IntelligencePipeline:
    """
    The core Ask VJ intelligence engine.

    Usage:
        pipeline = IntelligencePipeline(config)
        result = await pipeline.ask("How many bookings this month?")
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.parser = QueryParser(config.llm)
        self.retriever = SchemaRetriever(config.llm, config.vector_db)
        self.generator = SQLGenerator(config.llm)
        self.executor = SQLExecutor(config.warehouse)
        self.verifier = ResultVerifier()
        self.formatter = ResponseFormatter(config.llm)
        self._glossary = get_glossary_dict()

    async def ask(self, question: str, session_id: str | None = None, user_id: int | None = None) -> PipelineResult:
        """
        Process a natural language question through the full pipeline.

        Args:
            question: The user's natural language question
            session_id: Optional session ID for conversation context

        Returns:
            PipelineResult with the formatted answer and metadata
        """
        start = datetime.now()

        # ── Stage 1: Parse ──
        logger.info("Stage 1: Parsing question: '%s'", question[:100])
        parsed = await self.parser.parse(question)
        logger.info("Parsed intent: %s (confidence: %.2f)", parsed.intent, parsed.confidence)

        # Handle non-SQL intents early
        if parsed.intent == QueryIntent.OUT_OF_SCOPE:
            return self._out_of_scope_response(question, start)

        if parsed.intent == QueryIntent.CLARIFICATION:
            return self._clarification_response(question, parsed, start)

        # ── Clarification check ──
        clarification_engine = ClarificationEngine(self.config.llm)
        if user_id and clarification_engine.should_clarify(parsed, self.config.clarification_threshold):
            # Need schema context for generating good options
            schemas = await self.retriever.retrieve(question, parsed.metric)
            schema_summary = self.retriever.format_schema_for_prompt(schemas)

            options = await clarification_engine.generate_options(
                question, parsed, schema_summary
            )

            if options:
                from sqlalchemy import create_engine as _ce
                engine = _ce(self.config.warehouse.connection_string)
                cid = clarification_engine.store_session(
                    engine, user_id, session_id or "", question, parsed, options
                )
                elapsed = int((datetime.now() - start).total_seconds() * 1000)
                return PipelineResult(
                    answer="I want to make sure I answer the right question.",
                    confidence="low",
                    confidence_score=parsed.confidence,
                    data_sources=[],
                    filters_applied={},
                    last_sync=None,
                    response_time_ms=elapsed,
                    intent=parsed.intent.value,
                    needs_clarification=True,
                    clarification_id=cid,
                    clarification_options=[
                        {"label": o.label, "description": o.description, "refined_query": o.refined_query}
                        for o in options
                    ],
                )

        # ── Guardrails: load user policies ──
        guardrails = DataGuardrails(self.config.warehouse.connection_string) if user_id else None
        policies = guardrails.load_policies(user_id) if guardrails else None

        # ── Stage 2: Retrieve schema context ──
        logger.info("Stage 2: Retrieving schema context")
        excluded = policies.denied_tables if policies else None
        schemas = await self.retriever.retrieve(question, parsed.metric, excluded_tables=excluded)

        # Apply guardrail schema filtering (remove denied tables, mask columns)
        if policies:
            schemas = guardrails.filter_schema_context(schemas, policies)

        schema_context = self.retriever.format_schema_for_prompt(schemas)
        data_sources = [s.table_name for s in schemas]

        # Get relevant business rules
        glossary_entries = find_relevant_terms(question)
        business_rules = format_glossary_for_prompt(glossary_entries)

        # Load user preferences and merge with glossary
        if user_id:
            from sqlalchemy import create_engine as _create_engine
            user_ctx = UserContextManager(_create_engine(self.config.warehouse.connection_string))
            user_prefs = user_ctx.load_preferences(user_id)
            if user_prefs:
                # Convert user prefs to GlossaryEntry format for merging
                user_glossary = [
                    GlossaryEntry(
                        term=p.term,
                        definition=p.definition,
                        sql_hint=p.sql_hint,
                        category="user_override",
                    )
                    for p in user_prefs
                ]
                merged_glossary = override_glossary(glossary_entries, user_glossary)
                business_rules = format_glossary_for_prompt(merged_glossary)
                # Also add user context section
                business_rules += "\n\n" + user_ctx.format_user_context_for_prompt(user_prefs)

        # ── Stage 3: Generate SQL ──
        logger.info("Stage 3: Generating SQL")

        # Add access restrictions to business rules for the LLM
        if policies and policies.allowed_project_keys is not None:
            keys_str = ", ".join(str(k) for k in policies.allowed_project_keys)
            business_rules += (
                f"\n\n=== ACCESS RESTRICTIONS ===\n"
                f"IMPORTANT: Only return data for project_key IN ({keys_str}). "
                f"Always include this filter in WHERE clauses for any table with a project_key column."
            )

        try:
            sql = await self.generator.generate(
                question=question,
                parsed=parsed,
                schema_context=schema_context,
                business_rules=business_rules,
            )
            logger.info("Generated SQL: %s", sql[:200])
        except ValueError as e:
            logger.error("SQL generation failed: %s", e)
            elapsed = int((datetime.now() - start).total_seconds() * 1000)
            return PipelineResult(
                answer=f"I couldn't generate a safe query for this question. {e}",
                confidence="low",
                confidence_score=0.0,
                data_sources=data_sources,
                filters_applied=self._extract_filters(parsed),
                last_sync=None,
                response_time_ms=elapsed,
                intent=parsed.intent.value,
                warnings=[str(e)],
            )

        # ── Guardrails: post-generation enforcement ──
        if policies:
            sql = guardrails.inject_where_clauses(sql, policies)
            is_allowed, reason = guardrails.validate_sql_access(sql, policies)
            if not is_allowed:
                return self._access_denied_response(reason, start)

        # ── Stage 4a: Execute SQL ──
        logger.info("Stage 4a: Executing SQL")
        result = self.executor.execute(sql)

        # If execution failed, try self-correction once
        if result.error:
            logger.warning("Execution failed, attempting self-correction: %s", result.error)
            try:
                corrected_sql = await self.generator.self_correct(
                    previous_sql=sql,
                    error=result.error,
                    schema_context=schema_context,
                )
                result = self.executor.execute(corrected_sql)
                if not result.error:
                    sql = corrected_sql
                    logger.info("Self-correction succeeded")
            except ValueError:
                logger.warning("Self-correction also failed")

        # ── Stage 4b: Verify results ──
        logger.info("Stage 4b: Verifying results")
        verification = self.verifier.verify(parsed, sql, result)
        logger.info(
            "Verification: %s (%.2f) — %d passed, %d failed",
            verification.confidence_label,
            verification.confidence,
            len(verification.passed_checks),
            len(verification.failed_checks),
        )

        # ── Stage 5: Format response ──
        logger.info("Stage 5: Formatting response")
        last_sync = self._get_last_sync_time()
        answer = await self.formatter.format(
            question=question,
            result=result,
            verification=verification,
            last_sync=last_sync,
        )

        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        logger.info("Pipeline complete in %dms", elapsed)

        return PipelineResult(
            answer=answer,
            confidence=verification.confidence_label,
            confidence_score=verification.confidence,
            data_sources=data_sources,
            filters_applied=self._extract_filters(parsed),
            last_sync=last_sync.isoformat() if last_sync else None,
            response_time_ms=elapsed,
            intent=parsed.intent.value,
            sql_hash=hashlib.md5(sql.encode()).hexdigest()[:8],
            warnings=verification.warnings,
        )

    async def ask_with_clarification(
        self, clarification_id: str, option_index: int, user_id: int
    ) -> PipelineResult:
        """Run the pipeline with a clarified query from a previous clarification session."""
        from sqlalchemy import create_engine as _ce
        engine = _ce(self.config.warehouse.connection_string)
        ce = ClarificationEngine(self.config.llm)
        option = ce.resolve_session(engine, clarification_id, option_index)
        # Run with the refined query at high confidence
        return await self.ask(option.refined_query, user_id=user_id)

    def _access_denied_response(self, reason: str, start: datetime) -> PipelineResult:
        """Handle queries blocked by data guardrails."""
        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        return PipelineResult(
            answer=(
                "You don't have access to this data. Contact your admin to update "
                "your data access policies."
            ),
            confidence="high",
            confidence_score=1.0,
            data_sources=[],
            filters_applied={},
            last_sync=None,
            response_time_ms=elapsed,
            intent="access_denied",
            warnings=[reason],
        )

    def _out_of_scope_response(self, question: str, start: datetime) -> PipelineResult:
        """Handle out-of-scope questions."""
        elapsed = int((datetime.now() - start).total_seconds() * 1000)
        return PipelineResult(
            answer=(
                "That question is outside my scope. I can help with:\n"
                "- **Sales & leads**: bookings, pipeline stages, conversion rates\n"
                "- **Collections**: demand letters, receipts, outstanding amounts\n"
                "- **Projects**: unit details, project status, inventory\n"
                "- **Performance**: sales person metrics, lead source analysis\n\n"
                "Try asking something like: \"How many bookings did we get this month?\""
            ),
            confidence="high",
            confidence_score=1.0,
            data_sources=[],
            filters_applied={},
            last_sync=None,
            response_time_ms=elapsed,
            intent=QueryIntent.OUT_OF_SCOPE.value,
        )

    def _clarification_response(
        self, question: str, parsed: ParsedQuery, start: datetime
    ) -> PipelineResult:
        """Handle clarification questions using the business glossary."""
        elapsed = int((datetime.now() - start).total_seconds() * 1000)

        # Search glossary for relevant terms
        entries = find_relevant_terms(question)
        if entries:
            lines = []
            for entry in entries[:3]:
                lines.append(f"**{entry.term.title()}**: {entry.definition}")
                if entry.formula:
                    lines.append(f"  _Formula: {entry.formula}_")
                if entry.good_range:
                    lines.append(f"  _Expected range: {entry.good_range}_")
            answer = "\n\n".join(lines)
        else:
            answer = (
                "I don't have a specific definition for that term. "
                "I can explain terms like: collection efficiency, conversion rate, "
                "pipeline stage, booking, agreement value, RERA, carpet area, "
                "fiscal year, channel partner, and more.\n\n"
                "What would you like to know about?"
            )

        return PipelineResult(
            answer=answer,
            confidence="high",
            confidence_score=1.0,
            data_sources=[],
            filters_applied={},
            last_sync=None,
            response_time_ms=elapsed,
            intent=QueryIntent.CLARIFICATION.value,
        )

    def _get_last_sync_time(self) -> datetime | None:
        """Query the warehouse for the most recent successful sync."""
        try:
            from sqlalchemy import text
            with self.executor.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT MAX(completed_at) FROM bronze.sync_log WHERE status = 'success'"
                ))
                row = result.fetchone()
                return row[0] if row and row[0] else None
        except Exception:
            return None

    @staticmethod
    def _extract_filters(parsed: ParsedQuery) -> dict:
        """Extract applied filters as a simple dict for response metadata."""
        filters = {}
        if parsed.project:
            filters["project"] = parsed.project
        if parsed.phase:
            filters["phase"] = parsed.phase
        if parsed.time_range:
            filters["time_range"] = parsed.time_range
        if parsed.group_by:
            filters["group_by"] = parsed.group_by
        return filters
