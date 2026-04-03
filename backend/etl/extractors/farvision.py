"""
Farvision ERP Extractor — Pulls data from Farvision DWH (FARVISIONDWHT75, SQL Server).

Source database: FARVISIONDWHT75, TenantId = 75
Schemas: CRMG, ENGG, FIN, dbo
"""

from backend.etl.extractors.base import BaseExtractor

# All queries filter on TenantId = 75 (or WHERE clause equivalent).
# Column names are PascalCase per Farvision convention.
# Exception: FactUnitMovement uses lowercase 'buid'.
_TENANT_FILTER = "TenantId = 75"


class FarvisionExtractor(BaseExtractor):
    """Extracts data from the Farvision ERP Data Warehouse (MS SQL Server)."""

    @property
    def source_name(self) -> str:
        return "farvision"

    def get_extract_tasks(self) -> list[dict]:
        return [
            # ──────────────────────────────────────────────
            # 1. CRMG.DimBookingMaster
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_booking_master",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT BookingId, LedgerId, FiscalYearId, BUId,
                           BookingDate, BookingNo, ProjectHierarchyId,
                           PrimaryUnitId, CustomerName, NetBasicPrice,
                           AllotmentDate, AgreementDate, AgreementNo,
                           RegistrationDate, RegistrationNo, TenantId,
                           IsCancelled, SalesPersonId, SalesPersonName,
                           DiscountPercentage
                    FROM CRMG.DimBookingMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
                "source_query": f"""
                    SELECT BookingId, LedgerId, FiscalYearId, BUId,
                           BookingDate, BookingNo, ProjectHierarchyId,
                           PrimaryUnitId, CustomerName, NetBasicPrice,
                           AllotmentDate, AgreementDate, AgreementNo,
                           RegistrationDate, RegistrationNo, TenantId,
                           IsCancelled, SalesPersonId, SalesPersonName,
                           DiscountPercentage
                    FROM CRMG.DimBookingMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 2. CRMG.FactUnitMovement
            #    NOTE: 'buid' is lowercase in this table.
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_fact_unit_movement",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT ProjectHierarchyId, BUId, UnitId, UnitStatus,
                           BookDate, Area, Value, TypologyId, UnitCount,
                           TenantId, TotalBasic, TotalDiscount, BookingId,
                           CarpetArea
                    FROM CRMG.FactUnitMovement
                    WHERE {_TENANT_FILTER}
                    ORDER BY UnitId ASC
                """,
                "source_query": f"""
                    SELECT ProjectHierarchyId, BUId, UnitId, UnitStatus,
                           BookDate, Area, Value, TypologyId, UnitCount,
                           TenantId, TotalBasic, TotalDiscount, BookingId,
                           CarpetArea
                    FROM CRMG.FactUnitMovement
                    WHERE {_TENANT_FILTER}
                    ORDER BY UnitId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 3. CRMG.DimUnitMaster
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_unit_master",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT UnitId, UnitCode, BUId, TypologyId,
                           UnitTypeId, FloorId, TenantId
                    FROM CRMG.DimUnitMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY UnitId ASC
                """,
                "source_query": f"""
                    SELECT UnitId, UnitCode, BUId, TypologyId,
                           UnitTypeId, FloorId, TenantId
                    FROM CRMG.DimUnitMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY UnitId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 4. CRMG.DimTypologyMaster  (static — full refresh only)
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_typology_master",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT TypologyId, TypologyCode, Typology, TenantId
                    FROM CRMG.DimTypologyMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY TypologyId ASC
                """,
                "source_query": f"""
                    SELECT TypologyId, TypologyCode, Typology, TenantId
                    FROM CRMG.DimTypologyMaster
                    WHERE {_TENANT_FILTER}
                    ORDER BY TypologyId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 5. CRMG.DimProjectHierarchy
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_project_hierarchy",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT ProjectHierarchyId, ParentId, HierarchyName,
                           HierarchyLebel, TenantId, BUId,
                           Level1, Level2, Level3, Level4, Level5
                    FROM CRMG.DimProjectHierarchy
                    WHERE {_TENANT_FILTER}
                    ORDER BY ProjectHierarchyId ASC
                """,
                "source_query": f"""
                    SELECT ProjectHierarchyId, ParentId, HierarchyName,
                           HierarchyLebel, TenantId, BUId,
                           Level1, Level2, Level3, Level4, Level5
                    FROM CRMG.DimProjectHierarchy
                    WHERE {_TENANT_FILTER}
                    ORDER BY ProjectHierarchyId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 6. CRMG.DimReceipt
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_receipt",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT RecieptId, FiscalYearId, BUId, BookingId,
                           PaymentMode, InstrumentNo, LedgerId,
                           ParentLedgerId, AmountLCY, Amount, TenantId,
                           DocumentNo, DocumentDate
                    FROM CRMG.DimReceipt
                    WHERE {_TENANT_FILTER}
                    ORDER BY RecieptId ASC
                """,
                "source_query": f"""
                    SELECT RecieptId, FiscalYearId, BUId, BookingId,
                           PaymentMode, InstrumentNo, LedgerId,
                           ParentLedgerId, AmountLCY, Amount, TenantId,
                           DocumentNo, DocumentDate
                    FROM CRMG.DimReceipt
                    WHERE {_TENANT_FILTER}
                    ORDER BY RecieptId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 7. CRMG.DimInvoice
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_invoice",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT InvoiceId, FiscalYearId, BUId, BookingId,
                           CustomerId, UnitId, InvoiceType, AmountLCY,
                           BasicAmount, LedgerId, TenantId, DocumentDate
                    FROM CRMG.DimInvoice
                    WHERE {_TENANT_FILTER}
                    ORDER BY InvoiceId ASC
                """,
                "source_query": f"""
                    SELECT InvoiceId, FiscalYearId, BUId, BookingId,
                           CustomerId, UnitId, InvoiceType, AmountLCY,
                           BasicAmount, LedgerId, TenantId, DocumentDate
                    FROM CRMG.DimInvoice
                    WHERE {_TENANT_FILTER}
                    ORDER BY InvoiceId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 8. CRMG.FactOutStanding
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_fact_outstanding",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT BookingId, UnitId, TenantId, LedgerId,
                           ParentLedgerId, BILLAMOUNT, PAIDAMOUNT,
                           OUTSTANDING, ONACCOUNTAMOUNT, NetBasicPrice,
                           BUId, ProjectHierarchyId, Status
                    FROM CRMG.FactOutStanding
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
                "source_query": f"""
                    SELECT BookingId, UnitId, TenantId, LedgerId,
                           ParentLedgerId, BILLAMOUNT, PAIDAMOUNT,
                           OUTSTANDING, ONACCOUNTAMOUNT, NetBasicPrice,
                           BUId, ProjectHierarchyId, Status
                    FROM CRMG.FactOutStanding
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 9. CRMG.FactDueDatewiseOutstanding
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_fact_duedate_outstanding",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT TenantId, LedgerId, CustomerName, DocumentDate,
                           DueDate, OverdueDays, UnitNo,
                           Bill_Amount, Paid_Amount, Due_Amount, BillOs,
                           DayAmt_15, DayAmt_30, DayAmt_60, DayAmt_90,
                           DayAmt_120, DayAmt_180,
                           DayAmt_More180, BuId,
                           Level1, Level2, Level3, Level4
                    FROM CRMG.FactDueDatewiseOutstanding
                    WHERE {_TENANT_FILTER}
                    ORDER BY LedgerId ASC
                """,
                "source_query": f"""
                    SELECT TenantId, LedgerId, CustomerName, DocumentDate,
                           DueDate, OverdueDays, UnitNo,
                           Bill_Amount, Paid_Amount, Due_Amount, BillOs,
                           DayAmt_15, DayAmt_30, DayAmt_60, DayAmt_90,
                           DayAmt_120, DayAmt_180,
                           DayAmt_More180, BuId,
                           Level1, Level2, Level3, Level4
                    FROM CRMG.FactDueDatewiseOutstanding
                    WHERE {_TENANT_FILTER}
                    ORDER BY LedgerId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 10. CRMG.DimCustomerDetail
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_customer_detail",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT LedgerCustId, TenantId, CustomerId,
                           CustomerCode, Customer, FullName, PanNo,
                           BUId, MobileNo, EmailId
                    FROM CRMG.DimCustomerDetail
                    WHERE {_TENANT_FILTER}
                    ORDER BY LedgerCustId ASC
                """,
                "source_query": f"""
                    SELECT LedgerCustId, TenantId, CustomerId,
                           CustomerCode, Customer, FullName, PanNo,
                           BUId, MobileNo, EmailId
                    FROM CRMG.DimCustomerDetail
                    WHERE {_TENANT_FILTER}
                    ORDER BY LedgerCustId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 11. CRMG.DimBookingCancellation
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_booking_cancellation",
                "timestamp_column": None,
                "full_query": """
                    SELECT ID, BookingId, BookingCancellationNo,
                           BookingCancellationDate, CancellationCharge,
                           UnitNo, CustomerId
                    FROM CRMG.DimBookingCancellation
                    ORDER BY ID ASC
                """,
                "source_query": """
                    SELECT ID, BookingId, BookingCancellationNo,
                           BookingCancellationDate, CancellationCharge,
                           UnitNo, CustomerId
                    FROM CRMG.DimBookingCancellation
                    ORDER BY ID ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 12. CRMG.DimUnitAgreement
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_unit_agreement",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT Id, TenantId, BookingId, BookingNo, UnitId,
                           CustomerName, AgreementNo, AgreementDate,
                           RegistrationNo, RegistrationDate
                    FROM CRMG.DimUnitAgreement
                    WHERE {_TENANT_FILTER}
                    ORDER BY Id ASC
                """,
                "source_query": f"""
                    SELECT Id, TenantId, BookingId, BookingNo, UnitId,
                           CustomerName, AgreementNo, AgreementDate,
                           RegistrationNo, RegistrationDate
                    FROM CRMG.DimUnitAgreement
                    WHERE {_TENANT_FILTER}
                    ORDER BY Id ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 13. CRMG.FactSalesDetailWise
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_fact_sales_detail_wise",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT BookingId, BUId, LedgerId, BookingDate,
                           BookingNo, IsCancelled, Status,
                           CancelationDate, AgreementDate, AgreementNo,
                           RegistrationDate, RegistrationNo,
                           ProjectHierarchyId, PrimaryUnitId, UnitId,
                           TypologyId, Area1, Area2, Area3, Area4,
                           BrokerId
                    FROM CRMG.FactSalesDetailWise
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
                "source_query": f"""
                    SELECT BookingId, BUId, LedgerId, BookingDate,
                           BookingNo, IsCancelled, Status,
                           CancelationDate, AgreementDate, AgreementNo,
                           RegistrationDate, RegistrationNo,
                           ProjectHierarchyId, PrimaryUnitId, UnitId,
                           TypologyId, Area1, Area2, Area3, Area4,
                           BrokerId
                    FROM CRMG.FactSalesDetailWise
                    WHERE {_TENANT_FILTER}
                    ORDER BY BookingId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 14. ENGG.DimBusinessUnit
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_business_unit",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT BusinessUnitId, BusinessUnit,
                           BusinessUnitParentId, BusinessUnitType,
                           TenantId, SegmentId
                    FROM ENGG.DimBusinessUnit
                    WHERE {_TENANT_FILTER}
                    ORDER BY BusinessUnitId ASC
                """,
                "source_query": f"""
                    SELECT BusinessUnitId, BusinessUnit,
                           BusinessUnitParentId, BusinessUnitType,
                           TenantId, SegmentId
                    FROM ENGG.DimBusinessUnit
                    WHERE {_TENANT_FILTER}
                    ORDER BY BusinessUnitId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 15. FIN.DimFiscalYearPeriodMonthly
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_fiscal_year_period",
                "timestamp_column": None,
                "full_query": f"""
                    SELECT MonthPeriodId, TenantId, MonthDescription,
                           PeriodFrom, PeriodTo, Year, FiscalYearId
                    FROM FIN.DimFiscalYearPeriodMonthly
                    WHERE {_TENANT_FILTER}
                    ORDER BY MonthPeriodId ASC
                """,
                "source_query": f"""
                    SELECT MonthPeriodId, TenantId, MonthDescription,
                           PeriodFrom, PeriodTo, Year, FiscalYearId
                    FROM FIN.DimFiscalYearPeriodMonthly
                    WHERE {_TENANT_FILTER}
                    ORDER BY MonthPeriodId ASC
                """,
            },

            # ──────────────────────────────────────────────
            # 16. dbo.DimDate  (static — full refresh only)
            # ──────────────────────────────────────────────
            {
                "staging_table": "bronze.stg_fv_dim_date",
                "timestamp_column": None,
                "full_query": """
                    SELECT DateKey, Date, DayOfMonth, DayName,
                           Month, MonthName, Quarter, Year, FiscalYearId
                    FROM dbo.DimDate
                    ORDER BY DateKey ASC
                """,
                "source_query": """
                    SELECT DateKey, Date, DayOfMonth, DayName,
                           Month, MonthName, Quarter, Year, FiscalYearId
                    FROM dbo.DimDate
                    ORDER BY DateKey ASC
                """,
            },
        ]
