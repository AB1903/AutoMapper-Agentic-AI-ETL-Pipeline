"""
Agent 5 — ETL Code Generator

Generates a complete, executable Python ETL script based on:
  - Validated column mappings (Agent 2 + 3)
  - Anomaly fixes (Agent 4)
  - Target schema definitions

Output is a ready-to-run Python file that:
  - Reads the source CSV
  - Applies all transformations
  - Cleans anomalies
  - Loads into the target PostgreSQL table

Uses LLM for complex transformation logic, rule-based for simple ones.
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)


def generate_transform_line(mapping: dict) -> str:
    """Generate a single pandas transformation line for a mapping."""
    src   = mapping.get("source_col")
    tgt   = mapping.get("target_col")
    trans = mapping.get("transform")

    if not tgt or not src:
        return f"    # SKIPPED: {src} — no target mapping"

    if not trans:
        return f'    df["{tgt}"] = df["{src}"]'

    # Convert SQL-style transforms to pandas
    trans_lower = trans.lower()

    if "lower(" in trans_lower and "trim(" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].str.lower().str.strip()'
    elif "lower(" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].str.lower()'
    elif "trim(" in trans_lower or "strip(" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].str.strip()'
    elif "upper(" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].str.upper()'
    elif "cast" in trans_lower and "integer" in trans_lower:
        return f'    df["{tgt}"] = pd.to_numeric(df["{src}"], errors="coerce").astype("Int64")'
    elif "cast" in trans_lower and "numeric" in trans_lower:
        return f'    df["{tgt}"] = pd.to_numeric(df["{src}"], errors="coerce")'
    elif "cast" in trans_lower and "varchar" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].astype(str)'
    elif "date(" in trans_lower or "timestamp" in trans_lower:
        return f'    df["{tgt}"] = pd.to_datetime(df["{src}"], errors="coerce")'
    elif "coalesce" in trans_lower:
        return f'    df["{tgt}"] = df["{src}"].fillna("")'
    else:
        # Keep as comment for manual handling
        return (f'    # MANUAL: {src} → {tgt}\n'
                f'    # Transform: {trans}\n'
                f'    df["{tgt}"] = df["{src}"]  # TODO: implement transform')


def generate_anomaly_fix(anomaly: dict) -> str:
    """Generate pandas code to fix a detected anomaly."""
    col      = anomaly.get("column")
    issue    = anomaly.get("type")
    severity = anomaly.get("severity", "LOW")

    if col == "ALL" and issue == "DUPLICATE_ROWS":
        return "    df = df.drop_duplicates()\n    print(f'Removed duplicates — {len(df)} rows remain')"

    if issue == "HIGH_NULLS":
        return f'    df["{col}"] = df["{col}"].fillna("")  # {severity}: {anomaly.get("pct")}% nulls'

    if issue == "NEGATIVE_VALUES":
        return f'    df = df[df["{col}"] >= 0]  # {severity}: removed negative values'

    if issue == "EMPTY_STRINGS":
        return f'    df["{col}"] = df["{col}"].replace("", None)  # convert empty strings to NULL'

    return f'    # TODO fix {issue} in column {col}'


class CodeGenerator:
    """
    Generates a complete executable Python ETL script
    from the validated mappings and anomaly report.
    """

    def generate(self,
                 source_filename: str,
                 target_schema_name: str,
                 target_table: str,
                 mappings: list,
                 anomalies: list,
                 db_connection_string: str = None) -> str:
        """
        Generate complete ETL Python script.

        Returns:
            String containing the complete Python ETL script
        """
        log.info("Agent 5 — Generating ETL code for %s → %s",
                 source_filename, target_table)

        ts  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        conn = db_connection_string or "postgresql://dwh_user:dwh_pass@localhost:5432/retail_dwh"

        # Filter valid mappings only
        valid_mappings = [
            m for m in mappings
            if m.get("target_col") and m.get("status") != "MANUAL_REQUIRED"
        ]
        manual_mappings = [
            m for m in mappings
            if m.get("status") == "MANUAL_REQUIRED"
        ]

        # Generate transform lines
        transform_lines = "\n".join(
            generate_transform_line(m) for m in valid_mappings
        )

        # Generate anomaly fix lines
        high_anomalies = [a for a in anomalies if a.get("severity") == "HIGH"]
        anomaly_lines  = "\n".join(
            generate_anomaly_fix(a) for a in high_anomalies
        )

        # Generate final column select
        target_cols = [
            f'"{m["target_col"]}"'
            for m in valid_mappings
            if m.get("target_col")
        ]
        cols_str = ",\n        ".join(target_cols)

        # Manual mapping comments
        manual_comments = "\n".join(
            f'#   {m["source_col"]} → ??? (confidence: {m.get("confidence", 0):.2f})'
            for m in manual_mappings
        )

        script = f'''#!/usr/bin/env python3
"""
AutoMapper Generated ETL Script
================================
Generated:     {ts}
Source file:   {source_filename}
Target schema: {target_schema_name}
Target table:  {target_table}

