"""
Dimension Transformers — Build silver.dim_* tables from bronze staging data.

Sources:
  - bronze.stg_vj_*            (VJ Sales App staging tables)
  - bronze.stg_vj_cp           (Channel Partners)
  - bronze.stg_vj_fos          (Field Officers)
  - silver.project_crosswalk   (unified project mapping)
"""

import logging
from datetime import date, timedelta
from calendar import monthrange

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Indian fiscal year starts in April
FISCAL_YEAR_START_MONTH = 4


class DimensionTransformer:
    """Builds and updates silver-layer dimension tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def transform_all(self):
        """Run all dimension transformations in dependency order."""
        self.build_dim_calendar()
        self.build_dim_country()
        self.build_dim_project()
        self.build_dim_project_unit()
        self.build_dim_employee()
        self.build_dim_channel_partner()
        self.build_dim_channel_partner_fos()
        self.build_dim_buyer()

    # ------------------------------------------------------------------
    # dim_calendar
    # ------------------------------------------------------------------
    def build_dim_calendar(self, start_year: int = 2015, end_year: int = 2035):
        """
        Populate silver.dim_calendar with all dates in range.
        Includes fiscal year logic (April-March for Indian FY).
        calendar_skey uses YYYYMMDD string format.
        """
        with self.engine.begin() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM silver.dim_calendar")
            ).scalar()
            if count > 0:
                logger.info("dim_calendar already populated (%d rows), skipping", count)
                return

            current = date(start_year, 1, 1)
            end = date(end_year, 12, 31)
            rows = []

            while current <= end:
                # --- Fiscal year: April-March (FY2026 = Apr 2025 - Mar 2026) ---
                if current.month >= FISCAL_YEAR_START_MONTH:
                    fiscal_year = current.year + 1
                    fiscal_month = current.month - 3   # Apr=1 .. Dec=9
                else:
                    fiscal_year = current.year
                    fiscal_month = current.month + 9   # Jan=10, Feb=11, Mar=12

                fiscal_quarter = (fiscal_month - 1) // 3 + 1
                fiscal_day = (
                    current
                    - date(fiscal_year - 1, FISCAL_YEAR_START_MONTH, 1)
                ).days + 1

                # ISO week info
                iso_year, iso_week, iso_weekday = current.isocalendar()
                fiscal_week = (fiscal_day - 1) // 7 + 1

                # Calendar quarter
                quarter_num = (current.month - 1) // 3 + 1

                # Week of month (1-based, week starts Monday)
                first_of_month = current.replace(day=1)
                week_of_month = (current.day + first_of_month.weekday()) // 7 + 1

                # Week start/end (Monday-Sunday)
                week_start = current - timedelta(days=current.weekday())
                week_end = week_start + timedelta(days=6)

                # Month start/end
                month_start = first_of_month
                month_end = current.replace(
                    day=monthrange(current.year, current.month)[1]
                )

                # Quarter start/end
                q_start_month = (quarter_num - 1) * 3 + 1
                q_end_month = q_start_month + 2
                quarter_start = date(current.year, q_start_month, 1)
                quarter_end = date(
                    current.year, q_end_month,
                    monthrange(current.year, q_end_month)[1],
                )

                # Year start/end
                year_start = date(current.year, 1, 1)
                year_end = date(current.year, 12, 31)

                # Fiscal year start/end
                fiscal_year_start = date(fiscal_year - 1, FISCAL_YEAR_START_MONTH, 1)
                fiscal_year_end = date(fiscal_year, 3, 31)

                rows.append({
                    "calendar_skey": current.strftime("%Y%m%d"),
                    "calendar_dt": current,
                    "day_of_month_num": current.day,
                    "day_of_week_num": iso_weekday,          # 1=Mon .. 7=Sun
                    "day_name": current.strftime("%A"),
                    "is_weekend": current.weekday() >= 5,
                    "week_of_year_num": iso_week,
                    "week_of_month_num": week_of_month,
                    "week_start_dt": week_start,
                    "week_end_dt": week_end,
                    "month_num": current.month,
                    "month_name": current.strftime("%B"),
                    "month_short_name": current.strftime("%b"),
                    "month_start_dt": month_start,
                    "month_end_dt": month_end,
                    "quarter_num": quarter_num,
                    "quarter_start_dt": quarter_start,
                    "quarter_end_dt": quarter_end,
                    "year_num": current.year,
                    "year_start_dt": year_start,
                    "year_end_dt": year_end,
                    "month_year": current.strftime("%B %Y"),
                    "week_year": f"W{iso_week:02d} {iso_year}",
                    "fiscal_day": fiscal_day,
                    "fiscal_week": fiscal_week,
                    "fiscal_month": fiscal_month,
                    "fiscal_quarter": fiscal_quarter,
                    "fiscal_year": fiscal_year,
                    "fiscal_month_year": f"FM{fiscal_month:02d} FY{fiscal_year}",
                    "fiscal_week_year": f"FW{fiscal_week:02d} FY{fiscal_year}",
                    "fiscal_year_start_dt": fiscal_year_start,
                    "fiscal_year_end_dt": fiscal_year_end,
                    "dw_created_by": "etl_pipeline",
                })

                current += timedelta(days=1)

            insert = text("""
                INSERT INTO silver.dim_calendar (
                    calendar_skey, calendar_dt,
                    day_of_month_num, day_of_week_num, day_name, is_weekend,
                    week_of_year_num, week_of_month_num, week_start_dt, week_end_dt,
                    month_num, month_name, month_short_name, month_start_dt, month_end_dt,
                    quarter_num, quarter_start_dt, quarter_end_dt,
                    year_num, year_start_dt, year_end_dt,
                    month_year, week_year,
                    fiscal_day, fiscal_week, fiscal_month, fiscal_quarter, fiscal_year,
                    fiscal_month_year, fiscal_week_year,
                    fiscal_year_start_dt, fiscal_year_end_dt,
                    dw_created_by
                ) VALUES (
                    :calendar_skey, :calendar_dt,
                    :day_of_month_num, :day_of_week_num, :day_name, :is_weekend,
                    :week_of_year_num, :week_of_month_num, :week_start_dt, :week_end_dt,
                    :month_num, :month_name, :month_short_name, :month_start_dt, :month_end_dt,
                    :quarter_num, :quarter_start_dt, :quarter_end_dt,
                    :year_num, :year_start_dt, :year_end_dt,
                    :month_year, :week_year,
                    :fiscal_day, :fiscal_week, :fiscal_month, :fiscal_quarter, :fiscal_year,
                    :fiscal_month_year, :fiscal_week_year,
                    :fiscal_year_start_dt, :fiscal_year_end_dt,
                    :dw_created_by
                )
                ON CONFLICT (calendar_skey) DO NOTHING
            """)
            conn.execute(insert, rows)
            logger.info("Populated dim_calendar with %d rows", len(rows))

    # ------------------------------------------------------------------
    # dim_country  (seed-only — data lives in silver_schema.sql seed)
    # ------------------------------------------------------------------
    def build_dim_country(self):
        """
        Seed silver.dim_country if empty.
        Primary seed data is inserted by silver_schema.sql; this is a
        safety net to ensure the table is never empty at transform time.
        """
        with self.engine.begin() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM silver.dim_country")
            ).scalar()
            if count > 0:
                logger.info("dim_country already seeded (%d rows), skipping", count)
                return

            conn.execute(text("""
                INSERT INTO silver.dim_country
                    (country_iso_2, country_iso_3, country_full_name, currency, dw_created_by)
                VALUES
                    ('IN', 'IND', 'India', 'INR', 'etl_pipeline')
                ON CONFLICT DO NOTHING
            """))
            logger.info("Seeded dim_country with India fallback row")

    # ------------------------------------------------------------------
    # dim_project
    # ------------------------------------------------------------------
    def build_dim_project(self):
        """
        Upsert silver.dim_project from bronze.stg_vj_projects joined
        with silver.project_crosswalk for bu_id resolution.

        Source: bronze.stg_vj_projects + silver.project_crosswalk
        """
        query = text("""
            INSERT INTO silver.dim_project (
                project_skey, project_id, bu_id, project_name,
                rera_number, is_completed,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                (p."projectId")::UUID,
                pc.farvision_bu_id::VARCHAR(256),
                COALESCE(pc.canonical_name, p."projectName"),
                p."reraNumber",
                COALESCE((p."isCompleted")::BOOLEAN, FALSE),
                CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_projects p
            -- Deduplicate: latest sync per projectId
            INNER JOIN (
                SELECT "projectId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_projects
                GROUP BY "projectId"
            ) p_latest ON p."projectId" = p_latest."projectId"
                      AND p._sync_id = p_latest.max_sync_id
            -- Resolve bu_id via crosswalk
            LEFT JOIN silver.project_crosswalk pc
                ON pc.vjsales_project_name = p."projectName"
            ON CONFLICT (project_id) DO UPDATE SET
                bu_id        = EXCLUDED.bu_id,
                project_name = EXCLUDED.project_name,
                rera_number  = EXCLUDED.rera_number,
                is_completed = EXCLUDED.is_completed,
                dw_update_ts = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_project", result.rowcount)

    # ------------------------------------------------------------------
    # dim_project_unit
    # ------------------------------------------------------------------
    def build_dim_project_unit(self):
        """
        Upsert silver.dim_project_unit from bronze.stg_vj_inventory,
        looking up project_skey via bu_id in silver.dim_project.

        Source: bronze.stg_vj_inventory + bronze.stg_vj_projects
        """
        query = text("""
            INSERT INTO silver.dim_project_unit (
                project_unit_skey, project_skey, fv_unit_id,
                wing_name, floor_no, unit_no,
                saleable_area, chargeable_area, total_cost_amt, bsp_amt,
                unit_status, unit_type, display_unit_type, fv_status,
                sold_dt, paid_amt,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                dp.project_skey,
                inv."farvisionUnitId"::VARCHAR(256),
                inv."wing",
                inv."floor"::VARCHAR(256),
                inv."unitNo",
                (inv."saleableArea")::NUMERIC(18,4),
                (inv."chargeableArea")::NUMERIC(18,4),
                (inv."totalCost")::NUMERIC(18,4),
                (inv."BSP")::NUMERIC(18,4),
                inv."inventoryStatus",
                inv."type",
                inv."displayUnitType",
                inv."farvisionStatus",
                (inv."soldDate")::DATE,
                (inv."paidAmount")::NUMERIC(18,4),
                CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_inventory inv
            -- Deduplicate: latest sync per unitId
            INNER JOIN (
                SELECT "unitId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_inventory
                GROUP BY "unitId"
            ) inv_latest ON inv."unitId" = inv_latest."unitId"
                        AND inv._sync_id = inv_latest.max_sync_id
            -- Resolve project_skey via bu_id
            LEFT JOIN silver.dim_project dp
                ON dp.bu_id = inv."buId"::VARCHAR(256)
            ON CONFLICT (fv_unit_id) DO UPDATE SET
                project_skey     = EXCLUDED.project_skey,
                wing_name        = EXCLUDED.wing_name,
                floor_no         = EXCLUDED.floor_no,
                unit_no          = EXCLUDED.unit_no,
                saleable_area    = EXCLUDED.saleable_area,
                chargeable_area  = EXCLUDED.chargeable_area,
                total_cost_amt   = EXCLUDED.total_cost_amt,
                bsp_amt          = EXCLUDED.bsp_amt,
                unit_status      = EXCLUDED.unit_status,
                unit_type        = EXCLUDED.unit_type,
                display_unit_type = EXCLUDED.display_unit_type,
                fv_status        = EXCLUDED.fv_status,
                sold_dt          = EXCLUDED.sold_dt,
                paid_amt         = EXCLUDED.paid_amt,
                dw_update_ts     = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_project_unit", result.rowcount)

    # ------------------------------------------------------------------
    # dim_employee
    # ------------------------------------------------------------------
    def build_dim_employee(self):
        """
        Upsert silver.dim_employee from bronze.stg_vj_users.

        Source: bronze.stg_vj_users (VJ Sales App users)
        """
        query = text("""
            INSERT INTO silver.dim_employee (
                employee_skey, employee_id, employee_name,
                email, contact_number, role_name,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                (u."userId")::UUID,
                u."name",
                u."email",
                u."contactNumber",
                r."roleName"
            ,   CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_users u
            -- Deduplicate: latest sync per userId
            INNER JOIN (
                SELECT "userId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_users
                GROUP BY "userId"
            ) u_latest ON u."userId" = u_latest."userId"
                      AND u._sync_id = u_latest.max_sync_id
            -- Optional: role lookup
            LEFT JOIN LATERAL (
                SELECT r2."roleName"
                FROM bronze.stg_vj_roles r2
                WHERE r2."roleId" = u."roleId"
                ORDER BY r2._sync_id DESC
                LIMIT 1
            ) r ON TRUE
            ON CONFLICT (employee_id) DO UPDATE SET
                employee_name  = EXCLUDED.employee_name,
                email          = EXCLUDED.email,
                contact_number = EXCLUDED.contact_number,
                role_name      = EXCLUDED.role_name,
                dw_update_ts   = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_employee", result.rowcount)

    # ------------------------------------------------------------------
    # dim_channel_partner
    # ------------------------------------------------------------------
    def build_dim_channel_partner(self):
        """
        Upsert silver.dim_channel_partner from bronze.stg_vj_cp.

        Source: bronze.stg_vj_cp (VJ Sales channel partners)
        """
        query = text("""
            INSERT INTO silver.dim_channel_partner (
                channel_partner_skey, cp_id, cp_display_id,
                cp_type, contact_number, email,
                type_of_agent, billing_name,
                gst_business_name, gst_legal_name, proprietorship_name,
                is_gst_applicable, msme_type, msme_number,
                approval_status, rejection_reason, is_disabled,
                ledger_id,
                bank_account_holder_name, bank_account_number,
                bank_ifsc_code, bank_branch_name,
                rera_start_dt, rera_end_dt,
                src_created_ts, src_updated_ts,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                (cp."cpId")::UUID,
                cp."cpDisplayId",
                cp."cpType",
                cp."contactNumber",
                cp."email",
                cp."typeOfAgent",
                cp."billingName",
                cp."gstBusinessName",
                cp."gstLegalName",
                cp."proprietorshipName",
                COALESCE((cp."isGstApplicable")::BOOLEAN, FALSE),
                cp."msmeType",
                cp."msmeNumber",
                cp."approvalStatus",
                cp."rejectionReason",
                COALESCE((cp."isDisabled")::BOOLEAN, FALSE),
                cp."ledgerId",
                cp."bankAccountHolderName",
                cp."bankAccountNumber",
                cp."bankIfscCode",
                cp."bankBranchName",
                (cp."reraStartDate")::DATE,
                (cp."reraEndDate")::DATE,
                (cp."createdAt")::TIMESTAMP,
                (cp."updatedAt")::TIMESTAMP,
                CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_cp cp
            -- Deduplicate: latest sync per cpId
            INNER JOIN (
                SELECT "cpId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_cp
                GROUP BY "cpId"
            ) cp_latest ON cp."cpId" = cp_latest."cpId"
                       AND cp._sync_id = cp_latest.max_sync_id
            ON CONFLICT (cp_id) DO UPDATE SET
                cp_display_id            = EXCLUDED.cp_display_id,
                cp_type                  = EXCLUDED.cp_type,
                contact_number           = EXCLUDED.contact_number,
                email                    = EXCLUDED.email,
                type_of_agent            = EXCLUDED.type_of_agent,
                billing_name             = EXCLUDED.billing_name,
                gst_business_name        = EXCLUDED.gst_business_name,
                gst_legal_name           = EXCLUDED.gst_legal_name,
                proprietorship_name      = EXCLUDED.proprietorship_name,
                is_gst_applicable        = EXCLUDED.is_gst_applicable,
                approval_status          = EXCLUDED.approval_status,
                rejection_reason         = EXCLUDED.rejection_reason,
                is_disabled              = EXCLUDED.is_disabled,
                src_updated_ts           = EXCLUDED.src_updated_ts,
                dw_update_ts             = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_channel_partner", result.rowcount)

    # ------------------------------------------------------------------
    # dim_channel_partner_fos
    # ------------------------------------------------------------------
    def build_dim_channel_partner_fos(self):
        """
        Upsert silver.dim_channel_partner_fos from bronze.stg_vj_fos.
        Links each FOS to its parent channel_partner_skey.

        Source: bronze.stg_vj_fos (VJ Sales field officers)
        """
        query = text("""
            INSERT INTO silver.dim_channel_partner_fos (
                channel_partner_fos_skey, channel_partner_skey,
                fos_id, name, contact_number, email,
                approval_status, rejection_reason, fos_display_id,
                bank_account_holder_name, bank_account_number,
                bank_ifsc_code, bank_branch_name,
                is_disabled,
                src_created_ts, src_updated_ts,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                dcp.channel_partner_skey,
                (fos."fosId")::UUID,
                fos."name",
                fos."contactNumber",
                fos."email",
                fos."approvalStatus",
                fos."rejectionReason",
                fos."fosDisplayId",
                fos."bankAccountHolderName",
                fos."bankAccountNumber",
                fos."bankIfscCode",
                fos."bankBranchName",
                COALESCE((fos."isDisabled")::BOOLEAN, FALSE),
                (fos."createdAt")::TIMESTAMP,
                (fos."updatedAt")::TIMESTAMP,
                CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_fos fos
            -- Deduplicate: latest sync per fosId
            INNER JOIN (
                SELECT "fosId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_fos
                GROUP BY "fosId"
            ) fos_latest ON fos."fosId" = fos_latest."fosId"
                        AND fos._sync_id = fos_latest.max_sync_id
            -- Resolve parent channel partner
            LEFT JOIN silver.dim_channel_partner dcp
                ON dcp.cp_id = (fos."cpId")::UUID
            ON CONFLICT (fos_id) DO UPDATE SET
                channel_partner_skey     = EXCLUDED.channel_partner_skey,
                name                     = EXCLUDED.name,
                contact_number           = EXCLUDED.contact_number,
                email                    = EXCLUDED.email,
                approval_status          = EXCLUDED.approval_status,
                rejection_reason         = EXCLUDED.rejection_reason,
                fos_display_id           = EXCLUDED.fos_display_id,
                is_disabled              = EXCLUDED.is_disabled,
                src_updated_ts           = EXCLUDED.src_updated_ts,
                dw_update_ts             = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info(
                "Upserted %d rows into dim_channel_partner_fos", result.rowcount
            )

    # ------------------------------------------------------------------
    # dim_buyer
    # ------------------------------------------------------------------
    def build_dim_buyer(self):
        """
        Upsert silver.dim_buyer from bronze.stg_vj_person.

        Source: bronze.stg_vj_person (VJ Sales persons / buyers)
        """
        query = text("""
            INSERT INTO silver.dim_buyer (
                buyer_skey, buyer_id, name,
                contact_number, email, pan,
                gender, role, op_user_id, dob,
                dw_load_ts, dw_created_by
            )
            SELECT
                gen_random_uuid(),
                (per."personId")::UUID,
                per."name",
                COALESCE(per."phone", per."mobile"),
                per."email",
                per."panNumber",
                per."gender",
                per."role",
                per."opUserId",
                per."dob",
                CURRENT_TIMESTAMP,
                'etl_pipeline'
            FROM bronze.stg_vj_person per
            -- Deduplicate: latest sync per personId
            INNER JOIN (
                SELECT "personId", MAX(_sync_id) AS max_sync_id
                FROM bronze.stg_vj_person
                GROUP BY "personId"
            ) per_latest ON per."personId" = per_latest."personId"
                        AND per._sync_id = per_latest.max_sync_id
            ON CONFLICT (buyer_id) DO UPDATE SET
                name           = EXCLUDED.name,
                contact_number = EXCLUDED.contact_number,
                email          = EXCLUDED.email,
                pan            = EXCLUDED.pan,
                gender         = EXCLUDED.gender,
                role           = EXCLUDED.role,
                op_user_id     = EXCLUDED.op_user_id,
                dob            = EXCLUDED.dob,
                dw_update_ts   = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            result = conn.execute(query)
            logger.info("Upserted %d rows into dim_buyer", result.rowcount)
