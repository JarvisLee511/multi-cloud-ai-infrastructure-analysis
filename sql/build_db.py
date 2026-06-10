"""Build cloud_market.db — a SQLite star schema over the project's datasets.

Dimensions: dim_provider, dim_region (geo-enriched), dim_gpu (vendor-tagged).
Facts: fact_gpu_price (weekly tracker snapshots), and — once the market-history
CSVs exist in data/market_history/ — fact_quarterly_financials, fact_market_share.

Usage:  py sql/build_db.py        (writes data/cloud_market.db)
Query:  see sql/analysis_queries.sql
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "data" / "cloud_market.db"
PRICE_CSV = REPO / "data" / "gpu_price_history.csv"
GEO_CSV = REPO / "pricing_tracker" / "region_geo.csv"
MARKET_DIR = REPO / "data" / "market_history"

GPU_VENDOR = {
    "GB200": "NVIDIA", "B300": "NVIDIA", "B200": "NVIDIA", "H200": "NVIDIA",
    "H100": "NVIDIA", "A100": "NVIDIA", "A100-80GB": "NVIDIA", "L40S": "NVIDIA",
    "L4": "NVIDIA", "A10": "NVIDIA", "A10G": "NVIDIA", "T4": "NVIDIA",
    "T4G": "NVIDIA", "V100": "NVIDIA", "P100": "NVIDIA", "P40": "NVIDIA",
    "P4": "NVIDIA", "K80": "NVIDIA", "K520": "NVIDIA", "M60": "NVIDIA",
    "NVIDIA GB202": "NVIDIA", "NVIDIA B300": "NVIDIA",
    "MI300X": "AMD", "MI300A": "AMD", "MI25": "AMD", "V620": "AMD", "V520": "AMD",
    "Gaudi": "Intel (Habana)", "AWS Inferentia": "AWS", "AWS Inferentia2": "AWS",
    "Qualcomm AI 100 Accelerators": "Qualcomm",
}

DDL = """
DROP TABLE IF EXISTS fact_gpu_price;
DROP TABLE IF EXISTS fact_quarterly_financials;
DROP TABLE IF EXISTS fact_market_share;
DROP TABLE IF EXISTS dim_region;
DROP TABLE IF EXISTS dim_gpu;
DROP TABLE IF EXISTS dim_provider;

