"""
Dimension Transformers — Build gold.dim_* tables from bronze + silver data.

Sources:
  - bronze.stg_fv_*            (Farvision ERP staging tables)
  - bronze.stg_vj_*            (VJ Sales App staging tables)
  - silver.project_crosswalk   (unified project mapping)
  - silver.entity_map          (cross-system identity resolution)
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
        """Run all dimension transformations in dependency order."""
        self.build_dim_date()
        self.build_dim_projects()
        self.build_dim_typologies()
        self.build_dim_units()
        self.build_dim_customers()
        self.build_dim_sales_persons()
        self.build_dim_lead_sources()

    # ------------------------------------------------------------------
    # dim_date
    # ------------------------------------------------------------------
    def build_dim_date(self, start_year: int = 2015, end_year: int = 2035):
        """
        Populate gold.dim_date with all dates in range.
        Includes fiscal year logic (April-March for Indian FY) and
        fiscal_year_id mapping for known Farvision fiscal year IDs.
        """
        # Known Farvision FiscalYearId mappings
        FISCAL_YEAR_ID_MAP = {
            2026: 56,   # FY2025-26
            2025: 52,   # FY2024-25
        }

        with self.engine.begin() as conn:
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
                    fiscal_q_month = current.month - 3  # Apr=1, Jul=4, Oct=7
                else:
                    fiscal_year = current.year
                    fiscal_q_month = current.month + 9  # Jan=10, Feb=11, Mar=12

                fiscal_quarter = f"Q{(fiscal_q_month - 1) // 3 + 1}"
                calendar_quarter = f"Q{(current.month - 1) // 3 + 1}"
                fiscal_year_id = FISCAL_YEAR_ID_MAP.get(fiscal_year)

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
                    "fiscal_year_id": fiscal_year_id,
                    "is_weekend": current.weekday() >= 5,
                    "is_month_end": (current + timedelta(days=1)).month != current.month,
                })

                current += timedelta(days=1)

            insert = text("""
                INSERT INTO gold.dim_date (
                    date_key, full_date, day_of_week, day_of_month, week_of_year,
                    month_number, month_name, quarter, fiscal_quarter,
                    calendar_year, fiscal_year, fiscal_year_label, fiscal_year_id,
                    is_weekend, is_month_end
                ) VALUES (
                    :date_key, :full_date, :day_of_week, :day_of_month, :week_of_year,
                    :month_number, :month_name, :quarter, :fiscal_quarter,
                    :calendar_year, :fiscal_year, :fiscal_year_label, :fiscal_year_id,
                    :is_weekend, :is_month_end
                )
                ON CONFLICT (date_key) DO NOTHING
            """)
            conn.execute(insert, rows)
            logger.info("Populated dim_date with %d rows", len(rows))

    # ------------------------------------------------------------------
    # dim_projects
    # ------------------------------------------------------------------
    def build_dim_projects(self):
        """
        Upsert gold.dim_projects from silver.project_crosswalk.
        Uses farvision_bu_id as the join key.
        """
        query = text("""
            INSERT INTO gold.dim_projects (bu_id, project_name, phase_name, status)
            SELECT
                pc.farvision_bu_id,
                pc.canonical_name,
                pc.phase_name,
                'active'
            FROM silver.project_crosswalk pc
            ON CONFLICT (bu_id) DO UPDATE SET
                project_name = EXCLUDED.project_name,
                phase_name   = EXCLUDED.phase_name,
                updated_at   = NOW()
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_projects", result.rowcount)

    # ------------------------------------------------------------------
    # dim_typologies
    # ------------------------------------------------------------------
    def build_dim_typologies(self):
        """
        Upsert gold.dim_typologies from bronze.stg_fv_dim_typology_master.
        Generates a human-friendly display_name (e.g. "3.00BHK" -> "3 BHK")
        and flags XL/XR variants.
        """
        query = text("""
            INSERT INTO gold.dim_typologies (
                typology_id, typology_code, typology, display_name, is_base_variant
            )
            SELECT
                t."TypologyId",
                t."TypologyCode",
                t."Typology",
                -- Generate display_name: strip trailing zeros from numeric prefix,
                -- add space before BHK, keep variant suffix
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        t."Typology",
                        '^([0-9]+)\\.?0*BHK',
                        '\\1 BHK'
                    ),
                    '\\s+', ' ', 'g'
                ),
                -- Base variant if no XL/XR/etc. suffix
                CASE
                    WHEN t."Typology" ~* '(XL|XR|JODI|DUPLEX|PENTHOUSE)'
                    THEN FALSE
                    ELSE TRUE
                END
            FROM bronze.stg_fv_dim_typology_master t
            WHERE t._sync_id = (
                SELECT MAX(t2._sync_id)
                FROM bronze.stg_fv_dim_typology_master t2
                WHERE t2."TypologyId" = t."TypologyId"
            )
            ON CONFLICT (typology_id) DO UPDATE SET
                typology_code  = EXCLUDED.typology_code,
                typology       = EXCLUDED.typology,
                display_name   = EXCLUDED.display_name,
                is_base_variant = EXCLUDED.is_base_variant
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_typologies", result.rowcount)

    # ------------------------------------------------------------------
    # dim_units
    # ------------------------------------------------------------------
    def build_dim_units(self):
        """
        Upsert gold.dim_units from Farvision unit master + unit movement,
        with optional VJ Sales inventory data merged in.

        Sources:
          - bronze.stg_fv_dim_unit_master   (UnitId, UnitCode, BUId, TypologyId)
          - bronze.stg_fv_fact_unit_movement (UnitStatus, Area, CarpetArea)
          - bronze.stg_vj_inventory         (saleable_area overlay via farvisionUnitId)
          - gold.dim_projects               (project_key via bu_id)
          - gold.dim_typologies             (typology_key via typology_id)
        """
        query = text("""
            INSERT INTO gold.dim_units (
                farvision_unit_id, project_key, typology_key,
                unit_no, wing, floor, unit_status, farvision_status,
                saleable_area, carpet_area
            )
            SELECT
                um."UnitId",
                dp.project_key,
                dt.typology_key,
                um."UnitCode",
                ph."Level3",         -- wing from project hierarchy
                um."FloorId",
                mv."UnitStatus",
                CASE mv."UnitStatus"
                    WHEN 1 THEN 'Sold'
                    WHEN 2 THEN 'Available'
                    WHEN 3 THEN 'Blocked'
                    ELSE 'Unknown'
                END,
                COALESCE(vi."saleableArea", mv."Area"),
                mv."CarpetArea"
            FROM bronze.stg_fv_dim_unit_master um
            -- Deduplicate: latest sync per UnitId
            INNER JOIN (
                SELECT "UnitId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_fv_dim_unit_master
                GROUP BY "UnitId"
            ) um_latest ON um."UnitId" = um_latest."UnitId"
                       AND um._sync_id = um_latest.max_sync_id
            -- Join to dim_projects via BUId
            INNER JOIN gold.dim_projects dp ON dp.bu_id = um."BUId"
            -- Optional: typology
            LEFT JOIN gold.dim_typologies dt ON dt.typology_id = um."TypologyId"
            -- Latest unit movement for status and area
            LEFT JOIN LATERAL (
                SELECT mv2."UnitStatus", mv2."Area", mv2."CarpetArea"
                FROM bronze.stg_fv_fact_unit_movement mv2
                WHERE mv2."UnitId" = um."UnitId"
                ORDER BY mv2._sync_id DESC
                LIMIT 1
            ) mv ON TRUE
            -- Optional: project hierarchy for wing name
            LEFT JOIN LATERAL (
                SELECT ph2."Level3"
                FROM bronze.stg_fv_dim_project_hierarchy ph2
                WHERE ph2."BUId" = um."BUId"
                ORDER BY ph2._sync_id DESC
                LIMIT 1
            ) ph ON TRUE
            -- Optional: VJ Sales inventory overlay (matched via farvisionUnitId)
            LEFT JOIN LATERAL (
                SELECT vi2."saleableArea"
                FROM bronze.stg_vj_inventory vi2
                WHERE vi2."farvisionUnitId" = um."UnitId"
                ORDER BY vi2._sync_id DESC
                LIMIT 1
            ) vi ON TRUE
            ON CONFLICT (farvision_unit_id) DO UPDATE SET
                project_key     = EXCLUDED.project_key,
                typology_key    = EXCLUDED.typology_key,
                unit_no         = EXCLUDED.unit_no,
                wing            = EXCLUDED.wing,
                floor           = EXCLUDED.floor,
                unit_status     = EXCLUDED.unit_status,
                farvision_status = EXCLUDED.farvision_status,
                saleable_area   = EXCLUDED.saleable_area,
                carpet_area     = EXCLUDED.carpet_area,
                updated_at      = NOW()
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_units", result.rowcount)

    # ------------------------------------------------------------------
    # dim_customers
    # ------------------------------------------------------------------
    def build_dim_customers(self):
        """
        Upsert gold.dim_customers from Farvision customer detail.

        Two-path approach:
        1. Direct from Farvision DimCustomerDetail (always works)
        2. Enhanced via entity_map when VJ Sales data is available

        Source: bronze.stg_fv_dim_customer_detail
        """
        query = text("""
            INSERT INTO gold.dim_customers (
                unified_customer_id, farvision_ledger_id,
                full_name, customer_name, mobile, email, pan_number,
                source_system_origin
            )
            SELECT DISTINCT ON (c."LedgerCustId")
                gen_random_uuid(),
                c."LedgerCustId",
                c."FullName",
                c."Customer",
                c."MobileNo",
                c."EmailId",
                c."PanNo",
                'farvision'
            FROM bronze.stg_fv_dim_customer_detail c
            WHERE c."LedgerCustId" IS NOT NULL
              AND c._sync_id = (
                  SELECT MAX(c2._sync_id)
                  FROM bronze.stg_fv_dim_customer_detail c2
                  WHERE c2."LedgerCustId" = c."LedgerCustId"
              )
              AND c."LedgerCustId" NOT IN (
                  SELECT farvision_ledger_id FROM gold.dim_customers
                  WHERE farvision_ledger_id IS NOT NULL
              )
            ORDER BY c."LedgerCustId", c._sync_id DESC
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_customers", result.rowcount)

    # ------------------------------------------------------------------
    # dim_sales_persons
    # ------------------------------------------------------------------
    def build_dim_sales_persons(self):
        """
        Upsert gold.dim_sales_persons from Farvision booking master.
        Deduplicated by SalesPersonId.

        Source: bronze.stg_fv_dim_booking_master (SalesPersonId, SalesPersonName)
        """
        query = text("""
            INSERT INTO gold.dim_sales_persons (farvision_sales_person_id, name, is_active)
            SELECT DISTINCT ON (b."SalesPersonId")
                b."SalesPersonId",
                b."SalesPersonName",
                TRUE
            FROM bronze.stg_fv_dim_booking_master b
            WHERE b."SalesPersonId" IS NOT NULL
              AND b._sync_id = (
                  SELECT MAX(b2._sync_id)
                  FROM bronze.stg_fv_dim_booking_master b2
                  WHERE b2."SalesPersonId" = b."SalesPersonId"
              )
            ORDER BY b."SalesPersonId", b._sync_id DESC
            ON CONFLICT (farvision_sales_person_id) DO UPDATE SET
                name = EXCLUDED.name
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_sales_persons", result.rowcount)

    # ------------------------------------------------------------------
    # dim_lead_sources
    # ------------------------------------------------------------------
    def build_dim_lead_sources(self):
        """
        Upsert gold.dim_lead_sources from VJ Sales leads + channel partners.

        Sources:
          - bronze.stg_vj_leads  (leadType, leadCategory, cpId)
          - bronze.stg_vj_cp     (cpId, name, companyName)
        """
        query = text("""
            WITH lead_sources AS (
                SELECT DISTINCT
                    COALESCE(l."leadType", 'Unknown') AS source_name,
                    CASE
                        WHEN l."leadType" ILIKE '%%walk%%' THEN 'organic'
                        WHEN l."leadType" ILIKE '%%referral%%' THEN 'referral'
                        WHEN l."leadType" ILIKE '%%digital%%'
                             OR l."leadType" ILIKE '%%facebook%%'
                             OR l."leadType" ILIKE '%%google%%' THEN 'paid'
                        WHEN l."cpId" IS NOT NULL THEN 'channel_partner'
                        WHEN l."leadType" ILIKE '%%channel%%'
                             OR l."leadType" ILIKE '%%cp%%'
                             OR l."leadType" ILIKE '%%broker%%' THEN 'channel_partner'
                        ELSE 'other'
                    END AS source_category,
                    cp.name AS channel_partner_name,
                    l."cpId" AS cp_id
                FROM bronze.stg_vj_leads l
                -- Deduplicate leads by latest sync per leadId
                INNER JOIN (
                    SELECT "leadId", MAX(_sync_id) AS max_sync_id
                    FROM bronze.stg_vj_leads
                    GROUP BY "leadId"
                ) l_latest ON l."leadId" = l_latest."leadId"
                          AND l._sync_id = l_latest.max_sync_id
                -- Optional: channel partner details
                LEFT JOIN LATERAL (
                    SELECT cp2.name
                    FROM bronze.stg_vj_cp cp2
                    WHERE cp2."cpId" = l."cpId"
                    ORDER BY cp2._sync_id DESC
                    LIMIT 1
                ) cp ON l."cpId" IS NOT NULL
                WHERE l."leadType" IS NOT NULL
            )
            INSERT INTO gold.dim_lead_sources (
                source_name, source_category, channel_partner_name, cp_id
            )
            SELECT source_name, source_category, channel_partner_name, cp_id
            FROM lead_sources
            ON CONFLICT (source_name) DO UPDATE SET
                source_category      = EXCLUDED.source_category,
                channel_partner_name = COALESCE(EXCLUDED.channel_partner_name, gold.dim_lead_sources.channel_partner_name),
                cp_id                = COALESCE(EXCLUDED.cp_id, gold.dim_lead_sources.cp_id)
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_lead_sources", result.rowcount)
