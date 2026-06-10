"""Fetch AWS GPU instance pricing from the Vantage (ec2instances.info) dataset.

Source: https://instances.vantage.sh/instances.json — an open dataset compiled
from the official AWS Price List API. Used instead of the raw AWS offer files
because those are multi-GB per region; this mirror is a few dozen MB and keyless.
On-demand Linux prices per region, plus spot when published.
"""
from __future__ import annotations

import re

import requests

from common import finalize

URL = "https://instances.vantage.sh/instances.json"

MODEL_PATTERNS = [
    (re.compile(r"GB200", re.I), "GB200"),
    (re.compile(r"B200", re.I), "B200"),
    (re.compile(r"H200", re.I), "H200"),
    (re.compile(r"H100", re.I), "H100"),
    (re.compile(r"A100", re.I), "A100"),
    (re.compile(r"L40S", re.I), "L40S"),
    (re.compile(r"\bL4\b", re.I), "L4"),
    (re.compile(r"A10G", re.I), "A10G"),
    (re.compile(r"T4G", re.I), "T4G"),
    (re.compile(r"\bT4\b", re.I), "T4"),
    (re.compile(r"V100", re.I), "V100"),
    (re.compile(r"K80", re.I), "K80"),
    (re.compile(r"M60", re.I), "M60"),
    (re.compile(r"K520", re.I), "K520"),
    (re.compile(r"V520", re.I), "V520"),
    (re.compile(r"Gaudi", re.I), "Gaudi"),
]


def normalize_model(raw: str) -> str:
    for pattern, model in MODEL_PATTERNS:
        if pattern.search(raw or ""):
            return model
    return (raw or "unknown").strip()


def _spot_price(linux: dict):
    for key in ("spot_avg", "spot", "spot_min"):
        value = linux.get(key)
        if value not in (None, "", "N/A"):
            return value
    return None


def fetch():
    resp = requests.get(URL, timeout=300)
    resp.raise_for_status()
    instances = resp.json()

    rows = []
    for inst in instances:
        try:
            gpu_count = float(inst.get("GPU") or 0)
        except (TypeError, ValueError):
            continue
        if gpu_count <= 0:
            continue
        itype = inst.get("instance_type", "")
        model = normalize_model(inst.get("GPU_model", ""))
        for region, by_os in (inst.get("pricing") or {}).items():
            linux = (by_os or {}).get("linux") or {}
            ondemand = linux.get("ondemand")
            if ondemand not in (None, "", "N/A"):
                rows.append({
                    "region": region, "sku": itype, "gpu_model": model,
                    "gpu_count": gpu_count, "price_type": "ondemand",
                    "price_usd_hour": ondemand,
                })
            spot = _spot_price(linux)
            if spot is not None:
                rows.append({
                    "region": region, "sku": itype, "gpu_model": model,
                    "gpu_count": gpu_count, "price_type": "spot",
                    "price_usd_hour": spot,
                })
    return finalize(rows, provider="AWS", source="instances.vantage.sh (AWS Price List mirror)")


if __name__ == "__main__":
    df = fetch()
    print(df.groupby(["gpu_model", "price_type"]).size().to_string())
    print(f"\n{len(df)} rows, {df['region'].nunique()} regions")
