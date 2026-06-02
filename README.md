# AutoMapper 🗺️
### LLM-Powered ETL Schema Mapping & Code Generation

AutoMapper is a 5-agent AI pipeline that automatically maps source CSV files to target data warehouse schemas and generates executable Python ETL scripts. It runs CodeLlama 7B locally via Ollama — no cloud API costs.

---

## Architecture

```
CSV Upload
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI  (/map)                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Agent 1     │    │  Agent 2     │    │  Agent 3     │
│  Schema      │───▶│  LLM Mapper  │───▶│  Type        │
│  Analyzer    │    │  (CodeLlama) │    │  Validator   │
└──────────────┘    └──────────────┘    └──────────────┘
                                                │
                    ┌──────────────┐            │
                    │  Agent 5     │◀───────────┤
                    │  Code        │            │
                    │  Generator   │    ┌──────────────┐
                    └──────────────┘    │  Agent 4     │
                           │           │  Anomaly     │
                           ▼           │  Detector    │
                    Generated ETL      └──────────────┘
                    Python Script
```

### The 5 Agents

| # | Agent | File | Uses LLM? | Purpose |
|---|-------|------|-----------|---------|
| 1 | Schema Analyzer | `backend/agents/schema_analyzer.py` | ❌ No | Profiles CSV — types, nulls, patterns, sample values |
| 2 | LLM Mapper | `backend/agents/llm_mapper.py` | ✅ Yes | Maps source columns → target schema columns |
| 3 | Type Validator | `backend/agents/type_validator.py` | ❌ No | Validates type compatibility, adds SQL casts |
| 4 | Anomaly Detector | `backend/agents/anomaly_detector.py` | ❌ No | IQR outliers, nulls, duplicates, negatives |
| 5 | Code Generator | `backend/agents/code_generator.py` | ❌ No | Produces executable Python ETL script |

Only Agent 2 calls the LLM — the rest are deterministic for speed and reliability.

---

## Project Structure

```
automapper/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── schema_analyzer.py     # Agent 1
│   │   ├── llm_mapper.py          # Agent 2
│   │   ├── type_validator.py      # Agent 3
│   │   ├── anomaly_detector.py    # Agent 4
│   │   └── code_generator.py      # Agent 5
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pipeline.py            # Orchestrates all 5 agents
│   │   ├── ollama_client.py       # Ollama REST wrapper
│   │   └── target_schemas.py      # Target DWH schema definitions
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py                # FastAPI endpoints
│   └── data/
│       └── sample_generator.py    # Generates test CSV files
├── config/
│   └── config.yaml                # All configuration
├── data/
│   ├── sample/                    # Test CSVs (generated)
│   ├── uploads/                   # Temp upload storage
│   └── output/                    # Generated ETL scripts
├── docker/
│   └── init.sql                   # PostgreSQL schema init
├── tests/
│   └── test_pipeline.py           # Full test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py                         # Local dev launcher
└── README.md
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker + Docker Compose
- [Ollama](https://ollama.com) installed on your Mac

### 1. Install Ollama and pull the model
```bash
# Install from https://ollama.com
ollama serve                    # start Ollama
ollama pull codellama:7b        # download the model (~3.8GB)
```

### 2. Clone and install Python dependencies
```bash
git clone <your-repo>
cd automapper
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start PostgreSQL (target DWH)
```bash
docker-compose up postgres -d
# Schema is auto-created from docker/init.sql
```

### 4. Generate sample test data
```bash
python backend/data/sample_generator.py
# Creates: data/sample/ecommerce_orders.csv
#          data/sample/crm_customers.csv
#          data/sample/product_catalog.csv
```

### 5. Start the API
```bash
python run.py
# API: http://localhost:8003
# Docs: http://localhost:8003/docs
```

### 6. Run a mapping
```bash
curl -X POST http://localhost:8003/map \
  -F 'file=@data/sample/ecommerce_orders.csv' \
  -F 'target_schema=retail_dwh' \
  -F 'target_table=staging.raw_transactions'
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | Service status + Ollama availability |
| `GET`  | `/schemas` | List available target schemas |
| `POST` | `/map` | Upload CSV → run full pipeline |
| `GET`  | `/download/{job_id}` | Download generated ETL script |

### POST /map — Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | CSV file | required | Source data file |
| `target_schema` | string | `retail_dwh` | Schema to map to |
| `target_table` | string | `staging.raw_transactions` | Target table |

### Response Structure

```json
{
  "job_id": "a1b2c3d4",
  "source_file": "ecommerce_orders.csv",
  "target_schema": "retail_dwh",
  "target_table": "staging.raw_transactions",
  "summary": {
    "total_columns": 10,
    "auto_approved": 7,
    "needs_review": 2,
    "manual_required": 1,
    "quality_score": 82,
    "total_issues": 3,
    "pipeline_time_s": 12.4
  },
  "mappings": [...],
  "anomalies": [...],
  "recommendations": [...],
  "download_url": "/download/a1b2c3d4",
  "code_preview": "..."
}
```

---

## Configuration (`config/config.yaml`)

```yaml
ollama:
  host: "http://host.docker.internal:11434"  # Docker → Mac host
  model: "codellama:7b"
  temperature: 0.1    # Low = deterministic mappings
  timeout: 120

pipeline:
  max_sample_rows: 100
  confidence_low:  0.60   # Below = manual review
  confidence_high: 0.90   # Above = auto-approve
```

### Adding a new target schema

Edit `backend/core/target_schemas.py` — add your schema to `SCHEMA_REGISTRY` following the existing pattern. Then reference it in `config.yaml`.

---

## Running with Docker

```bash
# Full stack (API + PostgreSQL)
docker-compose up --build

# API only
docker-compose up automapper

# View logs
docker-compose logs -f automapper
```

---

## Running Tests

```bash
pytest tests/ -v
# Tests mock Ollama — no LLM needed to run tests
```

---

## Data Quality Scoring

Each run produces a 0–100 quality score:
- **90–100** ✅ Clean data, safe to load
- **70–89** ⚠️ Minor issues, review recommendations
- **50–69** 🔶 Significant issues, apply fixes first
- **0–49** ❌ Major data problems, manual intervention needed

---

## Mapping Confidence Levels

| Level | Threshold | Action |
|-------|-----------|--------|
| ✅ Auto-approved | ≥ 0.90 | Included in ETL automatically |
| ⚠️ Needs review | 0.60–0.89 | Human should verify before running |
| ❌ Manual required | < 0.60 | Must be mapped manually |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | CodeLlama 7B via Ollama |
| API | FastAPI + Uvicorn |
| Data Processing | Pandas + NumPy |
| Target DB | PostgreSQL 16 |
| ORM / Load | SQLAlchemy |
| Container | Docker + Docker Compose |
| Testing | Pytest |
