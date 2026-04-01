"""
Snapshot Transformer — Generates daily funnel snapshots for trend analysis.
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
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        date_key = int(snapshot_date.strftime("%Y%m%d"))

        query = text("""
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
                p.project_key,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'inquiry') AS total_inquiries,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'site_visit') AS total_site_visits,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'booking') AS total_bookings,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'agreement') AS total_agreements,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'registered') AS total_registered,
                COUNT(*) FILTER (WHERE f.pipeline_stage = 'cancelled') AS total_cancelled,
                COUNT(*) FILTER (
                    WHERE f.pipeline_stage NOT IN ('cancelled', 'registered')
                ) AS total_active_leads,
                -- Conversion rates
                ROUND(
                    COUNT(*) FILTER (WHERE f.pipeline_stage = 'site_visit') * 100.0 /
                    NULLIF(COUNT(*) FILTER (WHERE f.pipeline_stage = 'inquiry'), 0),
                    2
                ),
                ROUND(
                    COUNT(*) FILTER (WHERE f.pipeline_stage = 'booking') * 100.0 /
                    NULLIF(COUNT(*) FILTER (WHERE f.pipeline_stage = 'site_visit'), 0),
                    2
                ),
                ROUND(
                    COUNT(*) FILTER (WHERE f.pipeline_stage = 'agreement') * 100.0 /
                    NULLIF(COUNT(*) FILTER (WHERE f.pipeline_stage = 'booking'), 0),
                    2
                )
            FROM gold.fact_lead_pipeline f
            JOIN gold.dim_projects p ON f.project_key = p.project_key
            WHERE f.event_date_key <= :date_key
            GROUP BY p.project_key
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
