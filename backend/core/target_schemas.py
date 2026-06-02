"""
Registry of known target schemas AutoMapper can map to.

Each schema defines:
  - Table names
  - Column names + data types
  - Column descriptions (used for LLM context)

Agent 2 (LLM Mapper) uses to understand
what the target system looks like.
"""

# ── Retail DWH Schema (Project 1)
RETAIL_DWH = {
    "name": "retail_dwh",
    "description": "Retail Analytics Data Warehouse — PostgreSQL",
    "tables": {
        "staging.raw_transactions": {
            "description": "Raw transactions from POS and e-commerce systems",
            "columns": {
                "transaction_id":  {"type": "VARCHAR(50)",   "desc": "Unique transaction ID from source system"},
                "customer_id":     {"type": "VARCHAR(50)",   "desc": "Customer identifier — nullable for anonymous"},
                "store_id":        {"type": "VARCHAR(20)",   "desc": "Store or channel identifier"},
                "channel":         {"type": "VARCHAR(20)",   "desc": "in-store or online"},
                "transaction_ts":  {"type": "TIMESTAMP",     "desc": "Transaction datetime"},
                "product_id":      {"type": "VARCHAR(50)",   "desc": "Product identifier"},
                "quantity":        {"type": "INTEGER",       "desc": "Units purchased — must be positive"},
                "unit_price":      {"type": "NUMERIC(10,2)", "desc": "Price per unit in EUR"},
                "discount_pct":    {"type": "NUMERIC(5,2)",  "desc": "Discount percentage 0-100"},
                "payment_method":  {"type": "VARCHAR(30)",   "desc": "Payment type"},
                "source_system":   {"type": "VARCHAR(20)",   "desc": "POS or ECOM"},
            }
        },
        "staging.raw_customers": {
            "description": "Customer records from CRM system",
            "columns": {
                "customer_id":   {"type": "VARCHAR(50)",  "desc": "Unique customer ID"},
                "first_name":    {"type": "VARCHAR(100)", "desc": "Customer first name"},
                "last_name":     {"type": "VARCHAR(100)", "desc": "Customer last name"},
                "email":         {"type": "VARCHAR(255)", "desc": "Email address — must be lowercase"},
                "city":          {"type": "VARCHAR(100)", "desc": "City of residence"},
                "country":       {"type": "VARCHAR(100)", "desc": "Country"},
                "segment":       {"type": "VARCHAR(50)",  "desc": "Gold, Silver, or Bronze"},
                "signup_date":   {"type": "DATE",         "desc": "Date customer first registered"},
            }
        },
        "staging.raw_products": {
            "description": "Product catalogue",
            "columns": {
                "product_id":    {"type": "VARCHAR(50)",   "desc": "Unique product SKU"},
                "product_name":  {"type": "VARCHAR(255)",  "desc": "Full product name"},
                "category_l1":   {"type": "VARCHAR(100)",  "desc": "Top-level category"},
                "category_l2":   {"type": "VARCHAR(100)",  "desc": "Sub-category"},
                "brand":         {"type": "VARCHAR(100)",  "desc": "Brand name"},
                "cost_price":    {"type": "NUMERIC(10,2)", "desc": "Cost to purchase"},
                "list_price":    {"type": "NUMERIC(10,2)", "desc": "Retail selling price"},
                "is_active":     {"type": "BOOLEAN",       "desc": "True if product is currently sold"},
            }
        },
    }
}

# ── Generic Sales Schema 
GENERIC_SALES = {
    "name": "generic_sales",
    "description": "Generic sales data schema for any retail business",
    "tables": {
        "transactions": {
            "description": "Sales transactions",
            "columns": {
                "id":           {"type": "INTEGER",       "desc": "Primary key"},
                "order_date":   {"type": "DATE",          "desc": "Date of purchase"},
                "customer_id":  {"type": "INTEGER",       "desc": "Customer FK"},
                "product_id":   {"type": "INTEGER",       "desc": "Product FK"},
                "quantity":     {"type": "INTEGER",       "desc": "Units sold"},
                "revenue":      {"type": "NUMERIC(12,2)", "desc": "Total revenue"},
            }
        },
        "customers": {
            "description": "Customer master data",
            "columns": {
                "id":         {"type": "INTEGER",      "desc": "Primary key"},
                "name":       {"type": "VARCHAR(200)", "desc": "Full name"},
                "email":      {"type": "VARCHAR(255)", "desc": "Email"},
                "country":    {"type": "VARCHAR(100)", "desc": "Country"},
            }
        }
    }
}

# ── Registry 
SCHEMA_REGISTRY = {
    "retail_dwh":    RETAIL_DWH,
    "generic_sales": GENERIC_SALES,
}


def get_schema(name: str) -> dict:
    """Return a target schema by name."""
    schema = SCHEMA_REGISTRY.get(name)
    if not schema:
        raise ValueError(
            f"Unknown schema '{name}'. "
            f"Available: {list(SCHEMA_REGISTRY.keys())}"
        )
    return schema


def format_schema_for_llm(schema: dict) -> str:
    """
    Format a target schema as a readable string for LLM context.
    This is what Agent 2 sees when generating mappings.
    """
    lines = [
        f"TARGET SCHEMA: {schema['name']}",
        f"Description: {schema['description']}",
        ""
    ]
    for table_name, table_info in schema["tables"].items():
        lines.append(f"TABLE: {table_name}")
        lines.append(f"  {table_info['description']}")
        lines.append("  Columns:")
        for col, info in table_info["columns"].items():
            lines.append(
                f"    {col} ({info['type']}) — {info['desc']}"
            )
        lines.append("")
    return "\n".join(lines)
