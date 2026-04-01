"""
VJ Sales App Extractor — Pulls leads, site visits, and bookings from VJ Sales PostgreSQL.
"""

from backend.etl.extractors.base import BaseExtractor


class VJSalesExtractor(BaseExtractor):
    """Extracts CRM data from the VJ Sales App (PostgreSQL)."""

    @property
    def source_name(self) -> str:
        return "vjsales"

    def get_extract_tasks(self) -> list[dict]:
        return [
            {
                "staging_table": "bronze.stg_vjsales_leads",
                "timestamp_column": "updated_date",
                "full_query": """
                    SELECT lead_id, lead_name, phone, email, source, status,
                           assigned_to, project_interest, unit_interest, remarks,
                           created_date, updated_date
                    FROM leads
                    ORDER BY updated_date ASC
                """,
                "source_query": """
                    SELECT lead_id, lead_name, phone, email, source, status,
                           assigned_to, project_interest, unit_interest, remarks,
                           created_date, updated_date
                    FROM leads
                    WHERE updated_date > :watermark
                    ORDER BY updated_date ASC
                """,
            },
            {
                "staging_table": "bronze.stg_vjsales_site_visits",
                "timestamp_column": "updated_date",
                "full_query": """
                    SELECT visit_id, lead_id, visit_date, project_name,
                           accompanied_by, feedback, next_follow_up,
                           created_date, updated_date
                    FROM site_visits
                    ORDER BY updated_date ASC
                """,
                "source_query": """
                    SELECT visit_id, lead_id, visit_date, project_name,
                           accompanied_by, feedback, next_follow_up,
                           created_date, updated_date
                    FROM site_visits
                    WHERE updated_date > :watermark
                    ORDER BY updated_date ASC
                """,
            },
            {
                "staging_table": "bronze.stg_vjsales_bookings",
                "timestamp_column": "updated_date",
                "full_query": """
                    SELECT booking_id, lead_id, project_name, unit_no, wing, floor,
                           unit_type, carpet_area, agreement_value, booking_amount,
                           booking_date, status, cancellation_date, cancellation_reason,
                           sales_person, channel_partner,
                           created_date, updated_date
                    FROM bookings
                    ORDER BY updated_date ASC
                """,
                "source_query": """
                    SELECT booking_id, lead_id, project_name, unit_no, wing, floor,
                           unit_type, carpet_area, agreement_value, booking_amount,
                           booking_date, status, cancellation_date, cancellation_reason,
                           sales_person, channel_partner,
                           created_date, updated_date
                    FROM bookings
                    WHERE updated_date > :watermark
                    ORDER BY updated_date ASC
                """,
            },
        ]
