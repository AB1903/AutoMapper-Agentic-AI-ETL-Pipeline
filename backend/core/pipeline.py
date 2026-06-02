"""
Main pipeline orchestrator — runs all 5 agents in sequence
and returns the complete AutoMapper result.

Flow:
  1. Schema Analyzer  → profiles source file
  2. LLM Mapper       → suggests column mappings
  3. Type Validator   → validates types, adds transforms
  4. Anomaly Detector → finds data quality issues
  5. Code Generator   → produces executable ETL script
"""

import logging
import time
from pathlib import Path

from backend.agents.anomaly_detector import AnomalyDetector
from backend.agents.code_generator import CodeGenerator
from backend.agents.llm_mapper import LLMMapper
from backend.agents.schema_analyzer import SchemaAnalyzer
from backend.agents.type_validator import TypeValidator
from backend.core.target_schemas import get_schema

log = logging.getLogger(__name__)


class AutoMapperPipeline:
    """
    Orchestrates all 5 agents to produce a complete
    mapping report and ETL script for a given source file.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.analyzer   = SchemaAnalyzer(config_path)
        self.mapper     = LLMMapper(config_path)
        self.validator  = TypeValidator()
        self.detector   = AnomalyDetector()
        self.generator  = CodeGenerator()

    def run(self, file_path: str,
            target_schema_name: str = "retail_dwh",
            target_table: str = "staging.raw_transactions") -> dict:
        """
        Run the full AutoMapper pipeline on a source file.

        Args:
            file_path:          Path to uploaded CSV
            target_schema_name: Which target schema to map to
            target_table:       Specific table within the schema

        Returns:
            Complete result dict with all agent outputs
        """
        start = time.time()
        log.info("═══ AutoMapper Pipeline starting ═══")
        log.info("Source: %s | Target: %s.%s",
                 file_path, target_schema_name, target_table)

        result = {
            "source_file":      Path(file_path).name,
            "target_schema":    target_schema_name,
            "target_table":     target_table,
            "pipeline_stages":  {},
        }

        # ── Agent 1 — Schema Analyzer ──────────────────────────
        log.info("--- Stage 1: Schema Analysis ---")
        t1 = time.time()
        profile          = self.analyzer.analyze(file_path)
        profile_text     = self.analyzer.format_for_llm(profile)
        result["profile"] = profile
        result["pipeline_stages"]["schema_analyzer"] = {
            "status":   "done",
            "duration": round(time.time() - t1, 2),
            "columns":  profile["total_columns"],
        }

        # ── Agent 2 — LLM Mapper ───────────────────────────────
        log.info("--- Stage 2: LLM Mapping (CodeLlama) ---")
        t2 = time.time()
        mapping_result = self.mapper.map_columns(
            source_profile=profile,
            target_schema_name=target_schema_name,
            source_profile_text=profile_text,
        )
        result["pipeline_stages"]["llm_mapper"] = {
            "status":      "done",
            "duration":    round(time.time() - t2, 2),
            "mapped":      mapping_result["total_mapped"],
            "unmapped":    mapping_result["total_unmapped"],
            "auto_approved": mapping_result["auto_approved"],
        }

        # ── Agent 3 — Type Validator ───────────────────────────
        log.info("--- Stage 3: Type Validation ---")
        t3 = time.time()
        target_schema    = get_schema(target_schema_name)
        validated_mappings = self.validator.validate(
            mappings=mapping_result["mappings"],
            source_profile=profile,
            target_schema=target_schema,
        )
        result["mappings"] = validated_mappings
        result["unmapped_columns"] = mapping_result.get("unmapped_columns", [])
        result["mapping_notes"]    = mapping_result.get("notes", "")
        result["pipeline_stages"]["type_validator"] = {
            "status":   "done",
            "duration": round(time.time() - t3, 2),
        }

        # ── Agent 4 — Anomaly Detector ─────────────────────────
        log.info("--- Stage 4: Anomaly Detection ---")
        t4 = time.time()
        anomaly_result = self.detector.detect(file_path, profile)
        result["anomalies"]      = anomaly_result["anomalies"]
        result["quality_score"]  = anomaly_result["quality_score"]
        result["column_scores"]  = anomaly_result["column_scores"]
        result["recommendations"] = anomaly_result["recommendations"]
        result["pipeline_stages"]["anomaly_detector"] = {
            "status":       "done",
            "duration":     round(time.time() - t4, 2),
            "issues_found": anomaly_result["total_issues"],
            "quality_score": anomaly_result["quality_score"],
        }

        # ── Agent 5 — Code Generator ───────────────────────────
        log.info("--- Stage 5: ETL Code Generation ---")
        t5 = time.time()
        etl_code = self.generator.generate(
            source_filename=Path(file_path).name,
            target_schema_name=target_schema_name,
            target_table=target_table,
            mappings=validated_mappings,
            anomalies=anomaly_result["anomalies"],
        )
        result["generated_code"] = etl_code
        result["pipeline_stages"]["code_generator"] = {
            "status":   "done",
            "duration": round(time.time() - t5, 2),
            "lines":    len(etl_code.split("\n")),
        }

        # ── Summary ────────────────────────────────────────────
        total_time = round(time.time() - start, 2)
        auto  = sum(1 for m in validated_mappings if m.get("status") == "AUTO_APPROVED")
        review = sum(1 for m in validated_mappings if m.get("status") == "NEEDS_REVIEW")
        manual = sum(1 for m in validated_mappings if m.get("status") == "MANUAL_REQUIRED")

        result["summary"] = {
            "total_columns":   profile["total_columns"],
            "auto_approved":   auto,
            "needs_review":    review,
            "manual_required": manual,
            "quality_score":   anomaly_result["quality_score"],
            "total_issues":    anomaly_result["total_issues"],
            "pipeline_time_s": total_time,
        }

        log.info("═══ Pipeline complete in %.1fs ═══", total_time)
        log.info("    Auto: %d | Review: %d | Manual: %d | Quality: %d/100",
                 auto, review, manual, anomaly_result["quality_score"])

        return result
