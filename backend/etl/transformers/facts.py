"""
Fact Transformers — Build gold.fact_* tables from bronze + silver data.
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class FactTransformer:
    """Builds and updates gold-layer fact tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def transform_all(self):
        """Run all fact transformations."""
        self.build_fact_lead_pipeline()
        self.build_fact_collections()

    def build_fact_lead_pipeline(self):
        """
        Build gold.fact_lead_pipeline from VJ Sales leads, visits, and bookings.
        Each row represents a stage transition event in a lead's lifecycle.
        """
        with self.engine.begin() as conn:
            # Insert inquiry events (from leads table)
            inquiry_count = self._insert_inquiry_events(conn)

            # Insert site visit events
            visit_count = self._insert_site_visit_events(conn)

            # Insert booking events
            booking_count = self._insert_booking_events(conn)

            logger.info(
                "fact_lead_pipeline: +%d inquiries, +%d visits, +%d bookings",
                inquiry_count, visit_count, booking_count,
            )

    def _insert_inquiry_events(self, conn) -> int:
        """Insert inquiry-stage events for new leads."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                customer_key, project_key, sales_person_key, source_key,
                event_date_key, pipeline_stage, event_timestamp
            )
            SELECT
                c.customer_key,
                p.project_key,
                sp.sales_person_key,
                ls.source_key,
                TO_CHAR(l.created_date, 'YYYYMMDD')::INT,
                'inquiry',
                l.created_date
            FROM bronze.stg_vjsales_leads l
            JOIN silver.entity_map em ON l.lead_id = em.vjsales_lead_id
            JOIN gold.dim_customers c ON c.unified_customer_id = em.unified_customer_id
            LEFT JOIN gold.dim_projects p ON p.project_name = (
                SELECT pc.canonical_name FROM silver.project_crosswalk pc
                WHERE pc.vjsales_project_name = l.project_interest
            )
            LEFT JOIN gold.dim_sales_persons sp ON sp.name = l.assigned_to
            LEFT JOIN gold.dim_lead_sources ls ON ls.source_name = l.source
            WHERE l._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_leads l2
                WHERE l2.lead_id = l.lead_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.fact_lead_pipeline f
                WHERE f.customer_key = c.customer_key
                AND f.pipeline_stage = 'inquiry'
            )
        """)
        result = conn.execute(query)
        return result.rowcount

    def _insert_site_visit_events(self, conn) -> int:
        """Insert site-visit stage events."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                customer_key, project_key, sales_person_key,
                event_date_key, pipeline_stage, previous_stage,
                event_timestamp
            )
            SELECT
                c.customer_key,
                p.project_key,
                sp.sales_person_key,
                TO_CHAR(v.visit_date, 'YYYYMMDD')::INT,
                'site_visit',
                'inquiry',
                v.visit_date::timestamp
            FROM bronze.stg_vjsales_site_visits v
            JOIN bronze.stg_vjsales_leads l ON v.lead_id = l.lead_id
                AND l._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjsales_leads l2
                    WHERE l2.lead_id = l.lead_id
                )
            JOIN silver.entity_map em ON l.lead_id = em.vjsales_lead_id
            JOIN gold.dim_customers c ON c.unified_customer_id = em.unified_customer_id
            LEFT JOIN gold.dim_projects p ON p.project_name = (
                SELECT pc.canonical_name FROM silver.project_crosswalk pc
                WHERE pc.vjsales_project_name = v.project_name
            )
            LEFT JOIN gold.dim_sales_persons sp ON sp.name = v.accompanied_by
            WHERE v._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_site_visits v2
                WHERE v2.visit_id = v.visit_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.fact_lead_pipeline f
                WHERE f.customer_key = c.customer_key
                AND f.pipeline_stage = 'site_visit'
                AND f.event_date_key = TO_CHAR(v.visit_date, 'YYYYMMDD')::INT
            )
        """)
        result = conn.execute(query)
        return result.rowcount

    def _insert_booking_events(self, conn) -> int:
        """Insert booking-stage events."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                customer_key, project_key, unit_key, sales_person_key,
                event_date_key, pipeline_stage, previous_stage,
                agreement_value, booking_amount, event_timestamp
            )
            SELECT
                c.customer_key,
                p.project_key,
                u.unit_key,
                sp.sales_person_key,
                TO_CHAR(b.booking_date, 'YYYYMMDD')::INT,
                'booking',
                'site_visit',
                b.agreement_value,
                b.booking_amount,
                b.booking_date::timestamp
            FROM bronze.stg_vjsales_bookings b
            JOIN silver.entity_map em ON b.lead_id = em.vjsales_lead_id
            JOIN gold.dim_customers c ON c.unified_customer_id = em.unified_customer_id
            LEFT JOIN silver.project_crosswalk pc ON b.project_name = pc.vjsales_project_name
            LEFT JOIN gold.dim_projects p ON p.project_name = pc.canonical_name
            LEFT JOIN gold.dim_units u ON u.project_key = p.project_key AND u.unit_no = b.unit_no
            LEFT JOIN gold.dim_sales_persons sp ON sp.name = b.sales_person
            WHERE b._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_bookings b2
                WHERE b2.booking_id = b.booking_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.fact_lead_pipeline f
                WHERE f.customer_key = c.customer_key
                AND f.pipeline_stage = 'booking'
                AND f.unit_key = u.unit_key
            )
        """)
        result = conn.execute(query)
        return result.rowcount

    def build_fact_collections(self):
        """
        Build gold.fact_collections from Farvision receipts and demands.
        Links to customers via silver.entity_map.
        """
        with self.engine.begin() as conn:
            receipt_count = self._insert_receipts(conn)
            demand_count = self._insert_demands(conn)
            logger.info(
                "fact_collections: +%d receipts, +%d demands",
                receipt_count, demand_count,
            )

    def _insert_receipts(self, conn) -> int:
        """Insert receipt transactions into fact_collections."""
        query = text("""
            INSERT INTO gold.fact_collections (
                customer_key, project_key, unit_key,
                transaction_date_key, transaction_type,
                amount, payment_mode
            )
            SELECT
                c.customer_key,
                p.project_key,
                u.unit_key,
                TO_CHAR(r.receipt_date, 'YYYYMMDD')::INT,
                'receipt',
                r.amount,
                r.payment_mode
            FROM bronze.stg_farvision_receipts r
            JOIN silver.entity_map em
                ON em.farvision_project_code = r.project_code
                AND em.farvision_unit_no = r.unit_no
            JOIN gold.dim_customers c ON c.unified_customer_id = em.unified_customer_id
            LEFT JOIN silver.project_crosswalk pc ON r.project_code = pc.farvision_project_code
            LEFT JOIN gold.dim_projects p ON p.project_name = pc.canonical_name
            LEFT JOIN gold.dim_units u ON u.project_key = p.project_key AND u.unit_no = r.unit_no
            WHERE r._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_farvision_receipts r2
                WHERE r2.receipt_id = r.receipt_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.fact_collections fc
                WHERE fc.customer_key = c.customer_key
                AND fc.transaction_type = 'receipt'
                AND fc.transaction_date_key = TO_CHAR(r.receipt_date, 'YYYYMMDD')::INT
                AND fc.amount = r.amount
            )
        """)
        result = conn.execute(query)
        return result.rowcount

    def _insert_demands(self, conn) -> int:
        """Insert demand transactions into fact_collections."""
        query = text("""
            INSERT INTO gold.fact_collections (
                customer_key, project_key, unit_key,
                transaction_date_key, transaction_type,
                amount, milestone
            )
            SELECT
                c.customer_key,
                p.project_key,
                u.unit_key,
                TO_CHAR(d.demand_date, 'YYYYMMDD')::INT,
                'demand',
                d.demand_amount,
                d.milestone
            FROM bronze.stg_farvision_demands d
            JOIN silver.entity_map em
                ON em.farvision_project_code = d.project_code
                AND em.farvision_unit_no = d.unit_no
            JOIN gold.dim_customers c ON c.unified_customer_id = em.unified_customer_id
            LEFT JOIN silver.project_crosswalk pc ON d.project_code = pc.farvision_project_code
            LEFT JOIN gold.dim_projects p ON p.project_name = pc.canonical_name
            LEFT JOIN gold.dim_units u ON u.project_key = p.project_key AND u.unit_no = d.unit_no
            WHERE d._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_farvision_demands d2
                WHERE d2.demand_id = d.demand_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.fact_collections fc
                WHERE fc.customer_key = c.customer_key
                AND fc.transaction_type = 'demand'
                AND fc.transaction_date_key = TO_CHAR(d.demand_date, 'YYYYMMDD')::INT
                AND fc.amount = d.demand_amount
            )
        """)
        result = conn.execute(query)
        return result.rowcount
