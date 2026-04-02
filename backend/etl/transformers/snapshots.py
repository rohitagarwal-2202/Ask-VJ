"""
Snapshot Transformer — Generates daily funnel snapshots for trend analysis.

Combines:
- gold.fact_lead_pipeline (VJ Sales lead stages)
- gold.fact_bookings (Farvision confirmed bookings)
to produce a unified daily view per project.
"""

import logging
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class SnapshotTransformer:
    """Generates daily funnel snapshots from gold fact tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def build_daily_snapshot(self, snapshot_date: date | None = None):
        """
        Build or refresh the daily funnel snapshot for a given date.
        Defaults to today if no date provided.

        Uses fact_lead_pipeline for inquiry/site_visit counts and
        fact_bookings for confirmed booking/agreement/registration counts.
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        date_key = int(snapshot_date.strftime("%Y%m%d"))

        query = text("""
            WITH pipeline_counts AS (
                SELECT
                    p.project_key,
                    COUNT(*) FILTER (WHERE f.pipeline_stage = 'inquiry') AS total_inquiries,
                    COUNT(*) FILTER (WHERE f.pipeline_stage = 'site_visit') AS total_site_visits,
                    COUNT(*) FILTER (
                        WHERE f.pipeline_stage NOT IN ('cancelled', 'registered')
                    ) AS total_active_leads
                FROM gold.fact_lead_pipeline f
                JOIN gold.dim_projects p ON f.project_key = p.project_key
                WHERE f.event_date_key <= :date_key
                GROUP BY p.project_key
            ),
            booking_counts AS (
                SELECT
                    b.project_key,
                    COUNT(*) FILTER (WHERE NOT b.is_cancelled) AS total_bookings,
                    COUNT(*) FILTER (WHERE b.agreement_date IS NOT NULL AND NOT b.is_cancelled) AS total_agreements,
                    COUNT(*) FILTER (WHERE b.registration_date IS NOT NULL AND NOT b.is_cancelled) AS total_registered,
                    COUNT(*) FILTER (WHERE b.is_cancelled) AS total_cancelled
                FROM gold.fact_bookings b
                WHERE b.booking_date <= (SELECT full_date FROM gold.dim_date WHERE date_key = :date_key)
                GROUP BY b.project_key
            )
            INSERT INTO gold.fact_daily_funnel_snapshot (
                snapshot_date_key, project_key,
                total_inquiries, total_site_visits, total_bookings,
                total_agreements, total_registered, total_cancelled,
                total_active_leads,
                inquiry_to_visit_rate, visit_to_booking_rate,
                booking_to_agreement_rate
            )
            SELECT
                :date_key,
                COALESCE(pc.project_key, bc.project_key),
                COALESCE(pc.total_inquiries, 0),
                COALESCE(pc.total_site_visits, 0),
                COALESCE(bc.total_bookings, 0),
                COALESCE(bc.total_agreements, 0),
                COALESCE(bc.total_registered, 0),
                COALESCE(bc.total_cancelled, 0),
                COALESCE(pc.total_active_leads, 0),
                -- Conversion rates
                ROUND(
                    COALESCE(pc.total_site_visits, 0) * 100.0 /
                    NULLIF(COALESCE(pc.total_inquiries, 0), 0),
                    2
                ),
                ROUND(
                    COALESCE(bc.total_bookings, 0) * 100.0 /
                    NULLIF(COALESCE(pc.total_site_visits, 0), 0),
                    2
                ),
                ROUND(
                    COALESCE(bc.total_agreements, 0) * 100.0 /
                    NULLIF(COALESCE(bc.total_bookings, 0), 0),
                    2
                )
            FROM pipeline_counts pc
            FULL OUTER JOIN booking_counts bc ON pc.project_key = bc.project_key
            ON CONFLICT (snapshot_date_key, project_key) DO UPDATE
                SET total_inquiries = EXCLUDED.total_inquiries,
                    total_site_visits = EXCLUDED.total_site_visits,
                    total_bookings = EXCLUDED.total_bookings,
                    total_agreements = EXCLUDED.total_agreements,
                    total_registered = EXCLUDED.total_registered,
                    total_cancelled = EXCLUDED.total_cancelled,
                    total_active_leads = EXCLUDED.total_active_leads,
                    inquiry_to_visit_rate = EXCLUDED.inquiry_to_visit_rate,
                    visit_to_booking_rate = EXCLUDED.visit_to_booking_rate,
                    booking_to_agreement_rate = EXCLUDED.booking_to_agreement_rate,
                    created_at = NOW()
        """)

        with self.engine.begin() as conn:
            result = conn.execute(query, {"date_key": date_key})
            logger.info(
                "Daily snapshot for %s: %d project rows upserted",
                snapshot_date, result.rowcount,
            )
