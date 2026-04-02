"""
VJ Sales App Extractor — Pulls CRM data from VJ Sales PostgreSQL/Supabase.

Source conventions:
  - Table names are PascalCase, double-quoted: "Projects", "Leads", etc.
  - Column names are camelCase, double-quoted: "projectId", "leadId", etc.
  - Timestamps (created_at, last_updated_at) are EPOCH MILLISECONDS (BIGINT).
  - IDs are UUIDs.
  - Some tables ("AllotmentPayment") contain JSONB columns.
"""

from backend.etl.extractors.base import BaseExtractor


class VJSalesExtractor(BaseExtractor):
    """Extracts CRM data from the VJ Sales App (PostgreSQL / Supabase)."""

    @property
    def source_name(self) -> str:
        return "vjsales"

    def get_extract_tasks(self) -> list[dict]:
        return [
            # ----------------------------------------------------------
            # 1. Projects
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_projects",
                "timestamp_column": "last_updated_at",
                "full_query": """
                    SELECT "projectId", "projectName", "buId",
                           "reraNumber", "isCompleted"
                    FROM "Projects"
                    ORDER BY "projectId"
                """,
                "source_query": """
                    SELECT "projectId", "projectName", "buId",
                           "reraNumber", "isCompleted"
                    FROM "Projects"
                    WHERE "last_updated_at" > :watermark
                    ORDER BY "last_updated_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 2. Wings
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_wings",
                "timestamp_column": "last_updated_at",
                "full_query": """
                    SELECT "wingId", "wingName", "projectId"
                    FROM "Wings"
                    ORDER BY "wingId"
                """,
                "source_query": """
                    SELECT "wingId", "wingName", "projectId"
                    FROM "Wings"
                    WHERE "last_updated_at" > :watermark
                    ORDER BY "last_updated_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 3. Inventory (joined with InventoryType + InventoryStatus)
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_inventory",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT i."unitId", i."projectId", i."wingId",
                           i."floorNo", i."unitNo",
                           i."saleableArea", i."chargeableArea",
                           i."inventoryStatusId", i."inventoryTypeId",
                           i."farvisionUnitId", i."farvisionStatus",
                           i."totalCost", i."BSP",
                           i."displayUnitType", i."soldDate",
                           i."created_at", i."leadId"
                    FROM "Inventory" i
                    ORDER BY i."created_at" ASC
                """,
                "source_query": """
                    SELECT i."unitId", i."projectId", i."wingId",
                           i."floorNo", i."unitNo",
                           i."saleableArea", i."chargeableArea",
                           i."inventoryStatusId", i."inventoryTypeId",
                           i."farvisionUnitId", i."farvisionStatus",
                           i."totalCost", i."BSP",
                           i."displayUnitType", i."soldDate",
                           i."created_at", i."leadId"
                    FROM "Inventory" i
                    WHERE i."created_at" > :watermark
                    ORDER BY i."created_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 3a. InventoryType (small lookup — always full load)
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_inventory_type",
                "timestamp_column": None,
                "full_query": """
                    SELECT "inventoryTypeId", "type"
                    FROM "InventoryType"
                    ORDER BY "inventoryTypeId"
                """,
                "source_query": """
                    SELECT "inventoryTypeId", "type"
                    FROM "InventoryType"
                    ORDER BY "inventoryTypeId"
                """,
            },
            # ----------------------------------------------------------
            # 3b. InventoryStatus (small lookup — always full load)
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_inventory_status",
                "timestamp_column": None,
                "full_query": """
                    SELECT "inventoryStatusId", "status"
                    FROM "InventoryStatus"
                    ORDER BY "inventoryStatusId"
                """,
                "source_query": """
                    SELECT "inventoryStatusId", "status"
                    FROM "InventoryStatus"
                    ORDER BY "inventoryStatusId"
                """,
            },
            # ----------------------------------------------------------
            # 4. Leads
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_leads",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT "leadId", "personId", "userId", "cpId",
                           "leadType", "leadCategory", "created_at"
                    FROM "Leads"
                    ORDER BY "created_at" ASC
                """,
                "source_query": """
                    SELECT "leadId", "personId", "userId", "cpId",
                           "leadType", "leadCategory", "created_at"
                    FROM "Leads"
                    WHERE "created_at" > :watermark
                    ORDER BY "created_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 5. Person
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_person",
                "timestamp_column": "last_updated_at",
                "full_query": """
                    SELECT "personId", "name", "contactNumber",
                           "email", "gender"
                    FROM "Person"
                    ORDER BY "personId"
                """,
                "source_query": """
                    SELECT "personId", "name", "contactNumber",
                           "email", "gender"
                    FROM "Person"
                    WHERE "last_updated_at" > :watermark
                    ORDER BY "last_updated_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 6. LeadStatus
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_lead_status",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT "leadStatusId", "leadId", "status", "created_at"
                    FROM "LeadStatus"
                    ORDER BY "created_at" ASC
                """,
                "source_query": """
                    SELECT "leadStatusId", "leadId", "status", "created_at"
                    FROM "LeadStatus"
                    WHERE "created_at" > :watermark
                    ORDER BY "created_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 7. SiteVisits
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_site_visits",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT "siteVisitId", "projectId", "leadId", "cpId",
                           "userId", "inventoryTypeId", "dateTime",
                           "remarks", "mode", "created_at"
                    FROM "SiteVisits"
                    ORDER BY "created_at" ASC
                """,
                "source_query": """
                    SELECT "siteVisitId", "projectId", "leadId", "cpId",
                           "userId", "inventoryTypeId", "dateTime",
                           "remarks", "mode", "created_at"
                    FROM "SiteVisits"
                    WHERE "created_at" > :watermark
                    ORDER BY "created_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 8. AllotmentPayment (has JSONB columns: bookingAmt, unitCost)
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_allotment_payment",
                "timestamp_column": "created_at",
                "full_query": """
                    SELECT "allotmentPaymentId", "unitId", "leadId",
                           "status", "paidAmount", "bookingId",
                           "applicationNo",
                           "bookingAmt"::text   AS "bookingAmt",
                           "unitCost"::text     AS "unitCost",
                           "agreementNo", "agreementDate",
                           "created_at"
                    FROM "AllotmentPayment"
                    ORDER BY "created_at" ASC
                """,
                "source_query": """
                    SELECT "allotmentPaymentId", "unitId", "leadId",
                           "status", "paidAmount", "bookingId",
                           "applicationNo",
                           "bookingAmt"::text   AS "bookingAmt",
                           "unitCost"::text     AS "unitCost",
                           "agreementNo", "agreementDate",
                           "created_at"
                    FROM "AllotmentPayment"
                    WHERE "created_at" > :watermark
                    ORDER BY "created_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 9. CP (Channel Partners)
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_cp",
                "timestamp_column": "last_updated_at",
                "full_query": """
                    SELECT "cpId", "name", "contactNumber",
                           "companyName", "cpType",
                           "approvalStatus", "reraNo"
                    FROM "CP"
                    ORDER BY "cpId"
                """,
                "source_query": """
                    SELECT "cpId", "name", "contactNumber",
                           "companyName", "cpType",
                           "approvalStatus", "reraNo"
                    FROM "CP"
                    WHERE "last_updated_at" > :watermark
                    ORDER BY "last_updated_at" ASC
                """,
            },
            # ----------------------------------------------------------
            # 10. Users
            # ----------------------------------------------------------
            {
                "staging_table": "bronze.stg_vj_users",
                "timestamp_column": "last_updated_at",
                "full_query": """
                    SELECT "userId", "name", "roleId",
                           "email", "contactNumber"
                    FROM "Users"
                    ORDER BY "userId"
                """,
                "source_query": """
                    SELECT "userId", "name", "roleId",
                           "email", "contactNumber"
                    FROM "Users"
                    WHERE "last_updated_at" > :watermark
                    ORDER BY "last_updated_at" ASC
                """,
            },
        ]
