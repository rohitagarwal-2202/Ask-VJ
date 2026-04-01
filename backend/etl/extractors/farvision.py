"""
Farvision ERP Extractor — Pulls receipts and demand letters from Farvision MS SQL Server.
"""

from backend.etl.extractors.base import BaseExtractor


class FarvisionExtractor(BaseExtractor):
    """Extracts financial data from the Farvision ERP (MS SQL Server)."""

    @property
    def source_name(self) -> str:
        return "farvision"

    def get_extract_tasks(self) -> list[dict]:
        # NOTE: Table and column names below are placeholders.
        # These must be updated once the actual Farvision schema is mapped.
        return [
            {
                "staging_table": "bronze.stg_farvision_receipts",
                "timestamp_column": "updated_date",
                "full_query": """
                    SELECT receipt_id, customer_name, project_code, unit_no,
                           amount, receipt_date, payment_mode, cheque_no, bank_name,
                           narration, created_date, updated_date
                    FROM dbo.receipts
                    ORDER BY updated_date ASC
                """,
                "source_query": """
                    SELECT receipt_id, customer_name, project_code, unit_no,
                           amount, receipt_date, payment_mode, cheque_no, bank_name,
                           narration, created_date, updated_date
                    FROM dbo.receipts
                    WHERE updated_date > :watermark
                    ORDER BY updated_date ASC
                """,
            },
            {
                "staging_table": "bronze.stg_farvision_demands",
                "timestamp_column": "updated_date",
                "full_query": """
                    SELECT demand_id, customer_name, project_code, unit_no,
                           milestone, demand_amount, demand_date, due_date,
                           status, created_date, updated_date
                    FROM dbo.demand_letters
                    ORDER BY updated_date ASC
                """,
                "source_query": """
                    SELECT demand_id, customer_name, project_code, unit_no,
                           milestone, demand_amount, demand_date, due_date,
                           status, created_date, updated_date
                    FROM dbo.demand_letters
                    WHERE updated_date > :watermark
                    ORDER BY updated_date ASC
                """,
            },
        ]
