"""
Dimension Transformers — Build gold.dim_* tables from bronze + silver data.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DimensionTransformer:
    """Builds and updates gold-layer dimension tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def transform_all(self):
        """Run all dimension transformations."""
        self.build_dim_date()
        self.build_dim_projects()
        self.build_dim_units()
        self.build_dim_customers()
        self.build_dim_sales_persons()
        self.build_dim_lead_sources()

    def build_dim_date(self, start_year: int = 2020, end_year: int = 2030):
        """
        Populate gold.dim_date with all dates in range.
        Includes fiscal year logic (April-March for Indian FY).
        """
        with self.engine.begin() as conn:
            # Check if already populated
            count = conn.execute(text("SELECT COUNT(*) FROM gold.dim_date")).scalar()
            if count > 0:
                logger.info("dim_date already populated (%d rows), skipping", count)
                return

            current = date(start_year, 1, 1)
            end = date(end_year, 12, 31)
            rows = []

            while current <= end:
                # Fiscal year: April-March (FY2026 = Apr 2025 - Mar 2026)
                if current.month >= 4:
                    fiscal_year = current.year + 1
                    fiscal_q_month = current.month - 3  # Apr=1, Jul=4, Oct=7, Jan=10
                else:
                    fiscal_year = current.year
                    fiscal_q_month = current.month + 9

                fiscal_quarter = f"Q{(fiscal_q_month - 1) // 3 + 1}"
                calendar_quarter = f"Q{(current.month - 1) // 3 + 1}"

                rows.append({
                    "date_key": int(current.strftime("%Y%m%d")),
                    "full_date": current,
                    "day_of_week": current.strftime("%A"),
                    "day_of_month": current.day,
                    "week_of_year": current.isocalendar()[1],
                    "month_number": current.month,
                    "month_name": current.strftime("%B"),
                    "quarter": calendar_quarter,
                    "fiscal_quarter": fiscal_quarter,
                    "calendar_year": current.year,
                    "fiscal_year": fiscal_year,
                    "fiscal_year_label": f"FY{fiscal_year}",
                    "is_weekend": current.weekday() >= 5,
                    "is_month_end": (current + timedelta(days=1)).month != current.month,
                })

                current += timedelta(days=1)

            insert = text("""
                INSERT INTO gold.dim_date (
                    date_key, full_date, day_of_week, day_of_month, week_of_year,
                    month_number, month_name, quarter, fiscal_quarter,
                    calendar_year, fiscal_year, fiscal_year_label,
                    is_weekend, is_month_end
                ) VALUES (
                    :date_key, :full_date, :day_of_week, :day_of_month, :week_of_year,
                    :month_number, :month_name, :quarter, :fiscal_quarter,
                    :calendar_year, :fiscal_year, :fiscal_year_label,
                    :is_weekend, :is_month_end
                )
                ON CONFLICT (date_key) DO NOTHING
            """)
            conn.execute(insert, rows)
            logger.info("Populated dim_date with %d rows", len(rows))

    def build_dim_projects(self):
        """Upsert gold.dim_projects from silver.project_crosswalk."""
        query = text("""
            INSERT INTO gold.dim_projects (project_name, phase_name, status)
            SELECT
                pc.canonical_name,
                pc.phase_name,
                'active'
            FROM silver.project_crosswalk pc
            WHERE pc.canonical_name NOT IN (
                SELECT project_name FROM gold.dim_projects
            )
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Inserted %d new projects into dim_projects", result.rowcount)

    def build_dim_units(self):
        """Upsert gold.dim_units from VJ Sales bookings."""
        query = text("""
            INSERT INTO gold.dim_units (
                project_key, unit_no, wing, floor, unit_type,
                carpet_area_sqft, current_status
            )
            SELECT DISTINCT ON (p.project_key, b.unit_no)
                p.project_key,
                b.unit_no,
                b.wing,
                b.floor,
                b.unit_type,
                b.carpet_area,
                b.status
            FROM bronze.stg_vjsales_bookings b
            JOIN silver.project_crosswalk pc ON b.project_name = pc.vjsales_project_name
            JOIN gold.dim_projects p ON p.project_name = pc.canonical_name
            WHERE b._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_bookings b2
                WHERE b2.booking_id = b.booking_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM gold.dim_units u
                WHERE u.project_key = p.project_key AND u.unit_no = b.unit_no
            )
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Inserted %d new units into dim_units", result.rowcount)

    def build_dim_customers(self):
        """Upsert gold.dim_customers from silver.entity_map + bronze data."""
        query = text("""
            INSERT INTO gold.dim_customers (
                unified_customer_id, customer_name, phone, email,
                first_inquiry_date, lead_source, source_system_origin
            )
            SELECT
                em.unified_customer_id,
                COALESCE(l.lead_name, em.farvision_customer_name),
                l.phone,
                l.email,
                l.created_date::date,
                l.source,
                'vjsales'
            FROM silver.entity_map em
            LEFT JOIN bronze.stg_vjsales_leads l ON em.vjsales_lead_id = l.lead_id
                AND l._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjsales_leads l2
                    WHERE l2.lead_id = l.lead_id
                )
            WHERE em.unified_customer_id NOT IN (
                SELECT unified_customer_id FROM gold.dim_customers
            )
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Inserted %d new customers into dim_customers", result.rowcount)

    def build_dim_sales_persons(self):
        """Upsert gold.dim_sales_persons from VJ Sales data."""
        query = text("""
            INSERT INTO gold.dim_sales_persons (name, is_active)
            SELECT DISTINCT assigned_to, TRUE
            FROM bronze.stg_vjsales_leads
            WHERE assigned_to IS NOT NULL
            AND assigned_to NOT IN (
                SELECT name FROM gold.dim_sales_persons
            )
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Inserted %d new sales persons", result.rowcount)

    def build_dim_lead_sources(self):
        """Upsert gold.dim_lead_sources from VJ Sales lead data."""
        query = text("""
            INSERT INTO gold.dim_lead_sources (source_name, source_category)
            SELECT DISTINCT
                source,
                CASE
                    WHEN source ILIKE '%walk%' THEN 'organic'
                    WHEN source ILIKE '%referral%' THEN 'referral'
                    WHEN source ILIKE '%digital%' OR source ILIKE '%facebook%'
                         OR source ILIKE '%google%' THEN 'paid'
                    WHEN source ILIKE '%channel%' OR source ILIKE '%cp%'
                         OR source ILIKE '%broker%' THEN 'channel_partner'
                    ELSE 'other'
                END
            FROM bronze.stg_vjsales_leads
            WHERE source IS NOT NULL
            AND source NOT IN (
                SELECT source_name FROM gold.dim_lead_sources
            )
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Inserted %d new lead sources", result.rowcount)
