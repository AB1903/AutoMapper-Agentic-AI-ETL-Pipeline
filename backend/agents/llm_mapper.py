"""
Agent 2 — LLM Mapper

Uses a local LLM (via Ollama on Mac host) to suggest
column mappings from source → target schema.

The prompt forces the model to ONLY use actual source column
names — prevents hallucination of invented column names.
"""

import json
import logging
import re
from typing import Optional

from backend.core.ollama_client import OllamaClient
from backend.core.target_schemas import format_schema_for_llm, get_schema

log = logging.getLogger(__name__)


# ── System prompt ──────────────────────────────────────────────
SYSTEM_PROMPT = """You are a data engineer doing ETL column mapping.
You MUST respond with valid JSON only. No explanation. No markdown. No extra text.
Only output the JSON object."""


def build_mapping_prompt(source_profile_text: str,
                         target_schema_text: str,
                         source_columns: list) -> str:
    """
    Build a strict mapping prompt that forces the LLM to only
    use the actual source column names provided.
    """
    source_col_list = "\n".join(f"  - {col}" for col in source_columns)
    example_src = source_columns[0] if source_columns else "order_number"

    return f"""You must map SOURCE columns to TARGET columns.

CRITICAL RULES:
1. source_col MUST be one of the SOURCE COLUMNS listed below. Never invent column names.
2. target_col MUST be one of the TARGET COLUMNS listed below. Never invent column names.
3. If no good match exists, set target_col to null.
4. Respond with ONLY the JSON object, nothing else.

SOURCE COLUMNS (you must use EXACTLY these names):
{source_col_list}

{target_schema_text}

Example of correct output format:
{{
  "mappings": [
    {{"source_col": "{example_src}", "target_table": "staging.raw_transactions", "target_col": "transaction_id", "confidence": 0.95, "transform": null, "reasoning": "order number is the transaction id"}},
    {{"source_col": "buyer_id", "target_table": "staging.raw_transactions", "target_col": "customer_id", "confidence": 0.95, "transform": null, "reasoning": "buyer id maps to customer id"}},
    {{"source_col": "qty", "target_table": "staging.raw_transactions", "target_col": "quantity", "confidence": 0.99, "transform": null, "reasoning": "direct quantity match"}},
    {{"source_col": "sale_price", "target_table": "staging.raw_transactions", "target_col": "unit_price", "confidence": 0.92, "transform": null, "reasoning": "sale price is unit price"}},
    {{"source_col": "payment_type", "target_table": "staging.raw_transactions", "target_col": "payment_method", "confidence": 0.95, "transform": null, "reasoning": "payment type maps to payment method"}}
  ],
  "unmapped_columns": ["column_with_no_match"],
  "notes": "mapped all columns"
}}

Now map ALL of these source columns:
{source_col_list}

Respond with ONLY the JSON:"""


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from LLM response — handles extra text around JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    patterns = [
        r'\{[\s\S]*\}',
        r'```json\s*([\s\S]*?)```',
        r'```\s*([\s\S]*?)```',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1) if '```' in pattern else match.group(0)
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue

    log.warning("Could not extract JSON from LLM response: %s", text[:300])
    return {"mappings": [], "unmapped_columns": [], "notes": "Parse failed"}


def validate_source_columns(mappings: list, actual_source_cols: list) -> list:
    """
    Discard any mappings where the LLM hallucinated a source column
    that doesn't exist in the actual CSV.
    """
    valid = []
    actual_set = set(actual_source_cols)

    for m in mappings:
        src = m.get("source_col")
        if src in actual_set:
            valid.append(m)
        else:
            log.warning("LLM hallucinated source column '%s' — discarding", src)

    return valid


class LLMMapper:
    """
    Uses a local LLM via Ollama to generate column mappings.
    Runs on Mac host for GPU acceleration.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.ollama = OllamaClient(config_path)
        self.config_path = config_path

    def map_columns(self,
                    source_profile: dict,
                    target_schema_name: str,
                    source_profile_text: str) -> dict:
        """
        Generate mappings from source columns to target schema.

        Args:
            source_profile:      Full profile from Agent 1
            target_schema_name:  Name of the target schema
            source_profile_text: Formatted text from Agent 1

        Returns:
            dict with mappings, unmapped columns, confidence scores
        """
        # Extract ACTUAL source column names from the real CSV profile
        source_columns = [col["name"] for col in source_profile["columns"]]

        log.info("Agent 2 — Mapping %d columns to '%s' schema",
                 len(source_columns), target_schema_name)
        log.info("Source columns: %s", source_columns)

        # Get target schema
        target_schema = get_schema(target_schema_name)
        target_text   = format_schema_for_llm(target_schema)

        # Build prompt with explicit source column list
        prompt = build_mapping_prompt(
            source_profile_text=source_profile_text,
            target_schema_text=target_text,
            source_columns=source_columns,
        )

        # Call Ollama
        log.info("Calling LLM via Ollama …")
        raw_response = self.ollama.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.1,
        )
        log.info("RAW LLM RESPONSE: %s", raw_response[:500])

        # Parse response
        result = extract_json_from_response(raw_response)

        # ── Validate: discard hallucinated source columns ──────
        mappings = result.get("mappings", [])
        mappings = validate_source_columns(mappings, source_columns)

        # Enrich with status labels based on confidence
        for m in mappings:
            conf = m.get("confidence", 0)
            if conf >= 0.90:
                m["status"] = "AUTO_APPROVED"
                m["status_label"] = "✅ Auto-approved"
            elif conf >= 0.60:
                m["status"] = "NEEDS_REVIEW"
                m["status_label"] = "⚠️ Needs review"
            else:
                m["status"] = "MANUAL_REQUIRED"
                m["status_label"] = "❌ Manual mapping required"

        # Compute truly unmapped columns
        mapped_sources = {m["source_col"] for m in mappings}
        truly_unmapped = [c for c in source_columns if c not in mapped_sources]

        result["mappings"]         = mappings
        result["unmapped_columns"] = truly_unmapped
        result["total_mapped"]     = len(mappings)
        result["total_unmapped"]   = len(truly_unmapped)
        result["auto_approved"]    = sum(1 for m in mappings
                                         if m.get("status") == "AUTO_APPROVED")

        log.info("Agent 2 done — %d mapped | %d unmapped | %d auto-approved",
                 result["total_mapped"],
                 result["total_unmapped"],
                 result["auto_approved"])

        return result
