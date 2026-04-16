# Ask VJ — Enterprise Intelligence Engine

Ask VJ is an AI-driven decision intelligence platform that bridges the gap between complex enterprise data and actionable business insights. It provides a unified conversational layer over Farvision ERP, VJ Sales App, and VJOP, enabling stakeholders to query operational data in natural language.

## Architecture

```
User (Web / WhatsApp / Telegram)
         │
    API Gateway (Node.js)
         │
    Intelligence Engine (Python FastAPI)
    ├── Query Parser (intent + entities)
    ├── RAG Pipeline (schema retrieval)
    ├── SQL Generator (local LLM)
    ├── Executor + Verifier
    └── Response Formatter
         │
    Data Warehouse (PostgreSQL)
    ├── Gold:   Star schema (LLM-queryable)
    ├── Silver: Entity resolution layer
    └── Bronze: Raw staging from sources
         │
    ETL Pipeline (Python, 2-hour sync)
    ├── Farvision Extractor (MS SQL)
    └── VJ Sales Extractor (PostgreSQL)
```

## Quick Start

```bash
# 1. Start infrastructure
docker compose up -d

# 2. Install Python dependencies
cd backend && pip install -r requirements.txt

# 3. Copy and configure environment
cp .env.example .env

# 4. Run the ETL pipeline
python -m backend.etl.run_pipeline

# 5. Start the API
python -m backend.main
```

## Key Design Decisions

- **Local LLM only** — zero sensitive data leaves the internal network
- **Medallion architecture** (Bronze → Silver → Gold) — raw data preserved, entity resolution separated, clean star schema for querying
- **Entity resolution** — links records across systems via unit+project matching, phone matching, and fuzzy name matching
- **Dual-model strategy** — reasoning model (Mixtral) for intent parsing, SQL specialist (SQLCoder) for query generation

## Project Structure

```
ask-vj/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py             # Centralized configuration
│   ├── etl/                  # Data pipeline
│   │   ├── extractors/       # Source system connectors
│   │   ├── resolvers/        # Entity resolution
│   │   ├── transformers/     # Gold layer builders
│   │   ├── validators/       # Quality checks
│   │   └── sql/              # Schema definitions
│   ├── intelligence/         # LLM + RAG engine
│   └── api/                  # REST endpoints
├── gateway/                  # Node.js API gateway
├── frontend/                 # React web UI
├── docker-compose.yml
└── .env.example
```
