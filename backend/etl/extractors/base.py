"""
Base Extractor — Abstract class for incremental data extraction from source systems.

All source-specific extractors (Farvision, VJ Sales, VJOP) inherit from this.
Handles watermarking, batch tracking, and sync logging.
"""

import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base for source system extractors.

    Subclasses must implement:
        - source_name: str property
        - tables_to_extract: list of (source_table, staging_table, timestamp_column) tuples
        - build_extract_query(): SQL to pull data from source
    """

    def __init__(self, source_connection_string: str, warehouse_connection_string: str):
        self.source_engine: Engine = create_engine(source_connection_string)
        self.warehouse_engine: Engine = create_engine(warehouse_connection_string)
        self.batch_id = uuid.uuid4()

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this source system (e.g., 'farvision', 'vjsales')."""
        ...

    @abstractmethod
    def get_extract_tasks(self) -> list[dict]:
        """
        Return list of extraction tasks. Each task is a dict:
        {
            "source_query": "SELECT ... FROM source_table WHERE updated > :watermark",
            "staging_table": "bronze.stg_vjsales_leads",
            "timestamp_column": "updated_date",  # column to use as watermark
        }
        """
        ...

    def get_watermark(self, staging_table: str) -> datetime | None:
        """Get the last successful sync timestamp for a staging table."""
        query = text("""
            SELECT last_source_timestamp
            FROM bronze.sync_log
            WHERE source_system = :source AND table_name = :table AND status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """)
        with self.warehouse_engine.connect() as conn:
            result = conn.execute(query, {
                "source": self.source_name,
                "table": staging_table,
            }).fetchone()
        return result[0] if result else None

    def log_sync_start(self, staging_table: str) -> int:
        """Record the start of a sync operation."""
        query = text("""
            INSERT INTO bronze.sync_log (batch_id, source_system, table_name, status)
            VALUES (:batch_id, :source, :table, 'running')
            RETURNING sync_id
        """)
        with self.warehouse_engine.begin() as conn:
            result = conn.execute(query, {
                "batch_id": str(self.batch_id),
                "source": self.source_name,
                "table": staging_table,
            })
            return result.fetchone()[0]

    def log_sync_complete(self, sync_id: int, records: int, last_timestamp: datetime | None):
        """Record successful completion of a sync operation."""
        query = text("""
            UPDATE bronze.sync_log
            SET status = 'success',
                completed_at = NOW(),
                records_extracted = :records,
                last_source_timestamp = :last_ts
            WHERE sync_id = :sync_id
        """)
        with self.warehouse_engine.begin() as conn:
            conn.execute(query, {
                "sync_id": sync_id,
                "records": records,
                "last_ts": last_timestamp,
            })

    def log_sync_failed(self, sync_id: int, error: str):
        """Record a failed sync operation."""
        query = text("""
            UPDATE bronze.sync_log
            SET status = 'failed',
                completed_at = NOW(),
                error_message = :error
            WHERE sync_id = :sync_id
        """)
        with self.warehouse_engine.begin() as conn:
            conn.execute(query, {"sync_id": sync_id, "error": error[:2000]})

    def extract(self) -> dict[str, int]:
        """
        Run extraction for all configured tables.
        Returns dict of {staging_table: records_extracted}.
        """
        results = {}

        for task in self.get_extract_tasks():
            staging_table = task["staging_table"]
            sync_id = self.log_sync_start(staging_table)

            try:
                watermark = self.get_watermark(staging_table)
                logger.info(
                    "Extracting %s → %s (watermark: %s)",
                    self.source_name, staging_table, watermark
                )

                # Pull data from source
                with self.source_engine.connect() as source_conn:
                    if watermark:
                        result = source_conn.execute(
                            text(task["source_query"]),
                            {"watermark": watermark}
                        )
                    else:
                        result = source_conn.execute(text(task["full_query"]))

                    rows = result.fetchall()
                    columns = result.keys()

                if not rows:
                    logger.info("No new records for %s", staging_table)
                    self.log_sync_complete(sync_id, 0, watermark)
                    results[staging_table] = 0
                    continue

                # Insert into staging table
                records_inserted = self._insert_to_staging(
                    staging_table, columns, rows
                )

                # Find the max timestamp for watermarking
                ts_col = task.get("timestamp_column")
                last_ts = watermark
                if ts_col and rows:
                    col_index = list(columns).index(ts_col)
                    timestamps = [r[col_index] for r in rows if r[col_index]]
                    if timestamps:
                        last_ts = max(timestamps)

                self.log_sync_complete(sync_id, records_inserted, last_ts)
                results[staging_table] = records_inserted
                logger.info("Extracted %d records → %s", records_inserted, staging_table)

            except Exception as e:
                logger.error("Extraction failed for %s: %s", staging_table, e)
                self.log_sync_failed(sync_id, str(e))
                results[staging_table] = -1

        return results

    def _insert_to_staging(self, staging_table: str, columns: list, rows: list) -> int:
        """Bulk insert rows into a bronze staging table."""
        # Build column list (exclude auto-generated _sync_id, _synced_at, _source_system)
        source_columns = [c for c in columns]
        col_names = ", ".join(source_columns)
        placeholders = ", ".join(f":{c}" for c in source_columns)

        insert_sql = text(f"""
            INSERT INTO {staging_table} (_batch_id, {col_names})
            VALUES (:_batch_id, {placeholders})
        """)

        batch_data = []
        for row in rows:
            row_dict = {"_batch_id": str(self.batch_id)}
            for col, val in zip(source_columns, row):
                row_dict[col] = val
            batch_data.append(row_dict)

        with self.warehouse_engine.begin() as conn:
            conn.execute(insert_sql, batch_data)

        return len(rows)