Auto-mapped columns: {len(valid_mappings)}
Manual review needed: {len(manual_mappings)}

DO NOT EDIT the auto-generated sections without re-running AutoMapper.
"""

import sys
import logging
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────
SOURCE_FILE = "{source_filename}"
TARGET_TABLE = "{target_table}"
DB_URL = "{conn}"
BATCH_SIZE = 5000


# ── Manual mappings needed (review required) ────────────────────
# The following columns could not be automatically mapped:
{manual_comments if manual_comments else "# None — all columns mapped!"}


def extract(file_path: str) -> pd.DataFrame:
    """Load source CSV file."""
    log.info("Loading %s ...", file_path)
    df = pd.read_csv(file_path)
    log.info("Loaded %d rows x %d columns", len(df), len(df.columns))
    return df


def clean_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Fix detected data quality issues."""
    log.info("Cleaning anomalies ...")
    initial_rows = len(df)

{anomaly_lines if anomaly_lines else "    pass  # No high-severity anomalies detected"}

    log.info("Cleaning complete — %d rows remain (removed %d)",
             len(df), initial_rows - len(df))
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Apply column mappings and type transformations."""
    log.info("Applying transformations ...")
    df_out = pd.DataFrame()

{transform_lines}

    # Select only mapped target columns
    target_cols = [
        {cols_str}
    ]
    available = [c for c in target_cols if c in df_out.columns]
    df_out = df_out[available]

    log.info("Transformation complete — %d columns ready", len(df_out.columns))
    return df_out


def load(df: pd.DataFrame, db_url: str, table: str):
    """Load transformed data into target PostgreSQL table."""
    log.info("Loading %d rows into %s ...", len(df), table)

    engine = create_engine(db_url)
    schema, tbl = table.split(".") if "." in table else (None, table)

    total = 0
    with engine.begin() as conn:
        for i in range(0, len(df), BATCH_SIZE):
            chunk = df.iloc[i:i + BATCH_SIZE]
            chunk.to_sql(
                tbl,
                con=conn,
                schema=schema,
                if_exists="append",
                index=False,
                method="multi"
            )
            total += len(chunk)
            log.info("  ... %d rows loaded", total)

    log.info("Load complete — %d total rows", total)


def run():
    """Main ETL pipeline."""
    log.info("=== AutoMapper ETL starting ===")

    # Extract
    df_raw = extract(SOURCE_FILE)

    # Clean
    df_clean = clean_anomalies(df_raw)

    # Transform
    df_final = transform(df_clean)

    # Load
    load(df_final, DB_URL, TARGET_TABLE)

    log.info("=== ETL complete ===")


if __name__ == "__main__":
    run()
'''
        log.info("Agent 5 done — generated %d lines of ETL code",
                 len(script.split("\n")))
        return script
