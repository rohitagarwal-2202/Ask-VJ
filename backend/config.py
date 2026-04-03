"""
Ask VJ — Centralized Configuration

All database connections, LLM endpoints, and ETL settings.
Reads from environment variables with sensible defaults for local development.
"""

import os
from dataclasses import dataclass, field


@dataclass
class SourceDB:
    """Connection config for a source system database."""
    name: str
    driver: str  # "mssql" or "postgresql"
    host: str
    port: int
    database: str
    username: str
    password: str

    @property
    def connection_string(self) -> str:
        if self.driver == "mssql":
            return (
                f"mssql+pyodbc://{self.username}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
                f"?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
            )
        return (
            f"postgresql+psycopg2://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass
class WarehouseDB:
    """Connection config for the Ask VJ data warehouse."""
    host: str = os.getenv("WAREHOUSE_HOST", "localhost")
    port: int = int(os.getenv("WAREHOUSE_PORT", "5432"))
    database: str = os.getenv("WAREHOUSE_DB", "askvj_warehouse")
    username: str = os.getenv("WAREHOUSE_USER", "askvj")
    password: str = os.getenv("WAREHOUSE_PASSWORD", "askvj_dev")

    # Read-only role for the intelligence engine
    readonly_user: str = os.getenv("WAREHOUSE_RO_USER", "askvj_readonly")
    readonly_password: str = os.getenv("WAREHOUSE_RO_PASSWORD", "askvj_ro_dev")

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql+psycopg2://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def readonly_connection_string(self) -> str:
        return (
            f"postgresql+psycopg2://{self.readonly_user}:{self.readonly_password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass
class LLMConfig:
    """LLM configuration — supports Anthropic API or local Ollama."""
    # Provider: "anthropic" for Claude API, "ollama" for local LLM
    provider: str = os.getenv("LLM_PROVIDER", "anthropic")

    # Anthropic API settings (used when provider = "anthropic")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Local Ollama settings (used when provider = "ollama")
    reasoning_model: str = os.getenv("LLM_REASONING_MODEL", "mixtral:8x7b")
    reasoning_endpoint: str = os.getenv("LLM_REASONING_ENDPOINT", "http://localhost:11434")
    sql_model: str = os.getenv("LLM_SQL_MODEL", "sqlcoder:15b")
    sql_endpoint: str = os.getenv("LLM_SQL_ENDPOINT", "http://localhost:11434")

    # Embedding model (for RAG — always via Ollama)
    embedding_model: str = os.getenv("LLM_EMBEDDING_MODEL", "nomic-embed-text")
    embedding_endpoint: str = os.getenv("LLM_EMBEDDING_ENDPOINT", "http://localhost:11434")

    # Inference settings
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    request_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))


@dataclass
class ETLConfig:
    """ETL pipeline settings."""
    sync_interval_hours: int = int(os.getenv("ETL_SYNC_INTERVAL_HOURS", "2"))
    bronze_retention_days: int = int(os.getenv("ETL_BRONZE_RETENTION_DAYS", "90"))
    batch_size: int = int(os.getenv("ETL_BATCH_SIZE", "5000"))
    query_timeout_seconds: int = int(os.getenv("ETL_QUERY_TIMEOUT", "300"))

    # Entity resolution thresholds
    fuzzy_match_threshold: float = float(os.getenv("ETL_FUZZY_THRESHOLD", "0.6"))
    auto_resolve_confidence: float = float(os.getenv("ETL_AUTO_RESOLVE_CONFIDENCE", "0.85"))


@dataclass
class VectorDBConfig:
    """Vector database for RAG schema retrieval."""
    backend: str = os.getenv("VECTOR_DB_BACKEND", "chromadb")  # chromadb or weaviate
    host: str = os.getenv("VECTOR_DB_HOST", "localhost")
    port: int = int(os.getenv("VECTOR_DB_PORT", "8000"))
    collection_name: str = os.getenv("VECTOR_DB_COLLECTION", "askvj_schema")


@dataclass
class AuthConfig:
    """Authentication and authorization settings."""
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
    otp_expiry_minutes: int = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
    otp_max_attempts: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))
    otp_gateway: str = os.getenv("OTP_GATEWAY", "mock")  # mock, twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")


@dataclass
class AppConfig:
    """Top-level application configuration."""
    warehouse: WarehouseDB = field(default_factory=WarehouseDB)
    llm: LLMConfig = field(default_factory=LLMConfig)
    etl: ETLConfig = field(default_factory=ETLConfig)
    vector_db: VectorDBConfig = field(default_factory=VectorDBConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    # Source system connections (populated from env or config file)
    source_databases: list[SourceDB] = field(default_factory=list)

    # API settings
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Clarification threshold
    clarification_threshold: float = float(os.getenv("CLARIFICATION_THRESHOLD", "0.7"))


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    config = AppConfig()

    # Add source databases from environment
    # Farvision (MS SQL Server)
    if os.getenv("FARVISION_HOST"):
        config.source_databases.append(SourceDB(
            name="farvision",
            driver="mssql",
            host=os.getenv("FARVISION_HOST", ""),
            port=int(os.getenv("FARVISION_PORT", "1433")),
            database=os.getenv("FARVISION_DB", ""),
            username=os.getenv("FARVISION_USER", ""),
            password=os.getenv("FARVISION_PASSWORD", ""),
        ))

    # VJ Sales App (PostgreSQL)
    if os.getenv("VJSALES_HOST"):
        config.source_databases.append(SourceDB(
            name="vjsales",
            driver="postgresql",
            host=os.getenv("VJSALES_HOST", ""),
            port=int(os.getenv("VJSALES_PORT", "5432")),
            database=os.getenv("VJSALES_DB", ""),
            username=os.getenv("VJSALES_USER", ""),
            password=os.getenv("VJSALES_PASSWORD", ""),
        ))

    # VJOP Referral & Loyalty (MS SQL Server)
    if os.getenv("VJOP_HOST"):
        config.source_databases.append(SourceDB(
            name="vjop",
            driver="mssql",
            host=os.getenv("VJOP_HOST", ""),
            port=int(os.getenv("VJOP_PORT", "1433")),
            database=os.getenv("VJOP_DB", "RefferalAndLoyalty"),
            username=os.getenv("VJOP_USER", ""),
            password=os.getenv("VJOP_PASSWORD", ""),
        ))

    return config
