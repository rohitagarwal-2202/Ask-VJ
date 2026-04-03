-- ============================================================
-- ASK VJ: Bronze Layer Schema (Raw Staging)
-- ============================================================
-- 1:1 copies of source system tables. Append-only.
-- No transformations. Full audit trail with sync metadata.
--
-- Sources:
--   1. Farvision ERP DWH  (FARVISIONDWHT75, SQL Server, TenantId=75)
--   2. VJ Sales App        (PostgreSQL / Supabase)
--   3. VJOP Referral & Loyalty (SQL Server, db=RefferalAndLoyalty)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- ############################################################
--  SOURCE 1: FARVISION ERP DATA WAREHOUSE
--  Server: FARVISIONDWHT75 | TenantId = 75
-- ############################################################

-- ============================================================
-- CRMG.DimBookingMaster
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_booking_master (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "BookingId"              INT NOT NULL,
    "LedgerId"               INT,
    "FiscalYearId"           INT,
    "BUId"                   INT,
    "BookingDate"            DATE,
    "BookingNo"              VARCHAR(100),
    "ProjectHierarchyId"     INT,
    "PrimaryUnitId"          INT,
    "CustomerName"           VARCHAR(500),
    "NetBasicPrice"          DECIMAL(18, 2),
    "AllotmentDate"          DATE,
    "AgreementDate"          DATE,
    "AgreementNo"            VARCHAR(100),
    "RegistrationDate"       DATE,
    "RegistrationNo"         VARCHAR(100),
    "TenantId"               INT,
    "IsCancelled"            SMALLINT,        -- SQL Server BIT: 0=false, 1=true
    "SalesPersonId"          INT,
    "SalesPersonName"        VARCHAR(255),
    "DiscountPercentage"     DECIMAL(10, 4)
);

CREATE INDEX IF NOT EXISTS idx_fv_booking_master_booking_id
    ON bronze.stg_fv_dim_booking_master ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_booking_master_buid
    ON bronze.stg_fv_dim_booking_master ("BUId");
CREATE INDEX IF NOT EXISTS idx_fv_booking_master_ledger_id
    ON bronze.stg_fv_dim_booking_master ("LedgerId");
CREATE INDEX IF NOT EXISTS idx_fv_booking_master_synced
    ON bronze.stg_fv_dim_booking_master (_synced_at);

-- ============================================================
-- CRMG.FactUnitMovement
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_fact_unit_movement (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "ProjectHierarchyId" INT,
    "BUId"               INT,
    "UnitId"             INT,
    "UnitStatus"         INT,              -- 1=sold, 2=available, 3=blocked
    "BookDate"           DATE,
    "Area"               DECIMAL(12, 2),
    "Value"              DECIMAL(18, 2),
    "TypologyId"         INT,
    "UnitCount"          INT,
    "TenantId"           INT,
    "TotalBasic"         DECIMAL(18, 2),
    "TotalDiscount"      DECIMAL(18, 2),
    "BookingId"          INT,
    "CarpetArea"         DECIMAL(12, 2)
);

CREATE INDEX IF NOT EXISTS idx_fv_unit_movement_unit_id
    ON bronze.stg_fv_fact_unit_movement ("UnitId");
CREATE INDEX IF NOT EXISTS idx_fv_unit_movement_booking_id
    ON bronze.stg_fv_fact_unit_movement ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_unit_movement_buid
    ON bronze.stg_fv_fact_unit_movement ("BUId");

-- ============================================================
-- CRMG.DimUnitMaster
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_unit_master (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "UnitId"         INT NOT NULL,
    "UnitCode"       VARCHAR(100),
    "BUId"           INT,
    "TypologyId"     INT,
    "UnitTypeId"     INT,
    "FloorId"        INT,
    "TenantId"       INT
);

CREATE INDEX IF NOT EXISTS idx_fv_unit_master_unit_id
    ON bronze.stg_fv_dim_unit_master ("UnitId");
CREATE INDEX IF NOT EXISTS idx_fv_unit_master_buid
    ON bronze.stg_fv_dim_unit_master ("BUId");

