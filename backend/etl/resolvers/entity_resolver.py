"""
Entity Resolver — Links records across Farvision, VJ Sales, and VJOP
using shared IDs (BookingId, UnitId, BUId, LeadId).

Resolution strategy (priority order):
1. BookingId exact match (highest confidence — links Farvision ↔ VJ Sales ↔ VJOP)
2. UnitId exact match (links units across systems)
3. LeadId exact match (links VJ Sales leads ↔ VJOP referral leads)
4. Fuzzy fallback ONLY for unconverted leads (no shared ID yet)
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class EntityResolver:
    """Resolves customer/booking identities across source systems using shared IDs."""

    def __init__(self, warehouse_connection_string: str, fuzzy_threshold: float = 0.6):
        self.engine: Engine = create_engine(warehouse_connection_string)
        self.fuzzy_threshold = fuzzy_threshold

    def resolve(self) -> dict:
        """
        Run all matching strategies and update silver.entity_map.
        Returns stats: {booking_id_matched, unit_id_matched, lead_id_matched,
                        fuzzy_queued, already_resolved}.
        """
        stats = {
            "booking_id_matched": 0,
            "unit_id_matched": 0,
            "lead_id_matched": 0,
            "fuzzy_queued": 0,
        }

        with self.engine.begin() as conn:
            # Strategy 1: BookingId exact match (Farvision ↔ VJ Sales ↔ VJOP)
            matched = self._match_by_booking_id(conn)
            stats["booking_id_matched"] = matched
            logger.info("BookingId match: %d new matches", matched)

            # Strategy 2: UnitId exact match (Farvision ↔ VJ Sales inventory)
            matched = self._match_by_unit_id(conn)
            stats["unit_id_matched"] = matched
            logger.info("UnitId match: %d new matches", matched)

            # Strategy 3: LeadId exact match (VJ Sales ↔ VJOP)
            matched = self._match_by_lead_id(conn)
            stats["lead_id_matched"] = matched
            logger.info("LeadId match: %d new matches", matched)

            # Strategy 4: Queue unconverted leads for fuzzy fallback
            queued = self._queue_unresolved_leads(conn)
            stats["fuzzy_queued"] = queued
            logger.info("Fuzzy queue: %d leads queued for review", queued)

        return stats

    def _match_by_booking_id(self, conn) -> int:
        """
        Match records across all 3 systems using BookingId.

        Join path:
        - Farvision: stg_fv_dim_booking_master.BookingId
        - VJ Sales:  stg_vjsales_allotments.bookingId
        - VJOP:      stg_vjop_customer_units.fv_booking_id
        """
        query = text("""
            INSERT INTO silver.entity_map (
                farvision_booking_id, farvision_unit_id, farvision_bu_id, farvision_ledger_id,
                vjsales_lead_id, vjsales_allotment_id, vjsales_unit_id,
                vjop_customer_id,
                match_method, match_confidence
            )
            SELECT DISTINCT ON (fb."BookingId")
                fb."BookingId",
                fb."PrimaryUnitId",
                fb."BUId",
                fb."LedgerId",
                ap."leadId",
                ap."allotmentPaymentId",
                ap."unitId",
                cu.customer_id,
                'booking_id_exact',
                0.99
            FROM bronze.stg_fv_dim_booking_master fb
            -- Join to VJ Sales via BookingId
            LEFT JOIN bronze.stg_vjsales_allotments ap
                ON ap."bookingId" = fb."BookingId"
                AND ap._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjsales_allotments a2
                    WHERE a2."bookingId" = ap."bookingId"
                )
            -- Join to VJOP via BookingId
            LEFT JOIN bronze.stg_vjop_customer_units cu
                ON cu.fv_booking_id = fb."BookingId"
                AND cu._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjop_customer_units c2
                    WHERE c2.fv_booking_id = cu.fv_booking_id
                )
            WHERE fb."TenantId" = 75
              AND fb."IsCancelled" = 0
              -- Use latest sync record
              AND fb._sync_id = (
                  SELECT MAX(_sync_id) FROM bronze.stg_fv_dim_booking_master fb2
                  WHERE fb2."BookingId" = fb."BookingId"
              )
              -- Not already resolved
              AND fb."BookingId" NOT IN (
                  SELECT farvision_booking_id FROM silver.entity_map
                  WHERE farvision_booking_id IS NOT NULL
              )
            ON CONFLICT (farvision_booking_id) DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _match_by_unit_id(self, conn) -> int:
        """
        Match unresolved records via UnitId (Farvision UnitId ↔ VJ Sales farvisionUnitId).

        This catches records where the booking hasn't been created in Farvision yet
        but the unit is already linked.
        """
        query = text("""
            INSERT INTO silver.entity_map (
                farvision_unit_id, farvision_bu_id,
                vjsales_unit_id,
                match_method, match_confidence
            )
            SELECT DISTINCT ON (inv."farvisionUnitId")
                inv."farvisionUnitId",
                proj."buId",
                inv."unitId",
                'unit_id_exact',
                0.95
            FROM bronze.stg_vjsales_inventory inv
            JOIN bronze.stg_vjsales_projects proj
                ON inv."projectId" = proj."projectId"
            WHERE inv."farvisionUnitId" IS NOT NULL
              AND inv."farvisionUnitId" > 0
              -- Use latest sync record
              AND inv._sync_id = (
                  SELECT MAX(_sync_id) FROM bronze.stg_vjsales_inventory i2
                  WHERE i2."unitId" = inv."unitId"
              )
              -- Not already resolved by booking match
              AND inv."farvisionUnitId" NOT IN (
                  SELECT farvision_unit_id FROM silver.entity_map
                  WHERE farvision_unit_id IS NOT NULL
              )
            ON CONFLICT DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _match_by_lead_id(self, conn) -> int:
        """
        Match VJ Sales leads to VJOP referral leads via sales_app_lead_id.

        This links the pre-booking CRM pipeline to the referral system.
        """
        query = text("""
            INSERT INTO silver.entity_map (
                vjsales_lead_id,
                vjop_lead_id, vjop_customer_id,
                match_method, match_confidence
            )
            SELECT DISTINCT ON (vl.sales_app_lead_id)
                vl.sales_app_lead_id,
                vl.id,
                vl.user_id,
                'lead_id_exact',
                0.95
            FROM bronze.stg_vjop_leads vl
            WHERE vl.sales_app_lead_id IS NOT NULL
              -- Use latest sync record
              AND vl._sync_id = (
                  SELECT MAX(_sync_id) FROM bronze.stg_vjop_leads v2
                  WHERE v2.id = vl.id
              )
              -- Not already resolved
              AND vl.sales_app_lead_id NOT IN (
                  SELECT vjsales_lead_id FROM silver.entity_map
                  WHERE vjsales_lead_id IS NOT NULL
              )
            ON CONFLICT (vjsales_lead_id) DO NOTHING
        """)
        result = conn.execute(query)
        return result.rowcount

    def _queue_unresolved_leads(self, conn) -> int:
        """
        Queue unconverted VJ Sales leads (no BookingId/UnitId) for fuzzy review.

        These are leads that exist in VJ Sales but haven't progressed to a booking,
        so there's no shared ID to join on. They may still have a matching customer
        in Farvision or VJOP based on name/phone/email.
        """
        query = text("""
            INSERT INTO silver.entity_resolution_queue (
                vjsales_lead_id, vjsales_lead_name, vjsales_phone, vjsales_email,
                vjsales_project, match_method, reason, status
            )
            SELECT
                l."leadId",
                p.name,
                p."contactNumber",
                p.email,
                proj."projectName",
                'pending_fuzzy',
                'Pre-booking lead with no BookingId/UnitId for exact matching',
                'pending'
            FROM bronze.stg_vjsales_leads l
            JOIN bronze.stg_vjsales_persons p ON l."personId" = p."personId"
                AND p._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjsales_persons p2
                    WHERE p2."personId" = p."personId"
                )
            LEFT JOIN bronze.stg_vjsales_lead_status ls ON l."leadId" = ls."leadId"
                AND ls._sync_id = (
                    SELECT MAX(_sync_id) FROM bronze.stg_vjsales_lead_status ls2
                    WHERE ls2."leadId" = ls."leadId"
                )
            LEFT JOIN (
                SELECT DISTINCT ON ("leadId") "leadId", "unitId"
                FROM bronze.stg_vjsales_allotments
                ORDER BY "leadId", _sync_id DESC
            ) ap ON ap."leadId" = l."leadId"
            LEFT JOIN bronze.stg_vjsales_projects proj ON TRUE  -- simplified; real join would use ProjectPreference
            WHERE l._sync_id = (
                SELECT MAX(_sync_id) FROM bronze.stg_vjsales_leads l2
                WHERE l2."leadId" = l."leadId"
            )
            -- Only queue leads that have NO allotment (unconverted)
            AND ap."leadId" IS NULL
            -- Not already in entity_map
            AND l."leadId" NOT IN (
                SELECT vjsales_lead_id FROM silver.entity_map
                WHERE vjsales_lead_id IS NOT NULL
            )
            -- Not already in queue
            AND l."leadId" NOT IN (
                SELECT vjsales_lead_id FROM silver.entity_resolution_queue
                WHERE vjsales_lead_id IS NOT NULL
            )
            LIMIT 1000  -- Process in batches
        """)
        result = conn.execute(query)
        return result.rowcount
