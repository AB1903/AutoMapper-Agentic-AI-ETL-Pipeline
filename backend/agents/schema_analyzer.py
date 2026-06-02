"""
Agent 1 — Schema Analyzer

Scans an uploaded CSV file and builds a complete profile:
  - Column names and detected data types
  - Sample values (first 5 non-null)
  - Null count and percentage
  - Unique value count
  - Min/max for numeric columns
  - Pattern detection (email, date, ID, phone)

This profile is passed to Agent 2 (LLM Mapper) as context.
"""

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
import yaml

log = logging.getLogger(__name__)


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── Pattern detectors ──────────────────────────────────────────
EMAIL_RE   = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$')
DATE_RE    = re.compile(r'^\d{4}[-/]\d{2}[-/]\d{2}')
ID_RE      = re.compile(r'^[A-Z]{0,3}\d{3,}$')
PHONE_RE   = re.compile(r'^\+?[\d\s\-\(\)]{7,15}$')


def detect_pattern(series: pd.Series) -> str:
    """Detect semantic pattern from sample string values."""
    samples = series.dropna().astype(str).head(20).tolist()
    if not samples:
        return "unknown"

    email_count = sum(1 for s in samples if EMAIL_RE.match(s))
    date_count  = sum(1 for s in samples if DATE_RE.match(s))
    id_count    = sum(1 for s in samples if ID_RE.match(s))
    phone_count = sum(1 for s in samples if PHONE_RE.match(s))

    n = len(samples)
    if email_count / n > 0.7:  return "email"
    if date_count  / n > 0.7:  return "date"
    if id_count    / n > 0.7:  return "identifier"
    if phone_count / n > 0.7:  return "phone"
    return "text"


def detect_dtype(series: pd.Series) -> str:
    """Map pandas dtype to SQL-friendly type label."""
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):   return "INTEGER"
    if pd.api.types.is_float_dtype(dtype):     return "NUMERIC"
    if pd.api.types.is_bool_dtype(dtype):      return "BOOLEAN"
    if pd.api.types.is_datetime64_any_dtype(dtype): return "TIMESTAMP"

    # Try parsing as date
    sample = series.dropna().astype(str).head(5)
    try:
        pd.to_datetime(sample, infer_datetime_format=True)
        return "DATE/TIMESTAMP"
    except Exception:
        pass

    return "VARCHAR"


class SchemaAnalyzer:
    """
    Profiles a CSV file and returns a structured schema description
    ready to pass to the LLM mapper.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)
        self.max_rows = cfg["pipeline"]["max_sample_rows"]

    def analyze(self, file_path: str) -> dict:
        """
        Full schema analysis of a CSV file.

        Returns:
            dict with:
              - filename
              - total_rows
              - total_columns
              - columns: list of column profiles
              - sample_data: first 5 rows as dict
              - quality_issues: early-detected problems
        """
        path = Path(file_path)
        log.info("Agent 1 — Analyzing: %s", path.name)

        # Load file
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise ValueError(f"Cannot read file {file_path}: {e}")

        total_rows = len(df)
        log.info("Loaded %d rows × %d columns", total_rows, len(df.columns))

        # Profile each column
        columns = []
        quality_issues = []

        for col in df.columns:
            series  = df[col]
            dtype   = detect_dtype(series)
            pattern = detect_pattern(series) if dtype == "VARCHAR" else dtype.lower()

            null_count = int(series.isnull().sum())
            null_pct   = round(null_count / total_rows * 100, 1)
            unique     = int(series.nunique())

            # Sample values
            samples = (
                series.dropna()
                      .astype(str)
                      .head(5)
                      .tolist()
            )

            # Stats for numeric columns
            stats = {}
            if dtype in ("INTEGER", "NUMERIC"):
                numeric = pd.to_numeric(series, errors="coerce")
                stats = {
                    "min":  float(numeric.min()) if not numeric.isna().all() else None,
                    "max":  float(numeric.max()) if not numeric.isna().all() else None,
                    "mean": round(float(numeric.mean()), 2) if not numeric.isna().all() else None,
                }
                # Flag negative values in price/amount columns
                if numeric.min() < 0 and any(
                    kw in col.lower() for kw in
                    ["price", "amount", "revenue", "cost", "value"]
                ):
                    quality_issues.append({
                        "column":   col,
                        "issue":    f"{int((numeric < 0).sum())} negative values",
                        "severity": "HIGH",
                        "fix":      f"Filter: WHERE {col} >= 0"
                    })

            # Flag high null columns
            if null_pct > 30:
                quality_issues.append({
                    "column":   col,
                    "issue":    f"{null_pct}% null values",
                    "severity": "MEDIUM" if null_pct < 60 else "HIGH",
                    "fix":      f"COALESCE({col}, default_value) or drop column"
                })

            col_profile = {
                "name":        col,
                "dtype":       dtype,
                "pattern":     pattern,
                "null_count":  null_count,
                "null_pct":    null_pct,
                "unique":      unique,
                "samples":     samples,
                "stats":       stats,
            }
            columns.append(col_profile)

        # Overall quality score (simple heuristic)
        avg_null = sum(c["null_pct"] for c in columns) / len(columns)
        high_issues = sum(1 for q in quality_issues if q["severity"] == "HIGH")
        quality_score = max(0, round(100 - avg_null - (high_issues * 10)))

        result = {
            "filename":      path.name,
            "total_rows":    total_rows,
            "total_columns": len(columns),
            "columns":       columns,
            "sample_data":   df.head(5).fillna("").to_dict(orient="records"),
            "quality_issues": quality_issues,
            "quality_score": quality_score,
        }

        log.info("Agent 1 done — %d columns | %d issues | quality: %d/100",
                 len(columns), len(quality_issues), quality_score)
        return result

    def format_for_llm(self, profile: dict) -> str:
        """
        Format the schema profile as a readable string
        for the LLM mapper prompt.
        """
        lines = [
            f"SOURCE FILE: {profile['filename']}",
            f"Rows: {profile['total_rows']:,} | Columns: {profile['total_columns']}",
            "",
            "COLUMNS (name | type | pattern | null% | sample values):",
        ]
        for col in profile["columns"]:
            samples_str = ", ".join(str(s) for s in col["samples"][:3])
            lines.append(
                f"  {col['name']:<30} {col['dtype']:<15} "
                f"{col['pattern']:<15} {col['null_pct']}% null | "
                f"e.g. {samples_str}"
            )
        return "\n".join(lines)
