"""
VJOP Referral & Loyalty Extractor — Pulls customer, lead, points, and reward
data from the RefferalAndLoyalty MS SQL Server database.
"""

from backend.etl.extractors.base import BaseExtractor


class VJOPExtractor(BaseExtractor):
    """Extracts referral and loyalty data from the VJOP system (MS SQL Server)."""

    @property
    def source_name(self) -> str:
        return "rnl"

    def get_extract_tasks(self) -> list[dict]:
        return [
            # ----------------------------------------------------------
            # dbo.customers → bronze.stg_rnl_customers
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_customers",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, name, customer_id, mobile, email, PAN,
                           member_type, rm_id, FV_LedgerID, created_at
                    FROM dbo.customers
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, name, customer_id, mobile, email, PAN,
                           member_type, rm_id, FV_LedgerID, created_at
                    FROM dbo.customers
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
            # ----------------------------------------------------------
            # dbo.customer_bookings_units → bronze.stg_rnl_customer_bookings_units
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_customer_bookings_units",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, customer_id, fv_booking_id, unit_id,
                           fv_agreement_value, BUId, project, wing,
                           unit_type, unit_no, floor, area, PAN, created_at
                    FROM dbo.customer_bookings_units
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, customer_id, fv_booking_id, unit_id,
                           fv_agreement_value, BUId, project, wing,
                           unit_type, unit_no, floor, area, PAN, created_at
                    FROM dbo.customer_bookings_units
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
            # ----------------------------------------------------------
            # dbo.leads → bronze.stg_rnl_leads
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_leads",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, name, mobile, email, user_id, project_id,
                           status, sales_app_lead_id, booking_id,
                           referred_by, type, created_at
                    FROM dbo.leads
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, name, mobile, email, user_id, project_id,
                           status, sales_app_lead_id, booking_id,
                           referred_by, type, created_at
                    FROM dbo.leads
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
            # ----------------------------------------------------------
            # dbo.lead_allotments → bronze.stg_rnl_lead_allotments
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_lead_allotments",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, rnl_lead_id, sales_app_lead_id, booking_id,
                           unitNo, wingName, projectName, farvisionUnitId,
                           farvisionBuId, status, agreement_date, created_at
                    FROM dbo.lead_allotments
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, rnl_lead_id, sales_app_lead_id, booking_id,
                           unitNo, wingName, projectName, farvisionUnitId,
                           farvisionBuId, status, agreement_date, created_at
                    FROM dbo.lead_allotments
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
            # ----------------------------------------------------------
            # dbo.points_history → bronze.stg_rnl_points_history
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_points_history",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, user_id, points, type, reward_type,
                           transaction_type, status, created_at
                    FROM dbo.points_history
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, user_id, points, type, reward_type,
                           transaction_type, status, created_at
                    FROM dbo.points_history
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
            # ----------------------------------------------------------
            # dbo.reward_config → bronze.stg_rnl_reward_config
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_rnl_reward_config",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT id, project_id, reward_type, type,
                           reward_amount, created_at
                    FROM dbo.reward_config
                    ORDER BY created_at ASC
                """,
                "source_query": """
                    SELECT id, project_id, reward_type, type,
                           reward_amount, created_at
                    FROM dbo.reward_config
                    WHERE created_at > :watermark
                    ORDER BY created_at ASC
                """,
            },
        ]