CREATE TABLE dim_provider (
    provider_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_region (
    region_id   INTEGER PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES dim_provider(provider_id),
    region_code TEXT NOT NULL,
    city        TEXT,
    country     TEXT,
    continent   TEXT,
    lat         REAL,
    lon         REAL,
    UNIQUE (provider_id, region_code)
);

CREATE TABLE dim_gpu (
    gpu_id INTEGER PRIMARY KEY,
    model  TEXT NOT NULL UNIQUE,
    vendor TEXT
);

CREATE TABLE fact_gpu_price (
    price_id               INTEGER PRIMARY KEY,
    snapshot_date          TEXT NOT NULL,
    region_id              INTEGER NOT NULL REFERENCES dim_region(region_id),
    gpu_id                 INTEGER NOT NULL REFERENCES dim_gpu(gpu_id),
    sku                    TEXT NOT NULL,
    price_type             TEXT NOT NULL CHECK (price_type IN ('ondemand','spot')),
    gpu_count              REAL,
    price_usd_hour         REAL NOT NULL,
    price_usd_per_gpu_hour REAL
);
CREATE INDEX idx_price_date  ON fact_gpu_price(snapshot_date);
CREATE INDEX idx_price_gpu   ON fact_gpu_price(gpu_id, price_type);
CREATE INDEX idx_price_region ON fact_gpu_price(region_id);

CREATE TABLE fact_quarterly_financials (
    quarter               TEXT NOT NULL,           -- e.g. 2024Q3 (calendar)
    provider_id           INTEGER NOT NULL REFERENCES dim_provider(provider_id),
    revenue_musd          REAL,
    operating_income_musd REAL,
    note                  TEXT,
    source_url            TEXT,
    PRIMARY KEY (quarter, provider_id)
);

CREATE TABLE fact_market_share (
    quarter          TEXT NOT NULL,
    firm             TEXT NOT NULL,                -- Synergy | Canalys
    provider_id      INTEGER NOT NULL REFERENCES dim_provider(provider_id),
    share_pct        REAL,
    market_size_busd REAL,
    source_url       TEXT,
    PRIMARY KEY (quarter, firm, provider_id)
);
"""


def build() -> None:
    prices = pd.read_csv(PRICE_CSV)
    geo = pd.read_csv(GEO_CSV)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)

    providers = sorted(prices["provider"].unique())
    con.executemany("INSERT INTO dim_provider(name) VALUES (?)",
                    [(p,) for p in providers])
    pid = {name: i for i, (name,) in enumerate(
        con.execute("SELECT name FROM dim_provider ORDER BY provider_id"), start=1)}

    regions = (prices[["provider", "region"]].drop_duplicates()
               .merge(geo, on=["provider", "region"], how="left"))
    con.executemany(
        "INSERT INTO dim_region(provider_id, region_code, city, country, continent, lat, lon)"
        " VALUES (?,?,?,?,?,?,?)",
        [(pid[r.provider], r.region,
          None if pd.isna(r.city) else r.city,
          None if pd.isna(r.country) else r.country,
          None if pd.isna(r.continent) else r.continent,
          None if pd.isna(r.lat) else r.lat,
          None if pd.isna(r.lon) else r.lon)
         for r in regions.itertuples()])
    rid = {(prov, code): i for i, prov, code in con.execute(
        "SELECT region_id, p.name, region_code FROM dim_region r"
        " JOIN dim_provider p USING(provider_id)")}

    gpus = sorted(prices["gpu_model"].unique())
    con.executemany("INSERT INTO dim_gpu(model, vendor) VALUES (?,?)",
                    [(g, GPU_VENDOR.get(g, "unknown")) for g in gpus])
    gid = {model: i for i, model in con.execute("SELECT gpu_id, model FROM dim_gpu")}

    con.executemany(
        "INSERT INTO fact_gpu_price(snapshot_date, region_id, gpu_id, sku, price_type,"
        " gpu_count, price_usd_hour, price_usd_per_gpu_hour) VALUES (?,?,?,?,?,?,?,?)",
        [(r.snapshot_date, rid[(r.provider, r.region)], gid[r.gpu_model], r.sku,
          r.price_type,
          None if pd.isna(r.gpu_count) else r.gpu_count,
          r.price_usd_hour,
          None if pd.isna(r.price_usd_per_gpu_hour) else r.price_usd_per_gpu_hour)
         for r in prices.itertuples()])

    fin_csv = MARKET_DIR / "quarterly_financials.csv"
    if fin_csv.exists():
        fin = pd.read_csv(fin_csv)
        con.executemany(
            "INSERT OR REPLACE INTO fact_quarterly_financials VALUES (?,?,?,?,?,?)",
            [(r.quarter, pid[r.provider],
              None if pd.isna(r.revenue_musd) else r.revenue_musd,
              None if pd.isna(r.operating_income_musd) else r.operating_income_musd,
              None if pd.isna(getattr(r, "note", None)) else r.note,
              None if pd.isna(getattr(r, "source_url", None)) else r.source_url)
             for r in fin.itertuples()])

    share_csv = MARKET_DIR / "market_share.csv"
    if share_csv.exists():
        share = pd.read_csv(share_csv)
        con.executemany(
            "INSERT OR REPLACE INTO fact_market_share VALUES (?,?,?,?,?,?)",
            [(r.quarter, r.firm, pid[r.provider],
              None if pd.isna(r.share_pct) else r.share_pct,
              None if pd.isna(r.market_size_busd) else r.market_size_busd,
              None if pd.isna(getattr(r, "source_url", None)) else r.source_url)
             for r in share.itertuples()])

    con.commit()
    for table in ("dim_provider", "dim_region", "dim_gpu", "fact_gpu_price",
                  "fact_quarterly_financials", "fact_market_share"):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {n:,} rows")
    con.close()
    print(f"\ndatabase -> {DB_PATH}")


if __name__ == "__main__":
    build()
