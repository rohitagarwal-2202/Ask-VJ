"""
SQL Executor — Stage 4a of the Intelligence Pipeline

Safely executes validated SQL against the warehouse using a read-only connection.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.config import WarehouseDB

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a SQL query execution."""
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool      # True if LIMIT was hit
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.row_count == 0

    @property
    def is_scalar(self) -> bool:
        """True if result is a single value (1 row, 1 col)."""
        return self.row_count == 1 and len(self.columns) == 1

    def to_dict_list(self) -> list[dict]:
        """Convert rows to list of dicts for JSON serialization."""
        return [dict(zip(self.columns, row)) for row in self.rows]


class SQLExecutor:
    """Executes SQL queries against the warehouse with safety constraints."""

    STATEMENT_TIMEOUT_MS = 30_000  # 30 seconds
    MAX_RESULT_ROWS = 10_000

    def __init__(self, warehouse_config: WarehouseDB):
        # Use the read-only connection
        self.engine: Engine = create_engine(
            warehouse_config.readonly_connection_string,
            pool_pre_ping=True,
            pool_size=5,
            connect_args={"options": f"-c statement_timeout={self.STATEMENT_TIMEOUT_MS}"},
        )

    def execute(self, sql: str) -> QueryResult:
        """
        Execute a SQL query and return structured results.

        Uses a read-only DB role with statement_timeout enforced at connection level.
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = result.fetchmany(self.MAX_RESULT_ROWS + 1)

                truncated = len(rows) > self.MAX_RESULT_ROWS
                if truncated:
                    rows = rows[:self.MAX_RESULT_ROWS]

                # Convert SQLAlchemy Row objects to plain lists
                plain_rows = [list(row) for row in rows]

                # Serialize non-JSON-safe types
                for i, row in enumerate(plain_rows):
                    for j, val in enumerate(row):
                        if hasattr(val, "isoformat"):
                            plain_rows[i][j] = val.isoformat()
                        elif isinstance(val, (bytes, memoryview)):
                            plain_rows[i][j] = str(val)

                return QueryResult(
                    columns=columns,
                    rows=plain_rows,
                    row_count=len(plain_rows),
                    truncated=truncated,
                )

        except Exception as e:
            error_msg = str(e)
            logger.error("SQL execution failed: %s", error_msg)

            # Classify common errors for better self-correction prompts
            if "statement timeout" in error_msg.lower():
                error_msg = "Query timed out after 30 seconds. Simplify the query or add more filters."
            elif "permission denied" in error_msg.lower():
                error_msg = "Permission denied. Ensure query only uses gold schema SELECT statements."
            elif "does not exist" in error_msg.lower():
                error_msg = f"Table or column not found: {error_msg}"

            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                truncated=False,
                error=error_msg,
            )
