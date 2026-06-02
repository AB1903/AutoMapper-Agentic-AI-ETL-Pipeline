"""
Agent 4 — Anomaly Detector

Statistical data quality analysis using IQR-based outlier
detection, null analysis, duplicate detection, and pattern
validation. Returns a quality score per column and overall.
"""

import logging
from collections import Counter

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Detects data quality issues in a CSV file.
    Runs after Schema Analyzer for richer context.
    """

    def __init__(self, null_threshold: float = 0.05,
                 outlier_threshold: float = 0.01):
        self.null_threshold    = null_threshold     # 5% nulls = flag
        self.outlier_threshold = outlier_threshold  # 1% outliers = flag

    def detect(self, file_path: str, profile: dict) -> dict:
        """
        Full anomaly detection pass on the uploaded file.

        Returns:
            dict with:
              - anomalies:     list of detected issues
              - quality_score: 0-100 overall score
              - column_scores: per-column quality scores
              - duplicates:    duplicate row count
              - recommendations: list of actionable fixes
        """
        log.info("Agent 4 — Running anomaly detection …")

        df = pd.read_csv(file_path)
        anomalies = []
        column_scores = {}
        recommendations = []

        # ── Duplicate detection ────────────────────────────────
        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            anomalies.append({
                "type":     "DUPLICATE_ROWS",
                "column":   "ALL",
                "count":    dup_count,
                "pct":      round(dup_count / len(df) * 100, 1),
                "severity": "HIGH" if dup_count / len(df) > 0.05 else "MEDIUM",
                "fix":      "df.drop_duplicates(inplace=True)"
            })
            recommendations.append(
                f"Remove {dup_count} duplicate rows before loading"
            )

        for col in df.columns:
            series = df[col]
            score  = 100
            col_issues = []

            # ── Null analysis ──────────────────────────────────
            null_pct = series.isnull().mean()
            if null_pct > self.null_threshold:
                severity = "HIGH" if null_pct > 0.3 else "MEDIUM"
                col_issues.append({
                    "type":     "HIGH_NULLS",
                    "column":   col,
                    "count":    int(series.isnull().sum()),
                    "pct":      round(null_pct * 100, 1),
                    "severity": severity,
                    "fix":      f"COALESCE({col}, appropriate_default)"
                })
                score -= min(30, null_pct * 100)

            # ── Numeric outliers (IQR method) ──────────────────
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().sum() > 10:
                q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
                iqr    = q3 - q1
                if iqr > 0:
                    lower = q1 - 3 * iqr
                    upper = q3 + 3 * iqr
                    outliers = ((numeric < lower) | (numeric > upper)).sum()
                    out_pct  = outliers / len(df)

                    if out_pct > self.outlier_threshold:
                        col_issues.append({
                            "type":     "OUTLIERS",
                            "column":   col,
                            "count":    int(outliers),
                            "pct":      round(out_pct * 100, 1),
                            "range":    f"[{round(lower,2)}, {round(upper,2)}]",
                            "severity": "MEDIUM",
                            "fix":      f"Filter: {col} BETWEEN {round(lower,2)} AND {round(upper,2)}"
                        })
                        score -= 10

                # Negative values in amount/price columns
                if numeric.min() < 0:
                    price_keywords = ["price","amount","revenue","cost","value","sale","fee"]
                    if any(kw in col.lower() for kw in price_keywords):
                        neg_count = int((numeric < 0).sum())
                        col_issues.append({
                            "type":     "NEGATIVE_VALUES",
                            "column":   col,
                            "count":    neg_count,
                            "severity": "HIGH",
                            "fix":      f"WHERE {col} >= 0"
                        })
                        score -= 15
                        recommendations.append(
                            f"Column '{col}' has {neg_count} negative values — "
                            "likely data entry errors or refunds needing separate handling"
                        )

            # ── String length anomalies ────────────────────────
            if series.dtype == object:
                str_series = series.dropna().astype(str)
                if len(str_series) > 0:
                    lengths = str_series.str.len()
                    # Truncation risk — very long values
                    max_len = lengths.max()
                    if max_len > 250:
                        col_issues.append({
                            "type":     "LONG_VALUES",
                            "column":   col,
                            "count":    int((lengths > 250).sum()),
                            "max_len":  int(max_len),
                            "severity": "LOW",
                            "fix":      f"LEFT({col}, 255) to prevent truncation"
                        })

                    # Empty strings (different from NULL)
                    empty = (str_series.str.strip() == "").sum()
                    if empty > 0:
                        col_issues.append({
                            "type":     "EMPTY_STRINGS",
                            "column":   col,
                            "count":    int(empty),
                            "severity": "LOW",
                            "fix":      f"NULLIF(TRIM({col}), '')"
                        })

            column_scores[col] = max(0, round(score))
            anomalies.extend(col_issues)

        # Overall quality score
        if column_scores:
            base_score = sum(column_scores.values()) / len(column_scores)
        else:
            base_score = 100

        high_count = sum(1 for a in anomalies if a.get("severity") == "HIGH")
        overall_score = max(0, round(base_score - high_count * 5))

        # Summary recommendations
        if not recommendations:
            recommendations.append("Data looks clean — ready to load")

        result = {
            "anomalies":        anomalies,
            "quality_score":    overall_score,
            "column_scores":    column_scores,
            "duplicate_rows":   dup_count,
            "total_issues":     len(anomalies),
            "high_severity":    high_count,
            "recommendations":  recommendations,
        }

        log.info("Agent 4 done — %d anomalies | %d high severity | score: %d/100",
                 len(anomalies), high_count, overall_score)
        return result
