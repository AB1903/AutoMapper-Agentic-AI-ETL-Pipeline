-- ─────────────────────────────────────────────────────────────
-- AutoMapper — PostgreSQL DWH Initialisation
-- Runs automatically on first docker-compose up
-- Creates the staging + core schemas for the Retail DWH
-- ─────────────────────────────────────────────────────────────

-- Create schemas
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;

-- ── Staging Layer ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS staging.raw_transactions (
    transaction_id  VARCHAR(50),
    customer_id     VARCHAR(50),
    store_id        VARCHAR(20),
    channel         VARCHAR(20),
    transaction_ts  TIMESTAMP,
    product_id      VARCHAR(50),
    quantity        INTEGER,
    unit_price      NUMERIC(10,2),
    discount_pct    NUMERIC(5,2),
    payment_method  VARCHAR(30),
    source_system   VARCHAR(20),
    _loaded_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.raw_customers (
    customer_id   VARCHAR(50),
    first_name    VARCHAR(100),
    last_name     VARCHAR(100),
    email         VARCHAR(255),
    city          VARCHAR(100),
    country       VARCHAR(100),
    segment       VARCHAR(50),
    signup_date   DATE,
    _loaded_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.raw_products (
    product_id    VARCHAR(50),
    product_name  VARCHAR(255),
    category_l1   VARCHAR(100),
    category_l2   VARCHAR(100),
    brand         VARCHAR(100),
    cost_price    NUMERIC(10,2),
    list_price    NUMERIC(10,2),
    is_active     BOOLEAN,
    _loaded_at    TIMESTAMP DEFAULT NOW()
);

-- ── Core Layer (Dimensional Model) ───────────────────────────

CREATE TABLE IF NOT EXISTS core.dim_customer (
    customer_sk   SERIAL PRIMARY KEY,
    customer_id   VARCHAR(50) UNIQUE NOT NULL,
    first_name    VARCHAR(100),
    last_name     VARCHAR(100),
    email         VARCHAR(255),
    city          VARCHAR(100),
    country       VARCHAR(100),
    segment       VARCHAR(50),
    signup_date   DATE,
    valid_from    TIMESTAMP DEFAULT NOW(),
    valid_to      TIMESTAMP,
    is_current    BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS core.dim_product (
    product_sk    SERIAL PRIMARY KEY,
    product_id    VARCHAR(50) UNIQUE NOT NULL,
    product_name  VARCHAR(255),
    category_l1   VARCHAR(100),
    category_l2   VARCHAR(100),
    brand         VARCHAR(100),
    cost_price    NUMERIC(10,2),
    list_price    NUMERIC(10,2),
    is_active     BOOLEAN,
    valid_from    TIMESTAMP DEFAULT NOW(),
    valid_to      TIMESTAMP,
    is_current    BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS core.fact_transactions (
    transaction_sk  SERIAL PRIMARY KEY,
    transaction_id  VARCHAR(50) UNIQUE NOT NULL,
    customer_sk     INTEGER REFERENCES core.dim_customer(customer_sk),
    product_sk      INTEGER REFERENCES core.dim_product(product_sk),
    store_id        VARCHAR(20),
    channel         VARCHAR(20),
    transaction_ts  TIMESTAMP,
    quantity        INTEGER,
    unit_price      NUMERIC(10,2),
    discount_pct    NUMERIC(5,2),
    gross_revenue   NUMERIC(12,2),
    net_revenue     NUMERIC(12,2),
    payment_method  VARCHAR(30),
    source_system   VARCHAR(20),
    _loaded_at      TIMESTAMP DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_raw_tx_customer ON staging.raw_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_raw_tx_product  ON staging.raw_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_raw_tx_ts       ON staging.raw_transactions(transaction_ts);
CREATE INDEX IF NOT EXISTS idx_fact_tx_ts      ON core.fact_transactions(transaction_ts);
CREATE INDEX IF NOT EXISTS idx_fact_customer   ON core.fact_transactions(customer_sk);

-- Done
DO $$ BEGIN
    RAISE NOTICE 'AutoMapper DWH schema initialised successfully';
END $$;
