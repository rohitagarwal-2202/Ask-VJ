"""
Fact Transformers — Build Silver + Gold fact tables from bronze data.

Silver facts (VJ Sales App leads & site visits):
  - silver.fact_lead       — one row per lead
  - silver.fact_site_visit — one row per site visit

Gold facts (Farvision ERP — no Silver equivalent yet):
  - gold.fact_bookings          — one row per booking
  - gold.fact_receipts          — one row per receipt
  - gold.fact_invoices          — one row per invoice
  - gold.snapshot_outstanding   — daily aging snapshot
  - gold.snapshot_inventory     — daily inventory snapshot
  - gold.snapshot_referrals     — daily referral snapshot

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
    """Builds and updates Silver + Gold fact tables."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def transform_all(self):
        """Run all fact transformations in dependency order."""
        # Silver facts (VJ Sales App)
        self.build_fact_lead()
        self.build_fact_site_visit()
        # Gold facts (Farvision — no Silver equivalent yet)
        self.build_fact_bookings()
        self.build_fact_receipts()
        self.build_fact_invoices()
        self.build_snapshot_outstanding()
        self.build_snapshot_inventory()
        self.build_snapshot_referrals()

    # ==================================================================
    # 1. fact_lead  (Silver — VJ Sales leads)
    # ==================================================================
    def build_fact_lead(self):
        """
        Build silver.fact_lead from bronze.stg_vj_leads.

        Dimension lookups (all against Silver dimensions):
          - buyer_skey:            stg_vj_leads.personId → dim_buyer.buyer_id
          - project_skey:          lead → site_visit → stg_vj_projects.buId → dim_project.bu_id
          - channel_partner_skey:  stg_vj_leads.cpId → dim_channel_partner.cp_id
          - lead_dt_skey:          epoch ms → YYYYMMDD → dim_calendar.calendar_skey
          - LOV lookups:           status/type/category/response → dim_lov(lov_type, lov_value)

        Timestamps are epoch MILLISECONDS → to_timestamp(x/1000).
        Upserts on lead_id (UNIQUE constraint required on silver.fact_lead.lead_id).
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO silver.fact_lead (
                    fact_lead_skey,
                    lead_id,
                    buyer_skey,
                    project_skey,
                    channel_partner_skey,
                    channel_partner_fos_skey,
                    lead_dt_skey,
                    project_head_employee_skey,
                    sales_manager_employee_skey,
                    claimed_by_employee_skey,
                    referred_by_employee_skey,
                    external_referrer_skey,
                    referred_by_buyer_skey,
                    lead_status_lov_skey,
                    lead_type_lov_skey,
                    lead_sub_type_lov_skey,
                    lead_category_lov_skey,
                    lead_response_lov_skey,
                    verification_status_lov_skey,
                    referrer_type_lov_skey,
                    lead_display_id,
                    display_dt,
                    src_created_dt,
                    src_created_ts,
                    src_updated_ts,
                    dw_load_ts,
                    dw_created_by
                )
                SELECT
                    gen_random_uuid(),
                    l."leadId",
                    db.buyer_skey,
                    dp.project_skey,
                    dcp.channel_partner_skey,
                    dfos.channel_partner_fos_skey,
                    TO_CHAR(to_timestamp(l.created_at / 1000), 'YYYYMMDD'),
                    ph.employee_skey,
                    sm.employee_skey,
                    cb.employee_skey,
                    ref_emp.employee_skey,
                    dxr.external_referrer_skey,
                    ref_buyer.buyer_skey,
                    lov_status.lov_skey,
                    lov_type.lov_skey,
                    lov_sub_type.lov_skey,
                    lov_category.lov_skey,
                    lov_response.lov_skey,
                    lov_verif.lov_skey,
                    lov_ref_type.lov_skey,
                    l."leadDisplayId",
                    (to_timestamp(l.created_at / 1000))::DATE,
                    (to_timestamp(l.created_at / 1000))::DATE,
                    to_timestamp(l.created_at / 1000),
                    to_timestamp(l.updated_at / 1000),
                    CURRENT_TIMESTAMP,
                    'etl_pipeline'
                FROM bronze.stg_vj_leads l
                -- latest sync per lead
                INNER JOIN (
                    SELECT "leadId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_vj_leads
                    GROUP BY "leadId"
                ) ld ON l."leadId" = ld."leadId" AND l._sync_id = ld.max_sync

                -- latest status per lead
                LEFT JOIN LATERAL (
                    SELECT ls2.status, ls2.category, ls2.response
                    FROM bronze.stg_vj_lead_status ls2
                    WHERE ls2."leadId" = l."leadId"
                    ORDER BY ls2._sync_id DESC
                    LIMIT 1
                ) ls ON TRUE

                -- buyer: personId → dim_buyer.buyer_id
                LEFT JOIN silver.dim_buyer db
                    ON db.buyer_id = l."personId"

                -- project: lead → latest site visit → stg_vj_projects.buId → dim_project.bu_id
                LEFT JOIN LATERAL (
                    SELECT sv2."projectId"
                    FROM bronze.stg_vj_site_visits sv2
                    WHERE sv2."leadId" = l."leadId"
                    ORDER BY sv2._sync_id DESC
                    LIMIT 1
                ) lsv ON TRUE
                LEFT JOIN bronze.stg_vj_projects vp
                    ON vp."projectId" = lsv."projectId"
                LEFT JOIN silver.dim_project dp
                    ON dp.bu_id = CAST(vp."buId" AS VARCHAR)

                -- channel partner: cpId → dim_channel_partner.cp_id
                LEFT JOIN silver.dim_channel_partner dcp
                    ON dcp.cp_id = l."cpId"

                -- channel partner FOS: fosId → dim_channel_partner_fos.fos_id
                LEFT JOIN silver.dim_channel_partner_fos dfos
                    ON dfos.fos_id = l."fosId"

                -- project head employee
                LEFT JOIN silver.dim_employee ph
                    ON ph.employee_id = l."projectHeadId"

                -- sales manager employee
                LEFT JOIN silver.dim_employee sm
                    ON sm.employee_id = l."salesManagerId"

                -- claimed by employee
                LEFT JOIN silver.dim_employee cb
                    ON cb.employee_id = l."claimedBy"

                -- referred by employee
                LEFT JOIN silver.dim_employee ref_emp
                    ON ref_emp.employee_id = l."referredByEmployeeId"

                -- external referrer
                LEFT JOIN silver.dim_external_referrer dxr
                    ON dxr.external_referrer_skey IS NOT NULL
                   AND dxr.referrer_name = l."externalReferrerName"

                -- referred by buyer
                LEFT JOIN silver.dim_buyer ref_buyer
                    ON ref_buyer.buyer_id = l."referredByBuyerId"

                -- LOV: lead status
                LEFT JOIN silver.dim_lov lov_status
                    ON lov_status.lov_type = 'LEAD_STATUS'
                   AND LOWER(lov_status.lov_value) = LOWER(ls.status)

                -- LOV: lead type
                LEFT JOIN silver.dim_lov lov_type
                    ON lov_type.lov_type = 'LEAD_TYPE'
                   AND LOWER(lov_type.lov_value) = LOWER(l."leadType")

                -- LOV: lead sub type
                LEFT JOIN silver.dim_lov lov_sub_type
                    ON lov_sub_type.lov_type = 'LEAD_SUB_TYPE'
                   AND LOWER(lov_sub_type.lov_value) = LOWER(l."leadSubType")

                -- LOV: lead category
                LEFT JOIN silver.dim_lov lov_category
                    ON lov_category.lov_type = 'LEAD_CATEGORY'
                   AND LOWER(lov_category.lov_value) = LOWER(ls.category)

                -- LOV: lead response
                LEFT JOIN silver.dim_lov lov_response
                    ON lov_response.lov_type = 'LEAD_RESPONSE'
                   AND LOWER(lov_response.lov_value) = LOWER(ls.response)

                -- LOV: verification status
                LEFT JOIN silver.dim_lov lov_verif
                    ON lov_verif.lov_type = 'VERIFICATION_STATUS'
                   AND LOWER(lov_verif.lov_value) = LOWER(l."verificationStatus")

                -- LOV: referrer type
                LEFT JOIN silver.dim_lov lov_ref_type
                    ON lov_ref_type.lov_type = 'REFERRER_TYPE'
                   AND LOWER(lov_ref_type.lov_value) = LOWER(l."referrerType")

                WHERE l.created_at IS NOT NULL

                ON CONFLICT (lead_id) DO UPDATE SET
                    buyer_skey                   = EXCLUDED.buyer_skey,
                    project_skey                 = EXCLUDED.project_skey,
                    channel_partner_skey         = EXCLUDED.channel_partner_skey,
                    channel_partner_fos_skey     = EXCLUDED.channel_partner_fos_skey,
                    lead_dt_skey                 = EXCLUDED.lead_dt_skey,
                    project_head_employee_skey   = EXCLUDED.project_head_employee_skey,
                    sales_manager_employee_skey  = EXCLUDED.sales_manager_employee_skey,
                    claimed_by_employee_skey     = EXCLUDED.claimed_by_employee_skey,
                    referred_by_employee_skey    = EXCLUDED.referred_by_employee_skey,
                    external_referrer_skey       = EXCLUDED.external_referrer_skey,
                    referred_by_buyer_skey       = EXCLUDED.referred_by_buyer_skey,
                    lead_status_lov_skey         = EXCLUDED.lead_status_lov_skey,
                    lead_type_lov_skey           = EXCLUDED.lead_type_lov_skey,
                    lead_sub_type_lov_skey       = EXCLUDED.lead_sub_type_lov_skey,
                    lead_category_lov_skey       = EXCLUDED.lead_category_lov_skey,
                    lead_response_lov_skey       = EXCLUDED.lead_response_lov_skey,
                    verification_status_lov_skey = EXCLUDED.verification_status_lov_skey,
                    referrer_type_lov_skey       = EXCLUDED.referrer_type_lov_skey,
                    lead_display_id              = EXCLUDED.lead_display_id,
                    display_dt                   = EXCLUDED.display_dt,
                    src_updated_ts               = EXCLUDED.src_updated_ts,
                    dw_update_ts                 = CURRENT_TIMESTAMP
            """)
            result = conn.execute(query)
            logger.info("fact_lead: upserted %d rows", result.rowcount)

    # ==================================================================
    # 2. fact_site_visit  (Silver — VJ Sales site visits)
    # ==================================================================
    def build_fact_site_visit(self):
        """
        Build silver.fact_site_visit from bronze.stg_vj_site_visits.

        Dimension lookups (all against Silver dimensions):
          - fact_lead_skey:        sv.leadId → fact_lead.lead_id
          - project_skey:          stg_vj_projects.buId → dim_project.bu_id
          - employee_skey:         sv.userId → dim_employee.employee_id
          - channel_partner_skey:  sv.cpId → dim_channel_partner.cp_id
          - site_visit_dt_skey:    epoch ms → YYYYMMDD string → dim_calendar.calendar_skey

        Timestamps are epoch MILLISECONDS → to_timestamp(x/1000).
        Upserts on site_visit_id.
        """
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO silver.fact_site_visit (
                    fact_site_visit_skey,
                    site_visit_id,
                    fact_lead_skey,
                    project_skey,
                    employee_skey,
                    channel_partner_skey,
                    channel_partner_fos_skey,
                    site_visit_dt_skey,
                    site_visit_ts,
                    photo_url,
                    remarks,
                    mode,
                    src_created_dt,
                    src_created_ts,
                    src_updated_ts,
                    dw_load_ts,
                    dw_created_by
                )
                SELECT
                    gen_random_uuid(),
                    sv."siteVisitId",
                    fl.fact_lead_skey,
                    dp.project_skey,
                    de.employee_skey,
                    dcp.channel_partner_skey,
                    dfos.channel_partner_fos_skey,
                    TO_CHAR(to_timestamp(sv.created_at / 1000), 'YYYYMMDD'),
                    to_timestamp(sv.created_at / 1000),
                    sv."photoUrl",
                    sv.remarks,
                    sv.mode,
                    (to_timestamp(sv.created_at / 1000))::DATE,
                    to_timestamp(sv.created_at / 1000),
                    to_timestamp(sv.updated_at / 1000),
                    CURRENT_TIMESTAMP,
                    'etl_pipeline'
                FROM bronze.stg_vj_site_visits sv
                -- latest sync per site visit
                INNER JOIN (
                    SELECT "siteVisitId", MAX(_sync_id) AS max_sync
                    FROM bronze.stg_vj_site_visits
                    GROUP BY "siteVisitId"
                ) svd ON sv."siteVisitId" = svd."siteVisitId"
                     AND sv._sync_id = svd.max_sync

                -- lead FK: leadId → silver.fact_lead.lead_id
                LEFT JOIN silver.fact_lead fl
                    ON fl.lead_id = sv."leadId"

                -- project: stg_vj_projects.buId → dim_project.bu_id
                LEFT JOIN bronze.stg_vj_projects vp
                    ON vp."projectId" = sv."projectId"
                LEFT JOIN silver.dim_project dp
                    ON dp.bu_id = CAST(vp."buId" AS VARCHAR)

                -- employee: userId → dim_employee.employee_id
                LEFT JOIN silver.dim_employee de
                    ON de.employee_id = sv."userId"

                -- channel partner: cpId → dim_channel_partner.cp_id
                LEFT JOIN silver.dim_channel_partner dcp
                    ON dcp.cp_id = sv."cpId"

                -- channel partner FOS: fosId → dim_channel_partner_fos.fos_id
                LEFT JOIN silver.dim_channel_partner_fos dfos
                    ON dfos.fos_id = sv."fosId"

                WHERE sv.created_at IS NOT NULL

                ON CONFLICT (site_visit_id) DO UPDATE SET
                    fact_lead_skey           = EXCLUDED.fact_lead_skey,
                    project_skey             = EXCLUDED.project_skey,
                    employee_skey            = EXCLUDED.employee_skey,
                    channel_partner_skey     = EXCLUDED.channel_partner_skey,
                    channel_partner_fos_skey = EXCLUDED.channel_partner_fos_skey,
                    site_visit_dt_skey       = EXCLUDED.site_visit_dt_skey,
                    site_visit_ts            = EXCLUDED.site_visit_ts,
                    photo_url                = EXCLUDED.photo_url,
                    remarks                  = EXCLUDED.remarks,
                    mode                     = EXCLUDED.mode,
                    src_updated_ts           = EXCLUDED.src_updated_ts,
                    dw_update_ts             = CURRENT_TIMESTAMP
            """)
            result = conn.execute(query)
            logger.info("fact_site_visit: upserted %d rows", result.rowcount)

    # ==================================================================
    # 3. fact_bookings  (Gold — Farvision DimBookingMaster)
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
    # 4. fact_receipts  (Gold — Farvision DimReceipt)
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
    # 5. fact_invoices  (Gold — Farvision DimInvoice)
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
    # 6. snapshot_outstanding  (Gold — Farvision FactDueDatewiseOutstanding)
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
    # 7. snapshot_inventory  (Gold — VJ Sales Inventory)
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
    # 8. snapshot_referrals  (Gold — VJOP leads + lead_allotments + points)
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
