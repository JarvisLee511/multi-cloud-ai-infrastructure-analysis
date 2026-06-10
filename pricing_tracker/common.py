"""Shared schema and helpers for the GPU pricing tracker.

Every fetcher returns a pandas DataFrame with the columns in SCHEMA, one row
per (region, SKU, price_type). Prices are USD per hour. price_usd_per_gpu_hour
is filled only when the GPU count for the SKU is known.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "pricing_history"
CONSOLIDATED_CSV = REPO_ROOT / "data" / "gpu_price_history.csv"
DOCS_DIR = REPO_ROOT / "docs"

SCHEMA = [
    "snapshot_date",   # YYYY-MM-DD (UTC)
    "provider",        # AWS | Azure | GCP
    "region",          # provider-native region code
    "sku",             # instance type / ARM SKU / billing SKU description
    "gpu_model",       # normalized accelerator model (H100, A100, T4, ...)
    "gpu_count",       # GPUs per instance (float; fractional for partial GPUs)
    "price_type",      # ondemand | spot
    "price_usd_hour",  # instance price per hour, USD
    "price_usd_per_gpu_hour",  # price_usd_hour / gpu_count when known
    "source",          # data source identifier
]


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def finalize(rows: list[dict], provider: str, source: str) -> pd.DataFrame:
    """Build a schema-conformant DataFrame from raw row dicts."""
    df = pd.DataFrame(rows)
    df["snapshot_date"] = today_utc()
    df["provider"] = provider
    df["source"] = source
    df["price_usd_hour"] = pd.to_numeric(df["price_usd_hour"], errors="coerce")
    df = df[df["price_usd_hour"] > 0]
    df["gpu_count"] = pd.to_numeric(df.get("gpu_count"), errors="coerce")
    df["price_usd_per_gpu_hour"] = df["price_usd_hour"] / df["gpu_count"]
    df = df.reindex(columns=SCHEMA)
    df = df.drop_duplicates(subset=["region", "sku", "price_type"], keep="first")
    return df.sort_values(["region", "sku", "price_type"]).reset_index(drop=True)


def save_snapshot(df: pd.DataFrame, provider: str) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{today_utc()}_{provider.lower()}.csv"
    df.to_csv(path, index=False)
    return path


def consolidate() -> pd.DataFrame:
    """Rebuild the consolidated long table from all snapshot files."""
    files = sorted(HISTORY_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no snapshots in {HISTORY_DIR}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(
        subset=["snapshot_date", "provider", "region", "sku", "price_type"]
    )
    CONSOLIDATED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CONSOLIDATED_CSV, index=False)
    return df
