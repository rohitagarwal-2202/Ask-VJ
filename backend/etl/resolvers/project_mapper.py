"""
Project Mapper — Manages the project_crosswalk table that maps
BUId (Farvision BusinessUnitId) to project names across systems.

BUId is the universal project identifier shared across:
- Farvision ERP (ENGG.DimBusinessUnit.BusinessUnitId)
- VJ Sales App (Projects.buId)
- VJOP (customer_bookings_units.BUId)
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class ProjectMapper:
    """Maps project identifiers across VJ Sales, Farvision, and VJOP via BUId."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def seed_crosswalk(self, mappings: list[dict]):
        """
        Seed the project crosswalk with manual mappings.

        Args:
            mappings: List of dicts with keys:
                - canonical_name: The unified project name
                - farvision_bu_id: Farvision BusinessUnitId (INT)
                - phase_name: Phase within the project (optional)
                - vjsales_project_name: Name as it appears in VJ Sales
                - vjop_project_name: Name as it appears in VJOP (optional)
        """
        query = text("""
            INSERT INTO silver.project_crosswalk
                (canonical_name, farvision_bu_id, phase_name,
                 vjsales_project_name, vjop_project_name)
            VALUES
                (:canonical_name, :farvision_bu_id, :phase_name,
                 :vjsales_project_name, :vjop_project_name)
            ON CONFLICT (farvision_bu_id) DO UPDATE
                SET canonical_name = EXCLUDED.canonical_name,
                    vjsales_project_name = EXCLUDED.vjsales_project_name,
                    vjop_project_name = EXCLUDED.vjop_project_name,
                    phase_name = EXCLUDED.phase_name,
                    updated_at = NOW()
        """)
        with self.engine.begin() as conn:
            for mapping in mappings:
                conn.execute(query, mapping)

        logger.info("Seeded %d project crosswalk entries", len(mappings))

    def auto_discover_projects(self) -> dict:
        """
        Auto-discover new projects from bronze data and insert into crosswalk.
        Returns {discovered: int, already_mapped: int}.
        """
        stats = {"discovered": 0, "already_mapped": 0}

        with self.engine.begin() as conn:
            # Discover from Farvision DimBusinessUnit
            result = conn.execute(text("""
                INSERT INTO silver.project_crosswalk (canonical_name, farvision_bu_id)
                SELECT DISTINCT
                    bu."BusinessUnit",
                    bu."BusinessUnitId"
                FROM bronze.stg_fv_dim_business_unit bu
                WHERE bu."TenantId" = 75
                  AND bu._sync_id = (
                      SELECT MAX(_sync_id) FROM bronze.stg_fv_dim_business_unit bu2
                      WHERE bu2."BusinessUnitId" = bu."BusinessUnitId"
                  )
                  AND bu."BusinessUnitId" NOT IN (
                      SELECT farvision_bu_id FROM silver.project_crosswalk
                      WHERE farvision_bu_id IS NOT NULL
                  )
                ON CONFLICT (farvision_bu_id) DO NOTHING
            """))
            stats["discovered"] += result.rowcount

            # Match VJ Sales projects by buId
            result = conn.execute(text("""
                UPDATE silver.project_crosswalk pc
                SET vjsales_project_name = vp."projectName"
                FROM bronze.stg_vj_projects vp
                WHERE vp."buId" = pc.farvision_bu_id
                  AND pc.vjsales_project_name IS NULL
                  AND vp._sync_id = (
                      SELECT MAX(_sync_id) FROM bronze.stg_vj_projects vp2
                      WHERE vp2."projectId" = vp."projectId"
                  )
            """))
            stats["already_mapped"] += result.rowcount

            # Match VJOP projects by BUId
            result = conn.execute(text("""
                UPDATE silver.project_crosswalk pc
                SET vjop_project_name = DISTINCT_PROJ.project
                FROM (
                    SELECT DISTINCT ON ("BUId") "BUId", project
                    FROM bronze.stg_rnl_customer_bookings_units
                    WHERE "BUId" IS NOT NULL
                    ORDER BY "BUId", _sync_id DESC
                ) DISTINCT_PROJ
                WHERE DISTINCT_PROJ."BUId" = pc.farvision_bu_id
                  AND pc.vjop_project_name IS NULL
            """))

        logger.info("Project auto-discovery: %s", stats)
        return stats

    def detect_unmapped_projects(self) -> dict:
        """
        Find projects in bronze data that don't have crosswalk entries.
        Returns {vjsales_unmapped: [...], farvision_unmapped: [...], vjop_unmapped: [...]}.
        """
        unmapped = {
            "vjsales_unmapped": [],
            "farvision_unmapped": [],
            "vjop_unmapped": [],
        }

        with self.engine.connect() as conn:
            # VJ Sales projects with buId not in crosswalk
            vj_result = conn.execute(text("""
                SELECT DISTINCT vp."projectName", vp."buId"
                FROM bronze.stg_vj_projects vp
                WHERE vp."buId" IS NOT NULL
                  AND vp."buId" NOT IN (
                      SELECT farvision_bu_id FROM silver.project_crosswalk
                      WHERE farvision_bu_id IS NOT NULL
                  )
                  AND vp._sync_id = (
                      SELECT MAX(_sync_id) FROM bronze.stg_vj_projects vp2
                      WHERE vp2."projectId" = vp."projectId"
                  )
            """))
            unmapped["vjsales_unmapped"] = [
                {"name": row[0], "bu_id": row[1]} for row in vj_result
            ]

            # Farvision BusinessUnits not in crosswalk
            farv_result = conn.execute(text("""
                SELECT DISTINCT bu."BusinessUnit", bu."BusinessUnitId"
                FROM bronze.stg_fv_dim_business_unit bu
                WHERE bu."TenantId" = 75
                  AND bu."BusinessUnitId" NOT IN (
                      SELECT farvision_bu_id FROM silver.project_crosswalk
                      WHERE farvision_bu_id IS NOT NULL
                  )
                  AND bu._sync_id = (
                      SELECT MAX(_sync_id) FROM bronze.stg_fv_dim_business_unit bu2
                      WHERE bu2."BusinessUnitId" = bu."BusinessUnitId"
                  )
            """))
            unmapped["farvision_unmapped"] = [
                {"name": row[0], "bu_id": row[1]} for row in farv_result
            ]

            # VJOP projects not in crosswalk
            vjop_result = conn.execute(text("""
                SELECT DISTINCT project, "BUId"
                FROM bronze.stg_rnl_customer_bookings_units
                WHERE "BUId" IS NOT NULL
                  AND "BUId" NOT IN (
                      SELECT farvision_bu_id FROM silver.project_crosswalk
                      WHERE farvision_bu_id IS NOT NULL
                  )
            """))
            unmapped["vjop_unmapped"] = [
                {"name": row[0], "bu_id": row[1]} for row in vjop_result
            ]

        if any(unmapped.values()):
            logger.warning("Unmapped projects detected: %s", unmapped)

        return unmapped
