"""
tests/test_pipeline.py
========================
Tests for all 5 AutoMapper agents.
Runs without Ollama — LLM calls are mocked.

Usage:
    pytest tests/ -v
    pytest tests/ -v -k "test_schema"    # run specific tests
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def sample_csv(tmp_path):
    """Create a small test CSV with intentional issues."""
    df = pd.DataFrame({
        "order_number":   ["ORD001", "ORD002", "ORD003", "ORD002"],  # duplicate
        "buyer_id":       ["C001", None, "C003", "C002"],            # 1 null
        "shop_id":        ["DE_ONLINE", "AT_ONLINE", "CH_ONLINE", "DE_ONLINE"],
        "sale_channel":   ["web", "mobile", "app", "web"],
        "order_datetime": ["2024-01-15 10:00:00", "2024-01-16 12:00:00",
                           "2024-01-17 14:00:00", "2024-01-15 10:00:00"],
        "sku":            ["SKU001", "SKU002", "SKU003", "SKU001"],
        "qty":            [1, 2, 1, 3],
        "sale_price":     [99.99, 149.50, -10.00, 75.00],            # 1 negative
        "discount":       [0, 10, 0, 5],
        "payment_type":   ["credit_card", "paypal", "klarna", "credit_card"],
    })
    path = tmp_path / "test_orders.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def mock_config(tmp_path):
    """Write a minimal config.yaml for tests."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
ollama:
  host: "http://localhost:11434"
  model: "codellama:7b"
  temperature: 0.1
  timeout: 30
api:
  host: "0.0.0.0"
  port: 8003
  workers: 1
pipeline:
  max_sample_rows: 100
  anomaly_threshold: 0.05
  confidence_low: 0.60
  confidence_high: 0.90
data:
  sample_dir: "data/sample"
  output_dir: "data/output"
  upload_dir: "data/uploads"
