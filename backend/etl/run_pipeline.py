"""
Ask VJ ETL Pipeline — Main Orchestrator

Runs the full Bronze → Silver → Gold pipeline.
Designed to be called by cron every 2 hours.

Sources:
  1. Farvision ERP DWH (SQL Server, TenantId=75)
  2. VJ Sales App (PostgreSQL/Supabase)
  3. VJOP Referral & Loyalty (SQL Server)

Usage:
    python -m backend.etl.run_pipeline
"""

import logging
import sys
from datetime import datetime

from backend.config import load_config
from backend.etl.extractors.vj_sales import VJSalesExtractor
from backend.etl.extractors.farvision import FarvisionExtractor
from backend.etl.extractors.vjop import VJOPExtractor
from backend.etl.resolvers.entity_resolver import EntityResolver
from backend.etl.resolvers.project_mapper import ProjectMapper
from backend.etl.transformers.dimensions import DimensionTransformer
from backend.etl.transformers.facts import FactTransformer
from backend.etl.transformers.snapshots import SnapshotTransformer
from backend.etl.validators.quality_checks import QualityChecker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("etl.pipeline")

# Map source database names to extractor classes
EXTRACTORS = {
    "vjsales": VJSalesExtractor,
    "farvision": FarvisionExtractor,
    "vjop": VJOPExtractor,
}


def run_pipeline():
    """Execute the full ETL pipeline: Extract → Resolve → Transform → Validate."""
    config = load_config()
    warehouse_conn = config.warehouse.connection_string

    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("ASK VJ ETL PIPELINE — Starting at %s", start_time)
    logger.info("=" * 60)

    # ── Step 1: EXTRACT (Bronze) ──────────────────────────────
    logger.info("── Step 1: EXTRACT (Bronze) ──")
    extract_results = {}

    for source_db in config.source_databases:
        extractor_cls = EXTRACTORS.get(source_db.name)
        if not extractor_cls:
            logger.warning("Unknown source: %s, skipping", source_db.name)
            continue

        extractor = extractor_cls(source_db.connection_string, warehouse_conn)
        results = extractor.extract()
        extract_results[source_db.name] = results

    logger.info("Extraction complete: %s", extract_results)

    # ── Step 2: RESOLVE (Silver) ──────────────────────────────
    logger.info("── Step 2: RESOLVE (Silver) ──")

    # Auto-discover new projects from bronze data
    project_mapper = ProjectMapper(warehouse_conn)
    discovery = project_mapper.auto_discover_projects()
    logger.info("Project auto-discovery: %s", discovery)

    # Check for any remaining unmapped projects
    unmapped = project_mapper.detect_unmapped_projects()
    if any(unmapped.values()):
        logger.warning(
            "Unmapped projects remain! VJ Sales: %d, Farvision: %d, VJOP: %d. "
            "Add these to silver.project_crosswalk manually.",
            len(unmapped["vjsales_unmapped"]),
            len(unmapped["farvision_unmapped"]),
            len(unmapped["vjop_unmapped"]),
        )

    # Run entity resolution (ID-based matching + fuzzy fallback)
    resolver = EntityResolver(warehouse_conn, config.etl.fuzzy_match_threshold)
    resolve_stats = resolver.resolve()
    logger.info("Entity resolution: %s", resolve_stats)

    # ── Step 3: TRANSFORM (Gold) ──────────────────────────────
    logger.info("── Step 3: TRANSFORM (Gold) ──")

    dim_transformer = DimensionTransformer(warehouse_conn)
    dim_transformer.transform_all()

    fact_transformer = FactTransformer(warehouse_conn)
    fact_transformer.transform_all()

    snapshot_transformer = SnapshotTransformer(warehouse_conn)
    snapshot_transformer.build_daily_snapshot()

    # ── Step 4: VALIDATE ──────────────────────────────────────
    logger.info("── Step 4: VALIDATE ──")

    checker = QualityChecker(warehouse_conn)
    check_results = checker.run_all_checks()

    errors = [r for r in check_results if not r.passed and r.severity == "error"]
    if errors:
        logger.error(
            "Pipeline completed with %d quality errors! Review before trusting gold data.",
            len(errors),
        )

    # ── Summary ───────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info("ASK VJ ETL PIPELINE — Completed in %.1f seconds", elapsed)
    logger.info("Extract: %s", extract_results)
    logger.info("Resolve: %s", resolve_stats)
    logger.info("Quality errors: %d", len(errors))
    logger.info("=" * 60)

    return {
        "extract": extract_results,
        "resolve": resolve_stats,
        "quality_errors": len(errors),
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    try:
        result = run_pipeline()
        if result["quality_errors"] > 0:
            sys.exit(1)
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        sys.exit(2)
