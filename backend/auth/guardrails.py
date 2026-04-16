"""
Ask VJ — Data Guardrails System

Enforces per-user data access policies at three layers:
  1. Schema filtering — removes denied tables/columns from LLM context
  2. SQL injection — adds project_key WHERE clauses
  3. SQL validation — blocks access to denied tables in final SQL

Policies are stored in app.data_policies with types:
  - project_filter: limits user to specific project_keys
  - table_access:   deny access to specific gold tables
  - column_mask:    mask specific columns with NULL
"""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.intelligence.schema_retriever import TableSchema

logger = logging.getLogger(__name__)


@dataclass
class UserPolicies:
    """Resolved access policies for a single user."""
    allowed_project_keys: list[int] | None  # None = all projects
    denied_tables: set[str]                 # e.g. {"gold.fact_receipts"}
    masked_columns: dict[str, str]          # "gold.fact_bookings.net_basic_price" -> "NULL"


class DataGuardrails:
    """Loads and enforces per-user data access policies."""

    def __init__(self, connection_string: str):
        self.engine: Engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            pool_size=2,
        )

    # ── Load policies from DB ──

    def load_policies(self, user_id: int) -> UserPolicies:
        """
        Query app.data_policies for the given user and build a UserPolicies object.

        Admin users get no restrictions.
        """
        with self.engine.connect() as conn:
            # Check if user is admin
            role_row = conn.execute(
                text("SELECT role FROM app.users WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()

            if role_row and role_row[0] == "admin":
                return UserPolicies(
                    allowed_project_keys=None,
                    denied_tables=set(),
                    masked_columns={},
                )

            # Load all policies for this user
            rows = conn.execute(
                text(
                    "SELECT policy_type, target, action, value "
                    "FROM app.data_policies WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).fetchall()

        allowed_project_keys: list[int] | None = None
        denied_tables: set[str] = set()
        masked_columns: dict[str, str] = {}

        for row in rows:
            policy_type, target, action, value = row

            if policy_type == "project_filter" and action == "allow":
                # value is JSONB like {"project_keys": [1, 2, 3]}
                keys = (value or {}).get("project_keys", [])
                if allowed_project_keys is None:
                    allowed_project_keys = list(keys)
                else:
                    # Merge multiple project_filter policies
                    allowed_project_keys.extend(keys)

            elif policy_type == "table_access" and action == "deny":
                denied_tables.add(target)

            elif policy_type == "column_mask" and action == "mask":
                mask_value = (value or {}).get("replacement", "NULL")
                masked_columns[target] = mask_value

        # Deduplicate project keys
        if allowed_project_keys is not None:
            allowed_project_keys = sorted(set(allowed_project_keys))

        return UserPolicies(
            allowed_project_keys=allowed_project_keys,
            denied_tables=denied_tables,
            masked_columns=masked_columns,
        )

    # ── Schema filtering (Stage 2) ──

    def filter_schema_context(
        self, schemas: list[TableSchema], policies: UserPolicies
    ) -> list[TableSchema]:
        """
        Remove denied tables entirely and strip masked columns from column lists.
        Returns a new list — does not mutate the originals.
        """
        filtered: list[TableSchema] = []

        for schema in schemas:
            if schema.table_name in policies.denied_tables:
                logger.info("Guardrail: hiding table %s from schema context", schema.table_name)
                continue

            # Check if any columns need masking
            cols_to_mask = {
                col_ref.split(".")[-1]
                for col_ref, _ in policies.masked_columns.items()
                if col_ref.startswith(schema.table_name + ".")
            }

            if cols_to_mask:
                # Build new column list without masked columns
                new_columns = [
                    col for col in schema.columns
                    if col["name"] not in cols_to_mask
                ]
                filtered.append(TableSchema(
                    table_name=schema.table_name,
                    description=schema.description,
                    columns=new_columns,
                    joins=schema.joins,
                    sample_queries=schema.sample_queries,
                ))
            else:
                filtered.append(schema)

        return filtered

    # ── WHERE clause injection (Stage 3, post-generation) ──

    def inject_where_clauses(self, sql: str, policies: UserPolicies) -> str:
        """
        If allowed_project_keys is set, inject project_key IN (...) filters.

        Handles both existing WHERE clauses and queries without WHERE.
        """
        if policies.allowed_project_keys is None:
            return sql

        keys_csv = ", ".join(str(k) for k in policies.allowed_project_keys)
        project_filter = f"project_key IN ({keys_csv})"

        # Check if SQL references any table with project_key
        # Match gold.table_name aliases to find which alias to use
        # Pattern: gold.some_table <alias>  or  gold.some_table AS <alias>
        if "project_key" not in sql.lower():
            # No project_key column referenced — nothing to filter
            return sql

        # If there's an existing WHERE, append with AND
        # If not, add WHERE before GROUP BY / ORDER BY / LIMIT / ;
        if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
            # Insert AND project_key IN (...) after the last WHERE condition,
            # before GROUP BY / ORDER BY / LIMIT / ;
            # Find the position right after WHERE ... (before GROUP BY, ORDER BY, LIMIT, or end)
            pattern = re.compile(
                r'(\bWHERE\b.+?)'
                r'(\s*(?:GROUP\s+BY|ORDER\s+BY|LIMIT|;|$))',
                re.IGNORECASE | re.DOTALL,
            )
            match = pattern.search(sql)
            if match:
                where_part = match.group(1)
                rest_part = match.group(2)
                sql = (
                    sql[:match.start()]
                    + where_part
                    + f"\n  AND {project_filter}"
                    + rest_part
                    + sql[match.end():]
                )
            else:
                # Fallback: append before the semicolon
                sql = sql.rstrip().rstrip(";")
                sql += f"\n  AND {project_filter};"
        else:
            # No WHERE clause — insert one before GROUP BY / ORDER BY / LIMIT / ;
            insert_pattern = re.compile(
                r'(\s*)(GROUP\s+BY|ORDER\s+BY|LIMIT|;)',
                re.IGNORECASE,
            )
            match = insert_pattern.search(sql)
            if match:
                insert_pos = match.start()
                sql = (
                    sql[:insert_pos]
                    + f"\nWHERE {project_filter}"
                    + sql[insert_pos:]
                )
            else:
                # No GROUP/ORDER/LIMIT — append before semicolon or at end
                sql = sql.rstrip().rstrip(";")
                sql += f"\nWHERE {project_filter};"

        return sql

    # ── SQL access validation (Stage 3, post-generation) ──

    def validate_sql_access(
        self, sql: str, policies: UserPolicies
    ) -> tuple[bool, str]:
        """
        Parse SQL for gold.table_name references and check against denied_tables.

        Returns:
            (True, "") if access is allowed
            (False, reason) if access is blocked
        """
        if not policies.denied_tables:
            return True, ""

        # Find all gold.table_name references in the SQL
        table_refs = set(re.findall(r'\bgold\.\w+', sql.lower()))

        blocked = table_refs & policies.denied_tables
        if blocked:
            tables = ", ".join(sorted(blocked))
            return False, f"Access denied to table(s): {tables}"

        return True, ""
