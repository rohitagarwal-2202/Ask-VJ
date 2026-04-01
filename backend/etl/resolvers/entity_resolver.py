"""
Entity Resolver — Links records across VJ Sales and Farvision into unified customer identities.

Matching strategy (priority order):
1. Unit + Project exact match (highest confidence)
2. Phone number exact match
3. Fuzzy name match + project match
4. Queue for manual review
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class EntityResolver:
    """Resolves customer identities across source systems."""

    def __init__(self, warehouse_connection_string: str, fuzzy_threshold: float = 0.6):
        self.engine: Engine = create_engine(warehouse_connection_string)
        self.fuzzy_threshold = fuzzy_threshold

    def resolve(self) -> dict:
        """
        Run all matching strategies and update silver.entity_map.
        Returns stats: {matched, queued_for_review, already_resolved}.
        """
        stats = {"matched": 0, "queued_for_review": 0, "already_resolved": 0}

        with self.engine.begin() as conn:
            # Strategy 1: Unit + Project exact match
            matched = self._match_by_unit_project(conn)
            stats["matched"] += matched
            logger.info("Unit+Project match: %d new matches", matched)

            # Strategy 2: Phone exact match
            matched = self._match_by_phone(conn)
            stats["matched"] += matched
            logger.info("Phone match: %d new matches", matched)

            # Strategy 3: Fuzzy name + project match
            matched, queued = self._match_by_fuzzy_name(conn)
            stats["matched"] += matched
            stats["queued_for_review"] += queued
            logger.info("Fuzzy name match: %d matched, %d queued", matched, queued)

        return stats

    def _match_by_unit_project(self, conn) -> int:
        """
        Match VJ Sales bookings to Farvision records by unit_no + project.
        Uses silver.project_crosswalk to map project names.
        """
        query = text("""
            INSERT INTO silver.entity_map (
                vjsales_lead_id, vjsales_booking_id,
                farvision_customer_name, farvision_project_code, farvision_unit_no,
                match_method, match_confidence
            )
            SELECT DISTINCT ON (b.lead_id)
                b.lead_id,
                b.booking_id,
                r.customer_name,
                r.project_code,
                r.unit_no,
                'unit_project_exact',
                0.95
            FROM bronze.stg_vjsales_bookings b
            JOIN silver.project_crosswalk pc
                ON b.project_name = pc.vjsales_project_name
            JOIN bronze.stg_farvision_receipts r
                ON r.project_code = pc.farvision_project_code
                AND r.unit_no = b.unit_no
            WHERE b.lead_id NOT IN (
                SELECT vjsales_lead_id FROM silver.entity_map WHERE vjsales_lead_id IS NOT NULL
            )
            -- Use the most recent staging records
            AND b._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_bookings b2 WHERE b2.booking_id = b.booking_id
            )
            AND r._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_farvision_receipts r2
                WHERE r2.project_code = r.project_code AND r2.unit_no = r.unit_no
            )
            ON CONFLICT (vjsales_lead_id) DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _match_by_phone(self, conn) -> int:
        """
        Match VJ Sales leads to Farvision records by phone number.
        Only applies when both systems store phone numbers.
        """
        # NOTE: This requires a phone column in Farvision data.
        # Placeholder — implement when Farvision schema is confirmed.
        logger.info("Phone matching: skipped (Farvision phone column TBD)")
        return 0

    def _match_by_fuzzy_name(self, conn) -> tuple[int, int]:
        """
        Fuzzy match lead names (VJ Sales) against customer names (Farvision).
        High-confidence matches go to entity_map, low-confidence to review queue.
        """
        # Find unmatched VJ Sales bookings that have a Farvision record in the same project
        query = text("""
            SELECT
                b.lead_id,
                b.booking_id,
                l.lead_name,
                l.phone,
                b.project_name,
                b.unit_no,
                r.customer_name AS farv_customer_name,
                r.project_code AS farv_project_code,
                r.unit_no AS farv_unit_no,
                similarity(l.lead_name, r.customer_name) AS name_similarity
            FROM bronze.stg_vjsales_bookings b
            JOIN bronze.stg_vjsales_leads l ON b.lead_id = l.lead_id
            JOIN silver.project_crosswalk pc ON b.project_name = pc.vjsales_project_name
            JOIN bronze.stg_farvision_receipts r ON r.project_code = pc.farvision_project_code
            WHERE b.lead_id NOT IN (
                SELECT vjsales_lead_id FROM silver.entity_map WHERE vjsales_lead_id IS NOT NULL
            )
            AND similarity(l.lead_name, r.customer_name) > :threshold
            -- Most recent records only
            AND b._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_bookings b2 WHERE b2.booking_id = b.booking_id
            )
            AND l._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_leads l2 WHERE l2.lead_id = l.lead_id
            )
            ORDER BY name_similarity DESC
        """)
        rows = conn.execute(query, {"threshold": self.fuzzy_threshold}).fetchall()

        matched = 0
        queued = 0

        for row in rows:
            confidence = float(row.name_similarity)

            if confidence >= 0.85:
                # High confidence — auto-resolve
                insert = text("""
                    INSERT INTO silver.entity_map (
                        vjsales_lead_id, vjsales_booking_id,
                        farvision_customer_name, farvision_project_code, farvision_unit_no,
                        match_method, match_confidence
                    ) VALUES (
                        :lead_id, :booking_id,
                        :farv_name, :farv_project, :farv_unit,
                        'name_fuzzy', :confidence
                    )
                    ON CONFLICT (vjsales_lead_id) DO NOTHING
                """)
                conn.execute(insert, {
                    "lead_id": row.lead_id,
                    "booking_id": row.booking_id,
                    "farv_name": row.farv_customer_name,
                    "farv_project": row.farv_project_code,
                    "farv_unit": row.farv_unit_no,
                    "confidence": confidence,
                })
                matched += 1
            else:
                # Low confidence — queue for manual review
                queue_insert = text("""
                    INSERT INTO silver.entity_resolution_queue (
                        vjsales_lead_id, vjsales_lead_name, vjsales_phone,
                        vjsales_project, vjsales_unit,
                        farvision_customer_name, farvision_project_code, farvision_unit_no,
                        candidate_confidence, match_method, reason
                    ) VALUES (
                        :lead_id, :lead_name, :phone,
                        :vj_project, :vj_unit,
                        :farv_name, :farv_project, :farv_unit,
                        :confidence, 'name_fuzzy',
                        :reason
                    )
                """)
                conn.execute(queue_insert, {
                    "lead_id": row.lead_id,
                    "lead_name": row.lead_name,
                    "phone": row.phone,
                    "vj_project": row.project_name,
                    "vj_unit": row.unit_no,
                    "farv_name": row.farv_customer_name,
                    "farv_project": row.farv_project_code,
                    "farv_unit": row.farv_unit_no,
                    "confidence": confidence,
                    "reason": f"Name similarity {confidence:.2f} below auto-resolve threshold",
                })
                queued += 1

        return matched, queued
