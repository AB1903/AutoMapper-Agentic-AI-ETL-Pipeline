"""
Agent 3 — Type Validator

Validates that the data types of source columns are compatible
with their mapped target columns. Suggests SQL transformation
expressions where type conversion is needed.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Type compatibility rules ───────────────────────────────────
# Maps (source_type, target_type) → transformation or None
TYPE_RULES = {
    # Direct compatible mappings
    ("INTEGER",        "INTEGER"):        None,
    ("INTEGER",        "NUMERIC"):        None,
    ("INTEGER",        "VARCHAR"):        "CAST({col} AS VARCHAR)",
    ("NUMERIC",        "NUMERIC"):        None,
    ("NUMERIC",        "INTEGER"):        "ROUND({col})::INTEGER",
    ("NUMERIC",        "VARCHAR"):        "CAST({col} AS VARCHAR)",
    ("VARCHAR",        "VARCHAR"):        None,
    ("VARCHAR",        "INTEGER"):        "CAST({col} AS INTEGER)",
    ("VARCHAR",        "NUMERIC"):        "CAST({col} AS NUMERIC)",
    ("VARCHAR",        "BOOLEAN"):        "CASE WHEN LOWER({col}) IN ('true','yes','1') THEN TRUE ELSE FALSE END",
    ("DATE/TIMESTAMP", "DATE"):           "DATE({col})",
    ("DATE/TIMESTAMP", "TIMESTAMP"):      "CAST({col} AS TIMESTAMP)",
    ("DATE/TIMESTAMP", "VARCHAR"):        "TO_CHAR({col}, 'YYYY-MM-DD')",
    ("BOOLEAN",        "BOOLEAN"):        None,
    ("BOOLEAN",        "INTEGER"):        "CASE WHEN {col} THEN 1 ELSE 0 END",
    ("BOOLEAN",        "VARCHAR"):        "CAST({col} AS VARCHAR)",
}

# Types that need special handling
INCOMPATIBLE_PAIRS = {
    ("INTEGER",  "DATE"),
    ("NUMERIC",  "DATE"),
    ("BOOLEAN",  "DATE"),
    ("BOOLEAN",  "NUMERIC"),
}


def get_transform(source_type: str, target_type: str,
                  col_name: str) -> tuple[Optional[str], str]:
    """
    Returns (transform_sql, compatibility_status).
    transform_sql: None = direct, str = conversion needed
    status: COMPATIBLE / TRANSFORM_NEEDED / INCOMPATIBLE
    """
    key = (source_type.upper(), target_type.upper())

    if key in INCOMPATIBLE_PAIRS:
        return None, "INCOMPATIBLE"

    transform = TYPE_RULES.get(key)

    if transform is None and key[0] != key[1]:
        # Unknown combination — flag for review
        return None, "UNKNOWN"

    if transform:
        transform = transform.replace("{col}", col_name)
        return transform, "TRANSFORM_NEEDED"

    return None, "COMPATIBLE"


class TypeValidator:
    """
    Validates type compatibility for each mapped column pair.
    Enhances LLM mapper results with concrete transformation SQL.
    """

    def validate(self, mappings: list,
                 source_profile: dict,
                 target_schema: dict) -> list:
        """
        For each mapping, validate type compatibility and
        add or refine the transformation suggestion.

        Args:
            mappings:       Output from Agent 2 (LLM Mapper)
            source_profile: Output from Agent 1 (Schema Analyzer)
            target_schema:  Target schema dict

        Returns:
            Enhanced mappings with type_status and validated transforms
        """
        log.info("Agent 3 — Validating types for %d mappings", len(mappings))

        # Build lookup: source column name → type
        source_types = {
            col["name"]: col["dtype"]
            for col in source_profile["columns"]
        }

        # Build lookup: target (table, column) → type
        target_types = {}
        for table_name, table_info in target_schema.get("tables", {}).items():
            for col_name, col_info in table_info["columns"].items():
                target_types[(table_name, col_name)] = col_info["type"]

        validated = []
        for mapping in mappings:
            m = dict(mapping)  # copy

            source_col  = m.get("source_col")
            target_col  = m.get("target_col")
            target_table = m.get("target_table")

            if not target_col:
                m["type_status"] = "SKIPPED"
                validated.append(m)
                continue

            source_type = source_types.get(source_col, "VARCHAR")

            # Get target type — try exact match first, then column name only
            target_type = target_types.get((target_table, target_col))
            if not target_type:
                # Fallback: search by column name across all tables
                for (tbl, col), dtype in target_types.items():
                    if col == target_col:
                        target_type = dtype
                        break
            if not target_type:
                target_type = "VARCHAR"  # safe default

            # Normalise target type for comparison
            norm_target = (target_type.upper()
                          .split("(")[0]
                          .replace("NUMERIC", "NUMERIC")
                          .replace("TEXT", "VARCHAR")
                          .replace("BIGINT", "INTEGER")
                          .replace("SMALLINT", "INTEGER"))

            transform, status = get_transform(source_type, norm_target, source_col)

            m["source_type"]    = source_type
            m["target_type"]    = target_type
            m["type_status"]    = status

            # Only override LLM transform if we have a better rule-based one
            if transform and not m.get("transform"):
                m["transform"] = transform

            # Add type warning if needed
            if status == "INCOMPATIBLE":
                m["type_warning"] = (
                    f"⚠️ {source_type} cannot be directly cast to {target_type}. "
                    "Manual transformation required."
                )
                m["status"] = "MANUAL_REQUIRED"
            elif status == "TRANSFORM_NEEDED":
                m["type_warning"] = (
                    f"Type cast needed: {source_type} → {target_type}"
                )

            validated.append(m)

        compatible    = sum(1 for m in validated if m.get("type_status") == "COMPATIBLE")
        transform_needed = sum(1 for m in validated if m.get("type_status") == "TRANSFORM_NEEDED")
        incompatible  = sum(1 for m in validated if m.get("type_status") == "INCOMPATIBLE")

        log.info("Agent 3 done — compatible: %d | transform: %d | incompatible: %d",
                 compatible, transform_needed, incompatible)

        return validated