-- ============================================================
-- CRMG.DimTypologyMaster
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_typology_master (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "TypologyId"     INT NOT NULL,
    "TypologyCode"   VARCHAR(50),
    "Typology"       VARCHAR(100),         -- e.g. 1BHK, 2BHK, 3BHK, 3BHK XL
    "TenantId"       INT
);

CREATE INDEX IF NOT EXISTS idx_fv_typology_master_typology_id
    ON bronze.stg_fv_dim_typology_master ("TypologyId");

-- ============================================================
-- CRMG.DimProjectHierarchy
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_project_hierarchy (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "ProjectHierarchyId" INT NOT NULL,
    "ParentId"           INT,
    "HierarchyName"      VARCHAR(255),
    "HierarchyLebel"     INT,             -- sic: source column spelling
    "TenantId"           INT,
    "BUId"               INT,
    "Level1"             VARCHAR(255),
    "Level2"             VARCHAR(255),
    "Level3"             VARCHAR(255),
    "Level4"             VARCHAR(255),
    "Level5"             VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_fv_project_hierarchy_id
    ON bronze.stg_fv_dim_project_hierarchy ("ProjectHierarchyId");
CREATE INDEX IF NOT EXISTS idx_fv_project_hierarchy_buid
    ON bronze.stg_fv_dim_project_hierarchy ("BUId");

-- ============================================================
-- CRMG.DimReceipt
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_receipt (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "RecieptId"      INT NOT NULL,         -- sic: source column spelling
    "FiscalYearId"   INT,
    "BUId"           INT,
    "BookingId"      INT,
    "PaymentMode"    VARCHAR(100),
    "InstrumentNo"   VARCHAR(100),
    "LedgerId"       INT,
    "ParentLedgerId" INT,
    "AmountLCY"      DECIMAL(18, 2),
    "Amount"         DECIMAL(18, 2),
    "TenantId"       INT,
    "DocumentNo"     VARCHAR(100),
    "DocumentDate"   DATE
);

CREATE INDEX IF NOT EXISTS idx_fv_receipt_booking_id
    ON bronze.stg_fv_dim_receipt ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_receipt_ledger_id
    ON bronze.stg_fv_dim_receipt ("LedgerId");
CREATE INDEX IF NOT EXISTS idx_fv_receipt_buid
    ON bronze.stg_fv_dim_receipt ("BUId");

-- ============================================================
-- CRMG.DimInvoice
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_invoice (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "InvoiceId"      INT NOT NULL,
    "FiscalYearId"   INT,
    "BUId"           INT,
    "BookingId"      INT,
    "CustomerId"     INT,
    "UnitId"         INT,
    "InvoiceType"    VARCHAR(100),
    "AmountLCY"      DECIMAL(18, 2),
    "BasicAmount"    DECIMAL(18, 2),
    "LedgerId"       INT,
    "TenantId"       INT,
    "DocumentDate"   DATE
);

CREATE INDEX IF NOT EXISTS idx_fv_invoice_booking_id
    ON bronze.stg_fv_dim_invoice ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_invoice_unit_id
    ON bronze.stg_fv_dim_invoice ("UnitId");
CREATE INDEX IF NOT EXISTS idx_fv_invoice_buid
    ON bronze.stg_fv_dim_invoice ("BUId");

-- ============================================================
-- CRMG.FactOutStanding
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_fact_outstanding (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "BookingId"          INT,
    "UnitId"             INT,
    "TenantId"           INT,
    "LedgerId"           INT,
    "ParentLedgerId"     INT,
    "BILLAMOUNT"         DECIMAL(18, 2),
    "PAIDAMOUNT"         DECIMAL(18, 2),
    "OUTSTANDING"        DECIMAL(18, 2),
    "ONACCOUNTAMOUNT"    DECIMAL(18, 2),
    "NetBasicPrice"      DECIMAL(18, 2),
    "BUId"               INT,
    "ProjectHierarchyId" INT,
    "Status"             VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_fv_outstanding_booking_id
    ON bronze.stg_fv_fact_outstanding ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_outstanding_ledger_id
    ON bronze.stg_fv_fact_outstanding ("LedgerId");
CREATE INDEX IF NOT EXISTS idx_fv_outstanding_buid
    ON bronze.stg_fv_fact_outstanding ("BUId");

-- ============================================================
-- CRMG.FactDueDatewiseOutstanding
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_fact_duedate_outstanding (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "TenantId"       INT,
    "LedgerId"       INT,
    "CustomerName"   VARCHAR(500),
    "DocumentDate"   DATE,
    "DueDate"        DATE,
    "OverdueDays"    INT,
    "UnitNo"         VARCHAR(100),
    "Bill_Amount"    DECIMAL(18, 2),
    "Paid_Amount"    DECIMAL(18, 2),
    "Due_Amount"     DECIMAL(18, 2),
    "BillOs"         DECIMAL(18, 2),
    "DayAmt_15"      DECIMAL(18, 2),
    "DayAmt_30"      DECIMAL(18, 2),
    "DayAmt_60"      DECIMAL(18, 2),
    "DayAmt_90"      DECIMAL(18, 2),
    "DayAmt_120"     DECIMAL(18, 2),
    "DayAmt_150"     DECIMAL(18, 2),
    "DayAmt_180"     DECIMAL(18, 2),
    "DayAmt_More180" DECIMAL(18, 2),
    "BuId"           INT,
    "Level1"         VARCHAR(255),
    "Level2"         VARCHAR(255),
    "Level3"         VARCHAR(255),
    "Level4"         VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_fv_duedate_os_ledger_id
    ON bronze.stg_fv_fact_duedate_outstanding ("LedgerId");
CREATE INDEX IF NOT EXISTS idx_fv_duedate_os_buid
    ON bronze.stg_fv_fact_duedate_outstanding ("BuId");

-- ============================================================
-- CRMG.DimCustomerDetail
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_customer_detail (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "LedgerCustId"   INT NOT NULL,
    "TenantId"       INT,
    "CustomerId"     INT,
    "CustomerCode"   VARCHAR(100),
    "Customer"       VARCHAR(500),
    "FullName"       VARCHAR(500),
    "PanNo"          VARCHAR(20),
    "BUId"           INT,
    "MobileNo"       VARCHAR(50),
    "EmailId"        VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_fv_customer_detail_ledger_cust_id
    ON bronze.stg_fv_dim_customer_detail ("LedgerCustId");
CREATE INDEX IF NOT EXISTS idx_fv_customer_detail_customer_id
    ON bronze.stg_fv_dim_customer_detail ("CustomerId");
CREATE INDEX IF NOT EXISTS idx_fv_customer_detail_buid
    ON bronze.stg_fv_dim_customer_detail ("BUId");

-- ============================================================
-- CRMG.DimBookingCancellation
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_booking_cancellation (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "ID"                       INT NOT NULL,
    "BookingId"                INT,
    "BookingCancellationNo"    VARCHAR(100),
    "BookingCancellationDate"  DATE,
    "CancellationCharge"       DECIMAL(18, 2),
    "UnitNo"                   VARCHAR(100),
    "CustomerId"               INT
);

CREATE INDEX IF NOT EXISTS idx_fv_booking_cancel_booking_id
    ON bronze.stg_fv_dim_booking_cancellation ("BookingId");

-- ============================================================
-- CRMG.DimUnitAgreement
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_unit_agreement (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "Id"               INT NOT NULL,
    "TenantId"         INT,
    "BookingId"        INT,
    "BookingNo"        VARCHAR(100),
    "UnitId"           INT,
    "CustomerName"     VARCHAR(500),
    "AgreementNo"      VARCHAR(100),
    "AgreementDate"    DATE,
    "RegistrationNo"   VARCHAR(100),
    "RegistrationDate" DATE
);

CREATE INDEX IF NOT EXISTS idx_fv_unit_agreement_booking_id
    ON bronze.stg_fv_dim_unit_agreement ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_unit_agreement_unit_id
    ON bronze.stg_fv_dim_unit_agreement ("UnitId");

-- ============================================================
-- CRMG.FactSalesDetailWise
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_fact_sales_detail_wise (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "BookingId"          INT,
    "BUId"               INT,
    "LedgerId"           INT,
    "BookingDate"        DATE,
    "BookingNo"          VARCHAR(100),
    "IsCancelled"        SMALLINT,
    "Status"             VARCHAR(100),
    "CancelationDate"    DATE,
    "AgreementDate"      DATE,
    "AgreementNo"        VARCHAR(100),
    "RegistrationDate"   DATE,
    "RegistrationNo"     VARCHAR(100),
    "ProjectHierarchyId" INT,
    "PrimaryUnitId"      INT,
    "UnitId"             INT,
    "TypologyId"         INT,
    "Area1"              DECIMAL(12, 2),
    "Area2"              DECIMAL(12, 2),
    "Area3"              DECIMAL(12, 2),
    "Area4"              DECIMAL(12, 2),
    "BrokerId"           INT
);

CREATE INDEX IF NOT EXISTS idx_fv_sales_detail_booking_id
    ON bronze.stg_fv_fact_sales_detail_wise ("BookingId");
CREATE INDEX IF NOT EXISTS idx_fv_sales_detail_buid
    ON bronze.stg_fv_fact_sales_detail_wise ("BUId");
CREATE INDEX IF NOT EXISTS idx_fv_sales_detail_ledger_id
    ON bronze.stg_fv_fact_sales_detail_wise ("LedgerId");
CREATE INDEX IF NOT EXISTS idx_fv_sales_detail_unit_id
    ON bronze.stg_fv_fact_sales_detail_wise ("UnitId");

-- ============================================================
-- ENGG.DimBusinessUnit  (Project Master — maps BUId)
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_business_unit (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "BusinessUnitId"       INT NOT NULL,
    "BusinessUnit"         VARCHAR(255),
    "BusinessUnitParentId" INT,
    "BusinessUnitType"     VARCHAR(100),
    "TenantId"             INT,
    "SegmentId"            INT
);

CREATE INDEX IF NOT EXISTS idx_fv_business_unit_id
    ON bronze.stg_fv_dim_business_unit ("BusinessUnitId");

-- ============================================================
-- FIN.DimFiscalYearPeriodMonthly
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_fiscal_year_period (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "MonthPeriodId"    INT NOT NULL,
    "TenantId"         INT,
    "MonthDescription" VARCHAR(100),
    "PeriodFrom"       DATE,
    "PeriodTo"         DATE,
    "Year"             INT,
    "FiscalYearId"     INT
);

CREATE INDEX IF NOT EXISTS idx_fv_fiscal_year_period_id
    ON bronze.stg_fv_dim_fiscal_year_period ("MonthPeriodId");
CREATE INDEX IF NOT EXISTS idx_fv_fiscal_year_fy_id
    ON bronze.stg_fv_dim_fiscal_year_period ("FiscalYearId");

-- ============================================================
-- dbo.DimDate
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_fv_dim_date (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id      UUID,

    "DateKey"        INT NOT NULL,
    "Date"           DATE,
    "DayOfMonth"     INT,
    "DayName"        VARCHAR(20),
    "Month"          INT,
    "MonthName"      VARCHAR(20),
    "Quarter"        INT,
    "Year"           INT,
    "FiscalYearId"   INT
);

CREATE INDEX IF NOT EXISTS idx_fv_dim_date_key
    ON bronze.stg_fv_dim_date ("DateKey");


-- ############################################################
--  SOURCE 2: VJ SALES APP
--  PostgreSQL / Supabase
--  Note: timestamps arrive as epoch MILLISECONDS; stored as
--        BIGINT in bronze and converted in silver layer.
-- ############################################################

-- ============================================================
-- "Projects"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_projects (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    projectId      UUID NOT NULL,
    projectName    VARCHAR(255),
    buId           INT,                  -- maps to Farvision BUId
    reraNumber     VARCHAR(100),
    isCompleted    BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_vj_projects_project_id
    ON bronze.stg_vj_projects (projectId);
CREATE INDEX IF NOT EXISTS idx_vj_projects_bu_id
    ON bronze.stg_vj_projects (buId);

-- ============================================================
-- "Wings"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_wings (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    wingId         UUID NOT NULL,
    wingName       VARCHAR(255),
    projectId      UUID
);

CREATE INDEX IF NOT EXISTS idx_vj_wings_wing_id
    ON bronze.stg_vj_wings (wingId);
CREATE INDEX IF NOT EXISTS idx_vj_wings_project_id
    ON bronze.stg_vj_wings (projectId);

-- ============================================================
-- "Inventory"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_inventory (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    unitId            UUID NOT NULL,
    projectId         UUID,
    wingId            UUID,
    floorNo           INT,
    unitNo            VARCHAR(50),
    saleableArea      DECIMAL(12, 2),
    chargeableArea    DECIMAL(12, 2),
    inventoryStatusId INT,
    inventoryTypeId   INT,
    farvisionUnitId   INT,               -- cross-system join key
    farvisionStatus   VARCHAR(50),
    totalCost         DECIMAL(18, 2),
    BSP               DECIMAL(18, 2),
    displayUnitType   VARCHAR(50),
    soldDate          BIGINT,            -- epoch ms
    created_at        BIGINT,            -- epoch ms
    leadId            UUID
);

CREATE INDEX IF NOT EXISTS idx_vj_inventory_unit_id
    ON bronze.stg_vj_inventory (unitId);
CREATE INDEX IF NOT EXISTS idx_vj_inventory_project_id
    ON bronze.stg_vj_inventory (projectId);
CREATE INDEX IF NOT EXISTS idx_vj_inventory_fv_unit_id
    ON bronze.stg_vj_inventory (farvisionUnitId);
CREATE INDEX IF NOT EXISTS idx_vj_inventory_lead_id
    ON bronze.stg_vj_inventory (leadId);

-- ============================================================
-- "InventoryType"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_inventory_type (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    inventoryTypeId INT NOT NULL,
    type            VARCHAR(100)
);

-- ============================================================
-- "InventoryStatus"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_inventory_status (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    inventoryStatusId INT NOT NULL,
    status            VARCHAR(50)         -- Available / On Hold / Sold
);

-- ============================================================
-- "Leads"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_leads (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    leadId         UUID NOT NULL,
    personId       UUID,
    userId         UUID,
    cpId           UUID,
    leadType       VARCHAR(100),
    leadCategory   VARCHAR(100),
    created_at     BIGINT               -- epoch ms
);

CREATE INDEX IF NOT EXISTS idx_vj_leads_lead_id
    ON bronze.stg_vj_leads (leadId);
CREATE INDEX IF NOT EXISTS idx_vj_leads_person_id
    ON bronze.stg_vj_leads (personId);
CREATE INDEX IF NOT EXISTS idx_vj_leads_cp_id
    ON bronze.stg_vj_leads (cpId);

-- ============================================================
-- "Person"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_person (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    personId       UUID NOT NULL,
    name           VARCHAR(255),
    contactNumber  VARCHAR(50),
    email          VARCHAR(255),
    gender         VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_vj_person_person_id
    ON bronze.stg_vj_person (personId);

-- ============================================================
-- "LeadStatus"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_lead_status (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    leadStatusId   INT NOT NULL,
    leadId         UUID,
    status         VARCHAR(100),
    created_at     BIGINT               -- epoch ms
);

CREATE INDEX IF NOT EXISTS idx_vj_lead_status_lead_id
    ON bronze.stg_vj_lead_status (leadId);

-- ============================================================
-- "SiteVisits"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_site_visits (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    siteVisitId    INT NOT NULL,
    projectId      UUID,
    leadId         UUID,
    cpId           UUID,
    userId         UUID,
    inventoryTypeId INT,
    dateTime       BIGINT,              -- epoch ms
    remarks        TEXT,
    mode           VARCHAR(100),
    created_at     BIGINT               -- epoch ms
);

CREATE INDEX IF NOT EXISTS idx_vj_site_visits_lead_id
    ON bronze.stg_vj_site_visits (leadId);
CREATE INDEX IF NOT EXISTS idx_vj_site_visits_project_id
    ON bronze.stg_vj_site_visits (projectId);

-- ============================================================
-- "AllotmentPayment"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_allotment_payment (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    allotmentPaymentId UUID NOT NULL,
    unitId             UUID,
    leadId             UUID,
    status             VARCHAR(100),
    paidAmount         DECIMAL(18, 2),
    bookingId          INT,              -- maps to Farvision BookingId
    applicationNo      VARCHAR(100),
    bookingAmt         JSONB,            -- preserved as JSONB from source
    unitCost           JSONB,            -- preserved as JSONB from source
    agreementNo        VARCHAR(100),
    agreementDate      DATE,
    created_at         BIGINT            -- epoch ms
);

CREATE INDEX IF NOT EXISTS idx_vj_allotment_pmt_id
    ON bronze.stg_vj_allotment_payment (allotmentPaymentId);
CREATE INDEX IF NOT EXISTS idx_vj_allotment_pmt_lead_id
    ON bronze.stg_vj_allotment_payment (leadId);
CREATE INDEX IF NOT EXISTS idx_vj_allotment_pmt_unit_id
    ON bronze.stg_vj_allotment_payment (unitId);
CREATE INDEX IF NOT EXISTS idx_vj_allotment_pmt_booking_id
    ON bronze.stg_vj_allotment_payment (bookingId);

-- ============================================================
-- "AllotmentTransactions"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_allotment_transactions (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    transactionId       INT NOT NULL,
    allotmentPaymentId  UUID,
    amount              DECIMAL(18, 2),
    modeOfPayment       VARCHAR(100),
    status              VARCHAR(100),
    unitId              UUID,
    leadId              UUID,
    created_at          BIGINT           -- epoch ms
);

CREATE INDEX IF NOT EXISTS idx_vj_allotment_txn_allotment_id
    ON bronze.stg_vj_allotment_transactions (allotmentPaymentId);
CREATE INDEX IF NOT EXISTS idx_vj_allotment_txn_lead_id
    ON bronze.stg_vj_allotment_transactions (leadId);

-- ============================================================
-- "CP" (Channel Partners)
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_cp (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    cpId           UUID NOT NULL,
    name           VARCHAR(255),
    contactNumber  VARCHAR(50),
    companyName    VARCHAR(255),
    cpType         VARCHAR(100),
    approvalStatus VARCHAR(50),
    reraNo         VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_vj_cp_cp_id
    ON bronze.stg_vj_cp (cpId);

-- ============================================================
-- "Users"
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vj_users (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id      UUID,

    userId         UUID NOT NULL,
    name           VARCHAR(255),
    roleId         INT,
    email          VARCHAR(255),
    contactNumber  VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_vj_users_user_id
    ON bronze.stg_vj_users (userId);


-- ############################################################
--  SOURCE 3: VJOP REFERRAL & LOYALTY
--  SQL Server, db = RefferalAndLoyalty
-- ############################################################

-- ============================================================
-- dbo.customers
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_customers (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id             INT NOT NULL,
    name           VARCHAR(255),
    customer_id    VARCHAR(100),
    mobile         VARCHAR(50),
    email          VARCHAR(255),
    "PAN"            VARCHAR(20),
    member_type    VARCHAR(100),
    rm_id          INT,
    "FV_LedgerID"    INT                  -- cross-system join to Farvision LedgerId
);

CREATE INDEX IF NOT EXISTS idx_rnl_customers_id
    ON bronze.stg_rnl_customers (id);
CREATE INDEX IF NOT EXISTS idx_rnl_customers_fv_ledger_id
    ON bronze.stg_rnl_customers ("FV_LedgerID");

-- ============================================================
-- dbo.customer_bookings_units
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_customer_bookings_units (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id                  INT NOT NULL,
    customer_id         INT,
    fv_booking_id       INT,             -- cross-system join to Farvision BookingId
    unit_id             INT,
    fv_agreement_value  DECIMAL(18, 2),
    "BUId"                INT,             -- cross-system join to Farvision BUId
    project             VARCHAR(255),
    wing                VARCHAR(100),
    unit_type           VARCHAR(50),
    unit_no             VARCHAR(50),
    floor               VARCHAR(50),
    area                DECIMAL(12, 2),
    "PAN"                 VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_rnl_cbu_customer_id
    ON bronze.stg_rnl_customer_bookings_units (customer_id);
CREATE INDEX IF NOT EXISTS idx_rnl_cbu_fv_booking_id
    ON bronze.stg_rnl_customer_bookings_units (fv_booking_id);
CREATE INDEX IF NOT EXISTS idx_rnl_cbu_buid
    ON bronze.stg_rnl_customer_bookings_units ("BUId");

-- ============================================================
-- dbo.leads
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_leads (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id                 INT NOT NULL,
    name               VARCHAR(255),
    mobile             VARCHAR(50),
    email              VARCHAR(255),
    user_id            INT,
    project_id         INT,
    status             VARCHAR(100),
    sales_app_lead_id  UUID,             -- cross-system join to VJ Sales leadId
    booking_id         INT,
    referred_by        INT,
    type               VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_rnl_leads_id
    ON bronze.stg_rnl_leads (id);
CREATE INDEX IF NOT EXISTS idx_rnl_leads_sales_app_lead_id
    ON bronze.stg_rnl_leads (sales_app_lead_id);
CREATE INDEX IF NOT EXISTS idx_rnl_leads_booking_id
    ON bronze.stg_rnl_leads (booking_id);

-- ============================================================
-- dbo.lead_allotments
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_lead_allotments (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id                 INT NOT NULL,
    rnl_lead_id        INT,
    sales_app_lead_id  UUID,             -- cross-system join to VJ Sales leadId
    booking_id         INT,
    "unitNo"             VARCHAR(50),
    "wingName"           VARCHAR(100),
    "projectName"        VARCHAR(255),
    "farvisionUnitId"    INT,              -- cross-system join to Farvision UnitId
    "farvisionBuId"      INT,              -- cross-system join to Farvision BUId
    status             VARCHAR(100),
    agreement_date     DATE
);

CREATE INDEX IF NOT EXISTS idx_rnl_lead_allotments_id
    ON bronze.stg_rnl_lead_allotments (id);
CREATE INDEX IF NOT EXISTS idx_rnl_lead_allotments_sales_lead
    ON bronze.stg_rnl_lead_allotments (sales_app_lead_id);
CREATE INDEX IF NOT EXISTS idx_rnl_lead_allotments_fv_unit
    ON bronze.stg_rnl_lead_allotments ("farvisionUnitId");

-- ============================================================
-- dbo.points_history
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_points_history (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id                 INT NOT NULL,
    user_id            INT,
    points             DECIMAL(12, 2),
    type               VARCHAR(50),      -- credit / debit
    reward_type        VARCHAR(100),
    transaction_type   VARCHAR(100),
    status             VARCHAR(50),
    created_at         TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rnl_points_history_user_id
    ON bronze.stg_rnl_points_history (user_id);

-- ============================================================
-- dbo.reward_config
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_reward_config (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id             INT NOT NULL,
    project_id     INT,
    reward_type    VARCHAR(100),
    type           VARCHAR(100),
    reward_amount  DECIMAL(18, 2)
);

-- ============================================================
-- dbo.transactions
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_rnl_transactions (
    _sync_id       BIGSERIAL PRIMARY KEY,
    _synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'rnl',
    _batch_id      UUID,

    id                 INT NOT NULL,
    user_id            INT,
    transaction_type   VARCHAR(100),
    amount             DECIMAL(18, 2),
    status             VARCHAR(50),
    "UTR"                VARCHAR(100),
    transaction_date   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rnl_transactions_user_id
    ON bronze.stg_rnl_transactions (user_id);


-- ############################################################
--  SYNC METADATA — Tracks ETL run history
-- ############################################################
CREATE TABLE IF NOT EXISTS bronze.sync_log (
    sync_id              SERIAL PRIMARY KEY,
    batch_id             UUID NOT NULL,
    source_system        VARCHAR(50) NOT NULL,
    table_name           VARCHAR(100) NOT NULL,
    started_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at         TIMESTAMP WITH TIME ZONE,
    records_extracted    INT DEFAULT 0,
    last_source_timestamp TIMESTAMP,     -- watermark for incremental pulls
    status               VARCHAR(20) DEFAULT 'running',  -- running, success, failed
    error_message        TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_log_source
    ON bronze.sync_log (source_system, table_name);
CREATE INDEX IF NOT EXISTS idx_sync_log_batch
    ON bronze.sync_log (batch_id);
