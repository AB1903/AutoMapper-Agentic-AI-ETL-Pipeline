"""
Generates realistic sample CSV files for testing AutoMapper.
Creates files that intentionally have mixed column names,
type mismatches, and data quality issues — to demonstrate
all 5 agents working.
"""

import random
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT = Path("data/sample")
OUT.mkdir(parents=True, exist_ok=True)


def gen_ecommerce_orders(n: int = 500) -> pd.DataFrame:
    """
    Simulates an e-commerce order export with:
    - Slightly different column names than target schema
    - Mixed date formats
    - Some negative prices (anomaly)
    - 5% null customer IDs
    """
    channels = ["web", "mobile", "app", "instagram", "google"]
    methods  = ["credit_card", "paypal", "klarna", "apple_pay", "sepa"]
    products = [f"SKU{i:04d}" for i in range(1, 100)]
    stores   = ["DE_ONLINE", "AT_ONLINE", "CH_ONLINE"]

    rows = []
    for i in range(1, n + 1):
        # Intentional anomaly: 3% negative prices
        price = round(random.uniform(5, 500), 2)
        if random.random() < 0.03:
            price = -price

        rows.append({
            # Column names differ from target — AutoMapper must figure it out
            "order_number":    f"ORD{i:07d}",
            "buyer_id":        None if random.random() < 0.05
                               else f"C{random.randint(1,5000):06d}",
            "shop_id":         random.choice(stores),
            "sale_channel":    random.choice(channels),
            "order_datetime":  pd.Timestamp("2024-01-01") +
                               pd.Timedelta(hours=random.randint(0, 8760)),
            "sku":             random.choice(products),
            "qty":             random.randint(1, 5),
            "sale_price":      price,
            "discount":        random.choice([0, 5, 10, 15, 20]),
            "payment_type":    random.choice(methods),
        })

    df = pd.DataFrame(rows)
    path = OUT / "ecommerce_orders.csv"
    df.to_csv(path, index=False)
    print(f"✅  ecommerce_orders.csv — {len(df)} rows")
    return df


def gen_crm_customers(n: int = 300) -> pd.DataFrame:
    """
    Simulates a CRM customer export with:
    - Different naming conventions
    - Mixed case emails
    - Some missing cities
    """
    cities   = ["Berlin", "Munich", "Hamburg", "Frankfurt",
                "Cologne", "Stuttgart", "Vienna", "Zurich"]
    countries = ["Germany"] * 6 + ["Austria", "Switzerland"]
    segments  = ["premium", "standard", "basic"]  # different values than target

    rows = []
    for i in range(1, n + 1):
        idx = random.randint(0, len(cities) - 1)
        rows.append({
            "client_id":      f"C{i:06d}",
            "given_name":     random.choice(["Anna","Lukas","Sophie","Felix",
                                             "Emma","Max","Lena","Paul"]),
            "family_name":    random.choice(["Müller","Schmidt","Fischer","Weber"]),
            # Mixed case emails — needs LOWER() transform
            "email_address":  f"USER{i}@EXAMPLE.COM",
            "home_city":      cities[idx] if random.random() > 0.1 else None,
            "home_country":   countries[idx],
            # Different segment naming — needs mapping
            "tier":           random.choice(segments),
            "registration_date": (pd.Timestamp("2020-01-01") +
                                  pd.Timedelta(days=random.randint(0,1500))
                                 ).strftime("%d/%m/%Y"),  # different date format!
        })

    df = pd.DataFrame(rows)
    path = OUT / "crm_customers.csv"
    df.to_csv(path, index=False)
    print(f"✅  crm_customers.csv — {len(df)} rows")
    return df


def gen_product_catalog(n: int = 200) -> pd.DataFrame:
    """
    Product catalogue export with price in wrong format.
    """
    cats = {
        "Electronics": ["Smartphones", "Laptops", "Headphones"],
        "Clothing":    ["Shirts", "Trousers", "Shoes"],
        "Sports":      ["Gym Equipment", "Cycling", "Swimwear"],
    }
    brands = ["ZenTech", "NordStyle", "AlphaGear", "PureHome"]

    rows = []
    for i in range(1, n + 1):
        cat1 = random.choice(list(cats.keys()))
        cat2 = random.choice(cats[cat1])
        cost = round(random.uniform(5, 300), 2)
        rows.append({
            "product_code":  f"P{i:05d}",
            "item_name":     f"{random.choice(brands)} {cat2} {random.randint(100,999)}",
            "main_category": cat1,
            "sub_category":  cat2,
            "brand_name":    random.choice(brands),
            # Price stored as string with currency symbol — needs cleaning
            "purchase_cost": f"€{cost}",
            "retail_price":  f"€{round(cost * random.uniform(1.4, 3.0), 2)}",
            "available":     random.choice(["Yes", "No", "yes", "no"]),  # inconsistent booleans
        })

    df = pd.DataFrame(rows)
    path = OUT / "product_catalog.csv"
    df.to_csv(path, index=False)
    print(f"✅  product_catalog.csv — {len(df)} rows")
    return df


if __name__ == "__main__":
    print("Generating sample CSV files …\n")
    gen_ecommerce_orders()
    gen_crm_customers()
    gen_product_catalog()
    print(f"\n🎉  All sample files written to {OUT}")
    print("\nTest AutoMapper with:")
    print("  curl -X POST http://localhost:8003/map \\")
    print("    -F 'file=@data/sample/ecommerce_orders.csv' \\")
    print("    -F 'target_schema=retail_dwh' \\")
    print("    -F 'target_table=staging.raw_transactions'")
