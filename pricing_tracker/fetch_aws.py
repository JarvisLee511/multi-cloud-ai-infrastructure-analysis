"""Fetch AWS GPU instance pricing from the Vantage (ec2instances.info) dataset.

Source: https://instances.vantage.sh/instances.json — an open dataset compiled
from the official AWS Price List API. Used instead of the raw AWS offer files
because those are multi-GB per region; this mirror is a few dozen MB and keyless.
On-demand Linux prices per region, plus spot when published. Vantage reports AWS's own
chips (Trainium, Inferentia) as GPU = 0, so those are counted from the instance family
(labels.AWS_CUSTOM_SILICON).
"""
from __future__ import annotations

import requests

from common import finalize
from labels import aws_accelerators, aws_model

URL = "https://instances.vantage.sh/instances.json"


def normalize_model(instance_type: str, raw: str | None) -> str:
    return aws_model(instance_type, raw)


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
        itype = inst.get("instance_type", "")
        try:
            gpu_count = float(inst.get("GPU") or 0)
        except (TypeError, ValueError):
            gpu_count = 0.0
        if gpu_count <= 0:
            gpu_count = aws_accelerators(itype) or 0.0
        if gpu_count <= 0:
            continue
        model = normalize_model(itype, inst.get("GPU_model"))
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
