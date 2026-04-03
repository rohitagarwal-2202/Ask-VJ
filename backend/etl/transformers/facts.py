"""
Fact Transformers — Build gold.fact_* tables from bronze + silver data.

Sources:
  - Farvision ERP (bronze.stg_fv_*)  — TenantId = 75
  - VJ Sales App  (bronze.stg_vj_*)  — epoch ms timestamps
  - VJOP R&L      (bronze.stg_rnl_*) — referral & loyalty
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# All Farvision queries filter on this tenant.
FARVISION_TENANT_ID = 75


class FactTransformer:
    """Builds and updates gold-layer fact tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def transform_all(self):
        """Run all fact transformations in dependency order."""
        self.build_fact_lead_pipeline()
        self.build_fact_bookings()
        self.build_fact_receipts()
        self.build_fact_invoices()
        self.build_snapshot_outstanding()
        self.build_snapshot_inventory()
        self.build_snapshot_referrals()

    # ==================================================================
    # 1. fact_lead_pipeline  (VJ Sales leads → pipeline events)
    # ==================================================================
    def build_fact_lead_pipeline(self):
        """
        Build gold.fact_lead_pipeline from VJ Sales leads, statuses,
        allotments, and site visits.

        - Lead status gives the latest pipeline_stage per lead.
        - Site visits are separate events.
        - Allotment payments carry booking/agreement values.
        - Timestamps are epoch MILLISECONDS → to_timestamp(x/1000).
        - Customer linkage via silver.entity_map (vjsales_lead_id).
        - Project linkage via stg_vj_projects."buId" → dim_projects.bu_id.
        """
        with self.engine.begin() as conn:
            inquiry_count = self._insert_inquiry_events(conn)
            visit_count = self._insert_site_visit_events(conn)
            allotment_count = self._insert_allotment_events(conn)
            logger.info(
                "fact_lead_pipeline: +%d inquiries, +%d visits, +%d allotments",
                inquiry_count, visit_count, allotment_count,
            )

    def _insert_inquiry_events(self, conn) -> int:
        """Insert inquiry-stage events for leads (latest status per lead)."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                vjsales_lead_id, customer_key, project_key,
                source_key, event_date_key,
                pipeline_stage, event_timestamp
            )
            SELECT
                l."leadId",
                dc.customer_key,
                dp.project_key,
                dls.source_key,
                TO_CHAR(to_timestamp(l.created_at / 1000), 'YYYYMMDD')::INT,
                COALESCE(ls.status, 'inquiry'),
                to_timestamp(l.created_at / 1000)
            FROM bronze.stg_vj_leads l
            -- latest sync per lead
            INNER JOIN (
                SELECT "leadId", MAX(_sync_id) AS max_sync
                FROM bronze.stg_vj_leads
                GROUP BY "leadId"
            ) ld ON l."leadId" = ld."leadId" AND l._sync_id = ld.max_sync
            -- latest status per lead
            LEFT JOIN LATERAL (
                SELECT ls2.status
                FROM bronze.stg_vj_lead_status ls2
                WHERE ls2."leadId" = l."leadId"
                ORDER BY ls2._sync_id DESC
                LIMIT 1
            ) ls ON TRUE
            -- customer via entity_map
            LEFT JOIN silver.entity_map em
                ON em.vjsales_lead_id = l."leadId"
            LEFT JOIN gold.dim_customers dc
                ON dc.unified_customer_id = em.unified_customer_id
            -- project via stg_vj_projects buId
            LEFT JOIN bronze.stg_vj_projects vp
                ON vp."projectId" = (
                    SELECT sv."projectId"
                    FROM bronze.stg_vj_site_visits sv
                    WHERE sv."leadId" = l."leadId"
                    ORDER BY sv._sync_id DESC
                    LIMIT 1
                )
            LEFT JOIN gold.dim_projects dp
                ON dp.bu_id = vp."buId"
            -- lead source
            LEFT JOIN gold.dim_lead_sources dls
                ON dls.source_name = l."leadType"
            WHERE l.created_at IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _insert_site_visit_events(self, conn) -> int:
        """Insert site_visit events from stg_vj_site_visits."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                vjsales_lead_id, customer_key, project_key,
                event_date_key, pipeline_stage,
                previous_stage, event_timestamp
            )
            SELECT
                sv."leadId",
                dc.customer_key,
                dp.project_key,
                TO_CHAR(to_timestamp(sv.created_at / 1000), 'YYYYMMDD')::INT,
                'site_visit',
                'inquiry',
                to_timestamp(sv.created_at / 1000)
            FROM bronze.stg_vj_site_visits sv
            -- latest sync per site visit
            INNER JOIN (
                SELECT "siteVisitId", MAX(_sync_id) AS max_sync
                FROM bronze.stg_vj_site_visits
                GROUP BY "siteVisitId"
            ) svd ON sv."siteVisitId" = svd."siteVisitId"
                 AND sv._sync_id = svd.max_sync
            -- customer via entity_map
            LEFT JOIN silver.entity_map em
                ON em.vjsales_lead_id = sv."leadId"
            LEFT JOIN gold.dim_customers dc
                ON dc.unified_customer_id = em.unified_customer_id
            -- project via stg_vj_projects buId
            LEFT JOIN bronze.stg_vj_projects vp
                ON vp."projectId" = sv."projectId"
            LEFT JOIN gold.dim_projects dp
                ON dp.bu_id = vp."buId"
            WHERE sv.created_at IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _insert_allotment_events(self, conn) -> int:
        """Insert booking/allotment events from stg_vj_allotment_payment."""
        query = text("""
            INSERT INTO gold.fact_lead_pipeline (
                vjsales_lead_id, vjsales_allotment_id,
                customer_key, project_key, unit_key,
                event_date_key, pipeline_stage, allotment_status,
                booking_amount, event_timestamp
            )
            SELECT
                ap."leadId",
                ap."allotmentPaymentId",
                dc.customer_key,
                dp.project_key,
                du.unit_key,
                TO_CHAR(to_timestamp(ap.created_at / 1000), 'YYYYMMDD')::INT,
                'booking',
                ap.status,
                ap."paidAmount",
                to_timestamp(ap.created_at / 1000)
            FROM bronze.stg_vj_allotment_payment ap
            -- latest sync per allotment
            INNER JOIN (
                SELECT "allotmentPaymentId", MAX(_sync_id) AS max_sync
                FROM bronze.stg_vj_allotment_payment
                GROUP BY "allotmentPaymentId"
            ) apd ON ap."allotmentPaymentId" = apd."allotmentPaymentId"
                 AND ap._sync_id = apd.max_sync
            -- customer via entity_map
            LEFT JOIN silver.entity_map em
                ON em.vjsales_lead_id = ap."leadId"
            LEFT JOIN gold.dim_customers dc
                ON dc.unified_customer_id = em.unified_customer_id
            -- unit via inventory → farvision unit id
            LEFT JOIN bronze.stg_vj_inventory inv
                ON inv."unitId" = ap."unitId"
            LEFT JOIN gold.dim_units du
                ON du.farvision_unit_id = inv."farvisionUnitId"
            -- project via stg_vj_projects buId (through inventory)
            LEFT JOIN bronze.stg_vj_projects vp
                ON vp."projectId" = inv."projectId"
            LEFT JOIN gold.dim_projects dp
                ON dp.bu_id = vp."buId"
            WHERE ap.created_at IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    # ==================================================================
    # 2. fact_bookings  (Farvision DimBookingMaster)
    # ==================================================================
    def build_fact_bookings(self):
        """
        Build gold.fact_bookings from stg_fv_dim_booking_master.

        Joins:
          - dim_customers via entity_map (farvision_booking_id)
          - dim_projects  via "BUId" → dim_projects.bu_id
          - dim_units     via "PrimaryUnitId" → dim_units.farvision_unit_id
          - dim_typologies via stg_fv_fact_unit_movement."TypologyId"
          - agreement/registration from stg_fv_dim_unit_agreement
        Filter: TenantId = 75
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.fact_bookings (
                    farvision_booking_id, booking_no, booking_date,
                    customer_key, project_key, unit_key,
                    sales_person_key, typology_key,
                    net_basic_price, discount_percentage,
                    is_cancelled, cancellation_date,
                    agreement_date, agreement_no,
                    registration_date, registration_no,
                    allotment_date, broker_id, fiscal_year_id
                )
                SELECT
                    bm."BookingId",
                    bm."BookingNo",
                    bm."BookingDate",
                    dc.customer_key,
                    dp.project_key,
                    du.unit_key,
                    dsp.sales_person_key,
                    dt.typology_key,
                    bm."NetBasicPrice",
                    bm."DiscountPercentage",
                    bm."IsCancelled",
                    bc."BookingCancellationDate",
                    COALESCE(ua."AgreementDate", bm."AgreementDate"),
                    COALESCE(ua."AgreementNo", bm."AgreementNo"),
                    COALESCE(ua."RegistrationDate", bm."RegistrationDate"),
                    COALESCE(ua."RegistrationNo", bm."RegistrationNo"),
                    bm."AllotmentDate",
                    sd."BrokerId",
                    bm."FiscalYearId"
                FROM bronze.stg_fv_dim_booking_master bm
                -- latest sync per booking
                INNER JOIN (
                    SELECT "BookingId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_fv_dim_booking_master
                    WHERE "TenantId" = :tenant_id
                    GROUP BY "BookingId"
                ) bmd ON bm."BookingId" = bmd."BookingId"
                     AND bm._sync_id = bmd.max_sync
                -- customer via entity_map
                LEFT JOIN silver.entity_map em
                    ON em.farvision_booking_id = bm."BookingId"
                LEFT JOIN gold.dim_customers dc
                    ON dc.unified_customer_id = em.unified_customer_id
                -- project
                LEFT JOIN gold.dim_projects dp
                    ON dp.bu_id = bm."BUId"
                -- unit
                LEFT JOIN gold.dim_units du
                    ON du.farvision_unit_id = bm."PrimaryUnitId"
                -- sales person
                LEFT JOIN gold.dim_sales_persons dsp
                    ON dsp.farvision_sales_person_id = bm."SalesPersonId"
                -- typology via unit movement
                LEFT JOIN LATERAL (
                    SELECT um."TypologyId"
                    FROM bronze.stg_fv_fact_unit_movement um
                    WHERE um."BookingId" = bm."BookingId"
                      AND um."TenantId" = :tenant_id
                    ORDER BY um._sync_id DESC
                    LIMIT 1
                ) umt ON TRUE
                LEFT JOIN gold.dim_typologies dt
                    ON dt.typology_id = umt."TypologyId"
                -- agreement / registration from unit agreement
                LEFT JOIN LATERAL (
                    SELECT ua2."AgreementDate", ua2."AgreementNo",
                           ua2."RegistrationDate", ua2."RegistrationNo"
                    FROM bronze.stg_fv_dim_unit_agreement ua2
                    WHERE ua2."BookingId" = bm."BookingId"
                    ORDER BY ua2._sync_id DESC
                    LIMIT 1
                ) ua ON TRUE
                -- cancellation date
                LEFT JOIN LATERAL (
                    SELECT bc2."BookingCancellationDate"
                    FROM bronze.stg_fv_dim_booking_cancellation bc2
                    WHERE bc2."BookingId" = bm."BookingId"
                    ORDER BY bc2._sync_id DESC
                    LIMIT 1
                ) bc ON TRUE
                -- broker from sales detail
                LEFT JOIN LATERAL (
                    SELECT sd2."BrokerId"
                    FROM bronze.stg_fv_fact_sales_detail_wise sd2
                    WHERE sd2."BookingId" = bm."BookingId"
                    ORDER BY sd2._sync_id DESC
                    LIMIT 1
                ) sd ON TRUE
                WHERE bm."TenantId" = :tenant_id
                ON CONFLICT (farvision_booking_id)
                DO UPDATE SET
                    booking_no         = EXCLUDED.booking_no,
                    booking_date       = EXCLUDED.booking_date,
                    customer_key       = EXCLUDED.customer_key,
                    project_key        = EXCLUDED.project_key,
                    unit_key           = EXCLUDED.unit_key,
                    sales_person_key   = EXCLUDED.sales_person_key,
                    typology_key       = EXCLUDED.typology_key,
                    net_basic_price    = EXCLUDED.net_basic_price,
                    discount_percentage = EXCLUDED.discount_percentage,
                    is_cancelled       = EXCLUDED.is_cancelled,
                    cancellation_date  = EXCLUDED.cancellation_date,
                    agreement_date     = EXCLUDED.agreement_date,
                    agreement_no       = EXCLUDED.agreement_no,
                    registration_date  = EXCLUDED.registration_date,
                    registration_no    = EXCLUDED.registration_no,
                    allotment_date     = EXCLUDED.allotment_date,
                    broker_id          = EXCLUDED.broker_id,
                    fiscal_year_id     = EXCLUDED.fiscal_year_id
            """)
            result = conn.execute(query, {"tenant_id": FARVISION_TENANT_ID})
            logger.info("fact_bookings: upserted %d rows", result.rowcount)

    # ==================================================================
    # 3. fact_receipts  (Farvision DimReceipt)
    # ==================================================================
    def build_fact_receipts(self):
        """
        Build gold.fact_receipts from stg_fv_dim_receipt.

        Links to fact_bookings via "BookingId" → fact_bookings.farvision_booking_id.
        Note: source column is "RecieptId" (typo preserved from Farvision).
        Filter: TenantId = 75
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.fact_receipts (
                    farvision_receipt_id,
                    booking_key, customer_key, project_key, unit_key,
                    date_key,
                    amount, payment_mode, instrument_no, document_no
                )
                SELECT
                    r."RecieptId",
                    fb.booking_key,
                    fb.customer_key,
                    fb.project_key,
                    fb.unit_key,
                    TO_CHAR(r."DocumentDate", 'YYYYMMDD')::INT,
                    r."AmountLCY",
                    r."PaymentMode",
                    r."InstrumentNo",
                    r."DocumentNo"
                FROM bronze.stg_fv_dim_receipt r
                -- latest sync per receipt
                INNER JOIN (
                    SELECT "RecieptId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_fv_dim_receipt
                    WHERE "TenantId" = :tenant_id
                    GROUP BY "RecieptId"
                ) rd ON r."RecieptId" = rd."RecieptId"
                     AND r._sync_id = rd.max_sync
                -- link to bookings fact
                LEFT JOIN gold.fact_bookings fb
                    ON fb.farvision_booking_id = r."BookingId"
                WHERE r."TenantId" = :tenant_id
                ON CONFLICT (farvision_receipt_id)
                DO UPDATE SET
                    booking_key   = EXCLUDED.booking_key,
                    customer_key  = EXCLUDED.customer_key,
                    project_key   = EXCLUDED.project_key,
                    unit_key      = EXCLUDED.unit_key,
                    date_key      = EXCLUDED.date_key,
                    amount        = EXCLUDED.amount,
                    payment_mode  = EXCLUDED.payment_mode,
                    instrument_no = EXCLUDED.instrument_no,
                    document_no   = EXCLUDED.document_no
            """)
            result = conn.execute(query, {"tenant_id": FARVISION_TENANT_ID})
            logger.info("fact_receipts: upserted %d rows", result.rowcount)

    # ==================================================================
    # 4. fact_invoices  (Farvision DimInvoice)
    # ==================================================================
    def build_fact_invoices(self):
        """
        Build gold.fact_invoices from stg_fv_dim_invoice.

        Links to fact_bookings via "BookingId".
        Filter: TenantId = 75
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.fact_invoices (
                    farvision_invoice_id,
                    booking_key, customer_key, project_key, unit_key,
                    date_key,
                    basic_amount, total_amount
                )
                SELECT
                    inv."InvoiceId",
                    fb.booking_key,
                    fb.customer_key,
                    fb.project_key,
                    fb.unit_key,
                    TO_CHAR(inv."DocumentDate", 'YYYYMMDD')::INT,
                    inv."BasicAmount",
                    inv."AmountLCY"
                FROM bronze.stg_fv_dim_invoice inv
                -- latest sync per invoice
                INNER JOIN (
                    SELECT "InvoiceId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_fv_dim_invoice
                    WHERE "TenantId" = :tenant_id
                    GROUP BY "InvoiceId"
                ) invd ON inv."InvoiceId" = invd."InvoiceId"
                      AND inv._sync_id = invd.max_sync
                -- link to bookings fact
                LEFT JOIN gold.fact_bookings fb
                    ON fb.farvision_booking_id = inv."BookingId"
                WHERE inv."TenantId" = :tenant_id
                ON CONFLICT (farvision_invoice_id)
                DO UPDATE SET
                    booking_key   = EXCLUDED.booking_key,
                    customer_key  = EXCLUDED.customer_key,
                    project_key   = EXCLUDED.project_key,
                    unit_key      = EXCLUDED.unit_key,
                    date_key      = EXCLUDED.date_key,
                    basic_amount  = EXCLUDED.basic_amount,
                    total_amount  = EXCLUDED.total_amount
            """)
            result = conn.execute(query, {"tenant_id": FARVISION_TENANT_ID})
            logger.info("fact_invoices: upserted %d rows", result.rowcount)

    # ==================================================================
    # 5. snapshot_outstanding  (Farvision FactDueDatewiseOutstanding)
    # ==================================================================
    def build_snapshot_outstanding(self):
        """
        Build gold.snapshot_outstanding from stg_fv_fact_duedate_outstanding.

        Denormalized: customer_name and unit_no kept for fast LLM queries.
        Links to dim_projects via "BuId" → dim_projects.bu_id.
        Filter: Tenantid = 75  (note lowercase 'id' in source).
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.snapshot_outstanding (
                    project_key,
                    customer_name, unit_no,
                    bill_amount, paid_amount, due_amount,
                    overdue_days,
                    day_amt_15, day_amt_30, day_amt_60,
                    day_amt_90, day_amt_120, day_amt_180,
                    day_amt_more_180,
                    document_date, due_date
                )
                SELECT
                    dp.project_key,
                    dos."CustomerName",
                    dos."UnitNo",
                    dos."Bill_Amount",
                    dos."Paid_Amount",
                    dos."Due_Amount",
                    dos."OverdueDays",
                    dos."DayAmt_15",
                    dos."DayAmt_30",
                    dos."DayAmt_60",
                    dos."DayAmt_90",
                    dos."DayAmt_120",
                    dos."DayAmt_180",
                    dos."DayAmt_More180",
                    dos."DocumentDate",
                    dos."DueDate"
                FROM bronze.stg_fv_fact_duedate_outstanding dos
                -- latest sync per (LedgerId, UnitNo, DueDate) — natural grain
                INNER JOIN (
                    SELECT "LedgerId", "UnitNo", "DueDate",
                           MAX(_sync_id) AS max_sync
                    FROM bronze.stg_fv_fact_duedate_outstanding
                    WHERE "TenantId" = :tenant_id
                    GROUP BY "LedgerId", "UnitNo", "DueDate"
                ) dosd ON dos."LedgerId" = dosd."LedgerId"
                      AND dos."UnitNo"   = dosd."UnitNo"
                      AND dos."DueDate"  = dosd."DueDate"
                      AND dos._sync_id   = dosd.max_sync
                -- project
                LEFT JOIN gold.dim_projects dp
                    ON dp.bu_id = dos."BuId"
                WHERE dos."TenantId" = :tenant_id
            """)
            # Outstanding is a full-refresh snapshot — delete today's partition and reload.
            conn.execute(text("DELETE FROM gold.snapshot_outstanding WHERE snapshot_date = CURRENT_DATE"))
            result = conn.execute(query, {"tenant_id": FARVISION_TENANT_ID})
            logger.info("snapshot_outstanding: loaded %d rows", result.rowcount)

    # ==================================================================
    # 6. snapshot_inventory  (VJ Sales Inventory)
    # ==================================================================
    def build_snapshot_inventory(self):
        """
        Build gold.snapshot_inventory from stg_vj_inventory.

        Links:
          - dim_projects via stg_vj_projects."buId" → dim_projects.bu_id
          - dim_units    via "farvisionUnitId" → dim_units.farvision_unit_id
          - inventory_status from stg_vj_inventory_status
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.snapshot_inventory (
                    project_key, unit_key, typology_key,
                    inventory_status,
                    total_cost, bsp,
                    saleable_area, chargeable_area,
                    display_unit_type
                )
                SELECT
                    dp.project_key,
                    du.unit_key,
                    du.typology_key,
                    ist.status,
                    inv."totalCost",
                    inv."BSP",
                    inv."saleableArea",
                    inv."chargeableArea",
                    inv."displayUnitType"
                FROM bronze.stg_vj_inventory inv
                -- latest sync per unit
                INNER JOIN (
                    SELECT "unitId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_vj_inventory
                    GROUP BY "unitId"
                ) invd ON inv."unitId" = invd."unitId"
                      AND inv._sync_id = invd.max_sync
                -- project via stg_vj_projects buId
                LEFT JOIN bronze.stg_vj_projects vp
                    ON vp."projectId" = inv."projectId"
                LEFT JOIN gold.dim_projects dp
                    ON dp.bu_id = vp."buId"
                -- unit
                LEFT JOIN gold.dim_units du
                    ON du.farvision_unit_id = inv."farvisionUnitId"
                -- inventory status lookup
                LEFT JOIN bronze.stg_vj_inventory_status ist
                    ON ist."inventoryStatusId" = inv."inventoryStatusId"
            """)
            # Inventory is a full-refresh snapshot — delete today's partition and reload.
            conn.execute(text("DELETE FROM gold.snapshot_inventory WHERE snapshot_date = CURRENT_DATE"))
            result = conn.execute(query)
            logger.info("snapshot_inventory: loaded %d rows", result.rowcount)

    # ==================================================================
    # 7. snapshot_referrals  (VJOP leads + lead_allotments + points)
    # ==================================================================
    def build_snapshot_referrals(self):
        """
        Build gold.snapshot_referrals from VJOP tables.

        - Referrer = customer who referred (stg_rnl_leads.referred_by
          → stg_rnl_customers → dim_customers via FV_LedgerID).
        - booking_id comes from stg_rnl_lead_allotments (NOT stg_rnl_leads).
        - Points aggregated from stg_rnl_points_history per customer
          (SUM credits vs debits).
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO gold.snapshot_referrals (
                    referrer_customer_key,
                    referred_lead_name, referred_mobile,
                    project_key,
                    referral_status, vjop_lead_id,
                    sales_app_lead_id, booking_id,
                    points_earned, points_redeemed
                )
                SELECT
                    dc.customer_key,
                    rl.name,
                    rl.mobile,
                    dp.project_key,
                    rl.status,
                    rl.id,
                    rl.sales_app_lead_id,
                    la.booking_id,
                    COALESCE(pts.earned, 0),
                    COALESCE(pts.redeemed, 0)
                FROM bronze.stg_rnl_leads rl
                -- latest sync per VJOP lead
                INNER JOIN (
                    SELECT id, MAX(_sync_id) AS max_sync
                    FROM bronze.stg_rnl_leads
                    GROUP BY id
                ) rld ON rl.id = rld.id AND rl._sync_id = rld.max_sync
                -- referrer customer: referred_by → stg_rnl_customers → dim_customers
                LEFT JOIN bronze.stg_rnl_customers rc
                    ON rc.id = rl.referred_by
                LEFT JOIN gold.dim_customers dc
                    ON dc.farvision_ledger_id = rc."FV_LedgerID"
                -- booking_id from lead_allotments (NOT from leads)
                LEFT JOIN LATERAL (
                    SELECT la2.booking_id, la2."farvisionBuId"
                    FROM bronze.stg_rnl_lead_allotments la2
                    WHERE la2.rnl_lead_id = rl.id
                    ORDER BY la2._sync_id DESC
                    LIMIT 1
                ) la ON TRUE
                -- project via lead_allotments farvisionBuId
                LEFT JOIN gold.dim_projects dp
                    ON dp.bu_id = la."farvisionBuId"
                -- points earned / redeemed per referrer customer
                LEFT JOIN LATERAL (
                    SELECT
                        SUM(CASE WHEN ph.type = 'credit' THEN ph.points ELSE 0 END) AS earned,
                        SUM(CASE WHEN ph.type = 'debit'  THEN ph.points ELSE 0 END) AS redeemed
                    FROM bronze.stg_rnl_points_history ph
                    WHERE ph.user_id = rl.referred_by
                ) pts ON TRUE
                WHERE rl.referred_by IS NOT NULL
            """)
            # Referrals are a full-refresh snapshot — delete today's partition and reload.
            conn.execute(text("DELETE FROM gold.snapshot_referrals WHERE snapshot_date = CURRENT_DATE"))
            result = conn.execute(query)
            logger.info("snapshot_referrals: loaded %d rows", result.rowcount)
