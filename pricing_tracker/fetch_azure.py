"""Fetch Azure GPU VM retail prices from the public (keyless) Retail Prices API.

API docs: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
Covers the N-series GPU families (NC/ND/NV/NG), Linux, pay-as-you-go + Spot.
"""
from __future__ import annotations

import re

import requests

from common import finalize

API = "https://prices.azure.com/api/retail/prices"

FILTER = (
    "serviceName eq 'Virtual Machines' and priceType eq 'Consumption' and ("
    "contains(armSkuName,'Standard_NC') or "
    "contains(armSkuName,'Standard_ND') or "
    "contains(armSkuName,'Standard_NV') or "
    "contains(armSkuName,'Standard_NG'))"
)

# Order matters: first match wins (newest/most specific first).
GPU_MODEL_PATTERNS = [
    (re.compile(r"GB200", re.I), "GB200"),
    (re.compile(r"H200", re.I), "H200"),
    (re.compile(r"H100", re.I), "H100"),
    (re.compile(r"A100", re.I), "A100"),
    (re.compile(r"MI300X", re.I), "MI300X"),
    (re.compile(r"MI300A", re.I), "MI300A"),
    (re.compile(r"T4", re.I), "T4"),
    (re.compile(r"A10", re.I), "A10"),
    (re.compile(r"L40S", re.I), "L40S"),
    (re.compile(r"V620", re.I), "V620"),
    (re.compile(r"_NC\d+r?s?_v3|NCv3", re.I), "V100"),
    (re.compile(r"ND40rs_v2", re.I), "V100"),
    (re.compile(r"_NC\d+r?s?_v2|NCv2", re.I), "P100"),
    (re.compile(r"_ND\d+r?s($|_)|NDs", re.I), "P40"),
    (re.compile(r"_NV\d+s?_v3|_NV\d+($|_)", re.I), "M60"),
    (re.compile(r"_NC\d+r?($|_)", re.I), "K80"),
    (re.compile(r"_NV\d+as_v4", re.I), "MI25"),
]

# GPUs per instance for the SKUs that matter most for the price index.
# Fractional values = partitioned GPUs (e.g. NVads A10 v5 sells 1/6 of an A10).
GPU_COUNT = {
    "Standard_NC24ads_A100_v4": 1, "Standard_NC48ads_A100_v4": 2,
    "Standard_NC96ads_A100_v4": 4, "Standard_ND96asr_v4": 8,
    "Standard_ND96amsr_A100_v4": 8, "Standard_ND96ams_A100_v4": 8,
    "Standard_NC40ads_H100_v5": 1, "Standard_NC80adis_H100_v5": 2,
    "Standard_ND96isr_H100_v5": 8, "Standard_ND96is_H100_v5": 8,
    "Standard_ND96isr_H200_v5": 8, "Standard_ND96is_H200_v5": 8,
    "Standard_ND96isr_MI300X_v5": 8,
    "Standard_NC4as_T4_v3": 1, "Standard_NC8as_T4_v3": 1,
    "Standard_NC16as_T4_v3": 1, "Standard_NC64as_T4_v3": 4,
    "Standard_NC6s_v3": 1, "Standard_NC12s_v3": 2, "Standard_NC24s_v3": 4,
    "Standard_NC24rs_v3": 4, "Standard_ND40rs_v2": 8,
    "Standard_NV6ads_A10_v5": 1 / 6, "Standard_NV12ads_A10_v5": 1 / 3,
    "Standard_NV18ads_A10_v5": 1 / 2, "Standard_NV36ads_A10_v5": 1,
    "Standard_NV36adms_A10_v5": 1, "Standard_NV72ads_A10_v5": 2,
}


def classify_model(arm_sku: str, product: str) -> str | None:
    text = f"{arm_sku} {product}"
    for pattern, model in GPU_MODEL_PATTERNS:
        if pattern.search(text):
            return model
    return None


def fetch():
    rows = []
    url, params = API, {"$filter": FILTER, "currencyCode": "USD"}
    while url:
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        for item in payload.get("Items", []):
            product = item.get("productName", "")
            sku_name = item.get("skuName", "")
            if "Windows" in product or "Low Priority" in sku_name:
                continue
            if "CloudServices" in product or "Dedicated Host" in product:
                continue
            arm_sku = item.get("armSkuName", "")
            if not arm_sku:
                continue
            model = classify_model(arm_sku, product)
            if model is None:
                continue  # not an identifiable GPU SKU
            rows.append({
                "region": item.get("armRegionName", ""),
                "sku": arm_sku,
                "gpu_model": model,
                "gpu_count": GPU_COUNT.get(arm_sku),
                "price_type": "spot" if sku_name.endswith("Spot") else "ondemand",
                "price_usd_hour": item.get("retailPrice"),
            })
        url, params = payload.get("NextPageLink"), None
    return finalize(rows, provider="Azure", source="prices.azure.com retail API")


if __name__ == "__main__":
    df = fetch()
    print(df.groupby(["gpu_model", "price_type"]).size().to_string())
    print(f"\n{len(df)} rows, {df['region'].nunique()} regions")
