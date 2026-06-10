"""Fetch GCP GPU pricing from the Cloud Billing Catalog API.

GCP bills GPUs as separate per-GPU-hour SKUs attached to VMs, so gpu_count is 1
and the price IS the per-GPU price. Auth: set GCP_API_KEY (a plain API key with
the Cloud Billing API enabled), or fall back to `gcloud auth print-access-token`
for local runs.
"""
from __future__ import annotations

import os
import re
import subprocess

import requests

from common import finalize

COMPUTE_SERVICE = "services/6F81-5844-456A"  # Compute Engine
API = f"https://cloudbilling.googleapis.com/v1/{COMPUTE_SERVICE}/skus"

MODEL_PATTERNS = [
    (re.compile(r"GB200", re.I), "GB200"),
    (re.compile(r"B200", re.I), "B200"),
    (re.compile(r"H200", re.I), "H200"),
    (re.compile(r"H100", re.I), "H100"),
    (re.compile(r"A100 80GB|A100-80", re.I), "A100-80GB"),
    (re.compile(r"A100", re.I), "A100"),
    (re.compile(r"L4", re.I), "L4"),
    (re.compile(r"T4", re.I), "T4"),
    (re.compile(r"V100", re.I), "V100"),
    (re.compile(r"P100", re.I), "P100"),
    (re.compile(r"P4", re.I), "P4"),
    (re.compile(r"K80", re.I), "K80"),
]

USAGE_TYPE_MAP = {"OnDemand": "ondemand", "Preemptible": "spot"}


def _auth():
    """Return (params, headers) for the Billing API."""
    key = os.environ.get("GCP_API_KEY")
    if key:
        return {"key": key}, {}
    token = subprocess.run(
        "gcloud auth print-access-token", shell=True,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {}, {"Authorization": f"Bearer {token}"}


def normalize_model(description: str) -> str | None:
    for pattern, model in MODEL_PATTERNS:
        if pattern.search(description):
            return model
    return None


def _unit_price(sku: dict):
    """Last tiered rate of the first pricing info, in USD/hour."""
    infos = sku.get("pricingInfo") or []
    if not infos:
        return None
    expr = infos[0].get("pricingExpression") or {}
    if expr.get("usageUnit") not in ("h", "GiBy.h", "GBy.h"):
        # GPU SKUs bill per hour; skip anything else defensively.
        if expr.get("usageUnit") != "h":
            return None
    rates = expr.get("tieredRates") or []
    if not rates:
        return None
    price = rates[-1].get("unitPrice") or {}
    return float(price.get("units") or 0) + float(price.get("nanos") or 0) / 1e9


def fetch():
    params, headers = _auth()
    params = {**params, "pageSize": 5000}
    rows, page_token = [], None
    while True:
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(API, params=params, headers=headers, timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        for sku in payload.get("skus", []):
            cat = sku.get("category") or {}
            if cat.get("resourceGroup") != "GPU":
                continue
            price_type = USAGE_TYPE_MAP.get(cat.get("usageType"))
            if price_type is None:
                continue  # skip commitments / reservations
            desc = sku.get("description", "")
            if "Sole Tenancy" in desc or "Reserved" in desc:
                continue
            model = normalize_model(desc)
            if model is None:
                continue
            price = _unit_price(sku)
            if not price:
                continue
            for region in sku.get("serviceRegions") or []:
                rows.append({
                    "region": region, "sku": desc, "gpu_model": model,
                    "gpu_count": 1.0, "price_type": price_type,
                    "price_usd_hour": price,
                })
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return finalize(rows, provider="GCP", source="Cloud Billing Catalog API")


if __name__ == "__main__":
    df = fetch()
    print(df.groupby(["gpu_model", "price_type"]).size().to_string())
    print(f"\n{len(df)} rows, {df['region'].nunique()} regions")
