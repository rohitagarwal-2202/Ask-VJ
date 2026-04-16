"""
Tests for Ask VJ configuration loading.

Verifies defaults, connection string formats, and env-var-driven source database population.
"""

import os

import pytest

from backend.config import (
    AppConfig,
    ETLConfig,
    LLMConfig,
    SourceDB,
    WarehouseDB,
    load_config,
)


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------


def test_load_config_returns_app_config():
    config = load_config()
    assert isinstance(config, AppConfig)


# ---------------------------------------------------------------------------
# Warehouse defaults
# ---------------------------------------------------------------------------


def test_default_warehouse_settings():
    wh = WarehouseDB()
    assert wh.host == "localhost"
    assert wh.port == 5432
    assert wh.database == "askvj_warehouse"


def test_warehouse_connection_string_format():
    wh = WarehouseDB()
    cs = wh.connection_string
    assert cs.startswith("postgresql+psycopg2://")
    assert "localhost" in cs
    assert "5432" in cs
    assert "askvj_warehouse" in cs


def test_warehouse_readonly_connection_string_uses_ro_user():
    wh = WarehouseDB()
    ro_cs = wh.readonly_connection_string
    assert "askvj_readonly" in ro_cs
    assert "askvj_ro_dev" in ro_cs
    assert ro_cs.startswith("postgresql+psycopg2://")


# ---------------------------------------------------------------------------
# SourceDB connection strings
# ---------------------------------------------------------------------------


def test_source_db_mssql_connection_string():
    src = SourceDB(
        name="farvision",
        driver="mssql",
        host="10.0.0.1",
        port=1433,
        database="FarvisionDB",
        username="sa",
        password="secret",
    )
    cs = src.connection_string
    assert cs.startswith("mssql+pyodbc://")
    assert "ODBC+Driver+18+for+SQL+Server" in cs
    assert "TrustServerCertificate=yes" in cs
    assert "10.0.0.1:1433" in cs
    assert "FarvisionDB" in cs


def test_source_db_postgresql_connection_string():
    src = SourceDB(
        name="vjsales",
        driver="postgresql",
        host="10.0.0.2",
        port=5432,
        database="vjsales_db",
        username="pg",
        password="pgpass",
    )
    cs = src.connection_string
    assert cs.startswith("postgresql+psycopg2://")
    assert "10.0.0.2:5432" in cs
    assert "vjsales_db" in cs


# ---------------------------------------------------------------------------
# Source databases populated from environment
# ---------------------------------------------------------------------------


def test_farvision_loaded_from_env(monkeypatch):
    monkeypatch.setenv("FARVISION_HOST", "farvision.local")
    monkeypatch.setenv("FARVISION_PORT", "1433")
    monkeypatch.setenv("FARVISION_DB", "FarDB")
    monkeypatch.setenv("FARVISION_USER", "usr")
    monkeypatch.setenv("FARVISION_PASSWORD", "pwd")

    # Remove other source env vars to isolate
    monkeypatch.delenv("VJSALES_HOST", raising=False)
    monkeypatch.delenv("VJOP_HOST", raising=False)

    config = load_config()
    names = [s.name for s in config.source_databases]
    assert "farvision" in names


def test_vjsales_loaded_from_env(monkeypatch):
    monkeypatch.setenv("VJSALES_HOST", "vjsales.local")
    monkeypatch.setenv("VJSALES_PORT", "5432")
    monkeypatch.setenv("VJSALES_DB", "SalesDB")
    monkeypatch.setenv("VJSALES_USER", "usr")
    monkeypatch.setenv("VJSALES_PASSWORD", "pwd")

    monkeypatch.delenv("FARVISION_HOST", raising=False)
    monkeypatch.delenv("VJOP_HOST", raising=False)

    config = load_config()
    names = [s.name for s in config.source_databases]
    assert "vjsales" in names


def test_vjop_loaded_from_env(monkeypatch):
    monkeypatch.setenv("VJOP_HOST", "vjop.local")
    monkeypatch.setenv("VJOP_PORT", "1433")
    monkeypatch.setenv("VJOP_USER", "usr")
    monkeypatch.setenv("VJOP_PASSWORD", "pwd")

    monkeypatch.delenv("FARVISION_HOST", raising=False)
    monkeypatch.delenv("VJSALES_HOST", raising=False)

    config = load_config()
    names = [s.name for s in config.source_databases]
    assert "vjop" in names

    vjop = [s for s in config.source_databases if s.name == "vjop"][0]
    assert vjop.database == "RefferalAndLoyalty"


def test_no_sources_without_env(monkeypatch):
    monkeypatch.delenv("FARVISION_HOST", raising=False)
    monkeypatch.delenv("VJSALES_HOST", raising=False)
    monkeypatch.delenv("VJOP_HOST", raising=False)
    # Prevent load_dotenv from re-loading .env after monkeypatch clears vars
    monkeypatch.setattr("backend.config.load_dotenv", lambda: None)

    config = load_config()
    assert config.source_databases == []


# ---------------------------------------------------------------------------
# LLM defaults
# ---------------------------------------------------------------------------


def test_default_llm_config():
    llm = LLMConfig()
    assert llm.reasoning_model == "mixtral:8x7b"
    assert llm.sql_model == "sqlcoder:15b"
    assert llm.embedding_model == "nomic-embed-text"


# ---------------------------------------------------------------------------
# ETL defaults
# ---------------------------------------------------------------------------


def test_default_etl_config():
    etl = ETLConfig()
    assert etl.fuzzy_match_threshold == 0.6
    assert etl.auto_resolve_confidence == 0.85