""")
    return str(cfg)


# ── Agent 1: Schema Analyzer ───────────────────────────────────

class TestSchemaAnalyzer:

    def test_analyze_returns_correct_columns(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        assert profile["total_columns"] == 10
        assert profile["total_rows"] == 4
        col_names = [c["name"] for c in profile["columns"]]
        assert "order_number" in col_names
        assert "sale_price" in col_names

    def test_detects_nulls(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        buyer_col = next(c for c in profile["columns"] if c["name"] == "buyer_id")
        assert buyer_col["null_count"] == 1
        assert buyer_col["null_pct"] == 25.0

    def test_format_for_llm_returns_string(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)
        text = analyzer.format_for_llm(profile)

        assert isinstance(text, str)
        assert "SOURCE FILE" in text
        assert "order_number" in text

    def test_detects_negative_price(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        issues = [q for q in profile["quality_issues"] if "negative" in q["issue"]]
        assert len(issues) > 0, "Should flag negative values in sale_price"


# ── Agent 2: LLM Mapper ────────────────────────────────────────

MOCK_LLM_RESPONSE = json.dumps({
    "mappings": [
        {
            "source_col":   "order_number",
            "target_table": "staging.raw_transactions",
            "target_col":   "transaction_id",
            "confidence":   0.95,
            "transform":    None,
            "reasoning":    "Order number maps to transaction ID"
        },
        {
            "source_col":   "buyer_id",
            "target_table": "staging.raw_transactions",
            "target_col":   "customer_id",
            "confidence":   0.92,
            "transform":    None,
            "reasoning":    "Buyer ID is the customer identifier"
        },
        {
            "source_col":   "sale_price",
            "target_table": "staging.raw_transactions",
            "target_col":   "unit_price",
            "confidence":   0.88,
            "transform":    None,
            "reasoning":    "Sale price maps to unit price"
        },
        {
            "source_col":   "qty",
            "target_table": "staging.raw_transactions",
            "target_col":   "quantity",
            "confidence":   0.99,
            "transform":    None,
            "reasoning":    "Direct quantity mapping"
        },
        {
            "source_col":   "payment_type",
            "target_table": "staging.raw_transactions",
            "target_col":   "payment_method",
            "confidence":   0.91,
            "transform":    None,
            "reasoning":    "Payment type maps to payment method"
        },
    ],
    "unmapped_columns": ["shop_id", "sale_channel", "order_datetime"],
    "notes": "Good match overall"
})


class TestLLMMapper:

    @patch("backend.agents.llm_mapper.OllamaClient")
    def test_map_columns_returns_mappings(self, mock_ollama_cls, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.llm_mapper import LLMMapper

        # Mock Ollama to avoid needing the real model
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = MOCK_LLM_RESPONSE
        mock_ollama_cls.return_value = mock_ollama

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)
        profile_text = analyzer.format_for_llm(profile)

        mapper = LLMMapper(mock_config)
        mapper.ollama = mock_ollama

        result = mapper.map_columns(profile, "retail_dwh", profile_text)

        assert "mappings" in result
        assert result["total_mapped"] > 0

    @patch("backend.agents.llm_mapper.OllamaClient")
    def test_status_labels_applied(self, mock_ollama_cls, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.llm_mapper import LLMMapper

        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = MOCK_LLM_RESPONSE
        mock_ollama_cls.return_value = mock_ollama

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)
        profile_text = analyzer.format_for_llm(profile)

        mapper = LLMMapper(mock_config)
        mapper.ollama = mock_ollama
        result = mapper.map_columns(profile, "retail_dwh", profile_text)

        statuses = {m["status"] for m in result["mappings"]}
        # High confidence mappings should be auto-approved
        assert "AUTO_APPROVED" in statuses


# ── Agent 3: Type Validator ────────────────────────────────────

class TestTypeValidator:

    def test_validates_compatible_types(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.type_validator import TypeValidator
        from backend.core.target_schemas import get_schema

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        mappings = [
            {
                "source_col":   "qty",
                "target_table": "staging.raw_transactions",
                "target_col":   "quantity",
                "confidence":   0.99,
                "transform":    None,
                "status":       "AUTO_APPROVED",
            }
        ]

        validator = TypeValidator()
        schema = get_schema("retail_dwh")
        validated = validator.validate(mappings, profile, schema)

        assert len(validated) == 1
        assert validated[0]["type_status"] in ("COMPATIBLE", "TRANSFORM_NEEDED", "UNKNOWN")

    def test_adds_transform_for_type_mismatch(self):
        from backend.agents.type_validator import TypeValidator

        mappings = [{
            "source_col":    "some_int_col",
            "target_table":  "staging.raw_transactions",
            "target_col":    "transaction_id",
            "confidence":    0.8,
            "transform":     None,
            "status":        "AUTO_APPROVED",
        }]
        profile = {
            "columns": [
                {"name": "some_int_col", "dtype": "INTEGER"}
            ]
        }
        schema = {
            "tables": {
                "staging.raw_transactions": {
                    "columns": {
                        "transaction_id": {"type": "VARCHAR(50)", "desc": "ID"}
                    }
                }
            }
        }
        validator = TypeValidator()
        result = validator.validate(mappings, profile, schema)
        assert result[0]["type_status"] == "TRANSFORM_NEEDED"
        assert "CAST" in result[0]["transform"]


# ── Agent 4: Anomaly Detector ──────────────────────────────────

class TestAnomalyDetector:

    def test_detects_duplicates(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.anomaly_detector import AnomalyDetector

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        detector = AnomalyDetector()
        result = detector.detect(sample_csv, profile)

        dup_issues = [a for a in result["anomalies"] if a["type"] == "DUPLICATE_ROWS"]
        assert len(dup_issues) == 1
        assert dup_issues[0]["count"] == 1

    def test_detects_negative_values(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.anomaly_detector import AnomalyDetector

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        detector = AnomalyDetector()
        result = detector.detect(sample_csv, profile)

        neg_issues = [a for a in result["anomalies"] if a["type"] == "NEGATIVE_VALUES"]
        assert len(neg_issues) > 0

    def test_quality_score_range(self, sample_csv, mock_config):
        from backend.agents.schema_analyzer import SchemaAnalyzer
        from backend.agents.anomaly_detector import AnomalyDetector

        analyzer = SchemaAnalyzer(mock_config)
        profile = analyzer.analyze(sample_csv)

        detector = AnomalyDetector()
        result = detector.detect(sample_csv, profile)

        assert 0 <= result["quality_score"] <= 100


# ── Agent 5: Code Generator ────────────────────────────────────

class TestCodeGenerator:

    def test_generates_valid_python(self):
        from backend.agents.code_generator import CodeGenerator

        mappings = [
            {
                "source_col": "order_number",
                "target_col": "transaction_id",
                "transform":  None,
                "status":     "AUTO_APPROVED",
            },
            {
                "source_col": "buyer_id",
                "target_col": "customer_id",
                "transform":  "LOWER(TRIM(buyer_id))",
                "status":     "AUTO_APPROVED",
            },
        ]
        anomalies = [
            {
                "type":     "DUPLICATE_ROWS",
                "column":   "ALL",
                "count":    2,
                "pct":      5.0,
                "severity": "HIGH",
                "fix":      "df.drop_duplicates(inplace=True)",
            }
        ]

        gen = CodeGenerator()
        code = gen.generate(
            source_filename="test_orders.csv",
            target_schema_name="retail_dwh",
            target_table="staging.raw_transactions",
            mappings=mappings,
            anomalies=anomalies,
        )

        assert "def extract" in code
        assert "def transform" in code
        assert "def load" in code
        assert "def run" in code
        assert "transaction_id" in code
        assert "drop_duplicates" in code

    def test_handles_manual_mappings(self):
        from backend.agents.code_generator import CodeGenerator

        mappings = [
            {
                "source_col": "weird_col",
                "target_col": None,
                "transform":  None,
                "status":     "MANUAL_REQUIRED",
            }
        ]
        gen = CodeGenerator()
        code = gen.generate(
            source_filename="test.csv",
            target_schema_name="retail_dwh",
            target_table="staging.raw_transactions",
            mappings=mappings,
            anomalies=[],
        )
        # Manual mapping should appear as a comment
        assert "weird_col" in code
