"""
Project Mapper — Manages the project_crosswalk table that maps project names across systems.

Initially seeded manually, later can auto-detect new projects from bronze data.
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class ProjectMapper:
    """Maps project identifiers across VJ Sales, Farvision, and VJOP."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def seed_crosswalk(self, mappings: list[dict]):
        """
        Seed the project crosswalk with manual mappings.

        Args:
            mappings: List of dicts with keys:
                - canonical_name: The unified project name
                - phase_name: Phase within the project (optional)
                - vjsales_project_name: Name as it appears in VJ Sales
                - farvision_project_code: Code as it appears in Farvision
        """
        query = text("""
            INSERT INTO silver.project_crosswalk
                (canonical_name, phase_name, vjsales_project_name, farvision_project_code)
            VALUES
                (:canonical_name, :phase_name, :vjsales_project_name, :farvision_project_code)
            ON CONFLICT (vjsales_project_name) DO UPDATE
                SET canonical_name = EXCLUDED.canonical_name,
                    farvision_project_code = EXCLUDED.farvision_project_code,
                    phase_name = EXCLUDED.phase_name,
                    updated_at = NOW()
        """)
        with self.engine.begin() as conn:
            for mapping in mappings:
                conn.execute(query, mapping)

        logger.info("Seeded %d project crosswalk entries", len(mappings))

    def detect_unmapped_projects(self) -> dict:
        """
        Find projects in bronze data that don't have crosswalk entries.
        Returns {vjsales_unmapped: [...], farvision_unmapped: [...]}.
        """
        unmapped = {"vjsales_unmapped": [], "farvision_unmapped": []}

        with self.engine.connect() as conn:
            # VJ Sales projects not in crosswalk
            vj_result = conn.execute(text("""
                SELECT DISTINCT project_name
                FROM bronze.stg_vjsales_bookings
                WHERE project_name IS NOT NULL
                AND project_name NOT IN (
                    SELECT vjsales_project_name FROM silver.project_crosswalk
                    WHERE vjsales_project_name IS NOT NULL
                )
            """))
            unmapped["vjsales_unmapped"] = [row[0] for row in vj_result]

            # Farvision projects not in crosswalk
            farv_result = conn.execute(text("""
                SELECT DISTINCT project_code
                FROM bronze.stg_farvision_receipts
                WHERE project_code IS NOT NULL
                AND project_code NOT IN (
                    SELECT farvision_project_code FROM silver.project_crosswalk
                    WHERE farvision_project_code IS NOT NULL
                )
            """))
            unmapped["farvision_unmapped"] = [row[0] for row in farv_result]

        if unmapped["vjsales_unmapped"] or unmapped["farvision_unmapped"]:
            logger.warning("Unmapped projects detected: %s", unmapped)

        return unmapped
