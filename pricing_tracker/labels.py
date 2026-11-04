"""Price-type and accelerator labels, derived from SKU text instead of trusted upstream.

`normalise()` runs every time the history is consolidated, so a fix here applies to every
saved snapshot without editing the raw files in data/pricing_history/. Each rule exists
because a real snapshot got it wrong:

* Google sells GPUs through its Dynamic Workload Scheduler (DWS) as well as on demand. DWS
  SKUs ("... attached to DWS Defined Duration VMs", "DWS Calendar Mode ...") report usageType
  "OnDemand" in the billing catalog, but they are capacity you queue for or book for a fixed
  window, at a discount. From 2026-06-10 to 2026-11-02 the tracker counted them as on-demand,
  which made Google look like the cheapest cloud for H100, H200 and B200.
* A few B200 SKUs say "Spot Preemptible" in the description while reporting usageType
  "OnDemand".
* The Vantage AWS dataset reported Trainium instances as "AWS Inferentia", then as an empty
  model, and from 2026-07-13 as GPU = 0 (so they dropped out of the tracker). AWS's own chips
  are therefore identified from the instance family, with the chip count per size below.
* Vantage renamed the g7e accelerator from "NVIDIA GB202" to "NVIDIA RTX PRO 6000 Blackwell"
  on 2026-08-10; both map to one model so the series does not break.
"""
from __future__ import annotations

import re

import pandas as pd

PRICE_TYPES = ("ondemand", "spot", "dws_duration", "dws_calendar")

# --------------------------------------------------------------------------- Google Cloud


def gcp_price_type(description: str, usage_type: str | None) -> str | None:
    """Price type of a Google GPU SKU. None = not a price this tracker keeps."""
    text = description or ""
    if "Spot Preemptible" in text or usage_type == "Preemptible":
        return "spot"
    if "DWS Calendar" in text:
        return "dws_calendar"
    if "DWS" in text:
        return "dws_duration"
    if usage_type == "OnDemand":
        return "ondemand"
    return None  # commitments and anything else


# --------------------------------------------------------------------------- AWS

# AWS's own accelerators: model name and chips per instance size (AWS instance-type docs).
AWS_CUSTOM_SILICON = {
    "inf1": ("Inferentia", {"xlarge": 1, "2xlarge": 1, "6xlarge": 4, "24xlarge": 16}),
    "inf2": ("Inferentia2", {"xlarge": 1, "8xlarge": 1, "24xlarge": 6, "48xlarge": 12}),
    "trn1": ("Trainium", {"2xlarge": 1, "32xlarge": 16}),
    "trn1n": ("Trainium", {"32xlarge": 16}),
    "trn2": ("Trainium2", {"48xlarge": 16}),
}

# Order matters: first match wins (newest / most specific first).
AWS_MODEL_PATTERNS = [
    (re.compile(r"GB200", re.I), "GB200"),
    (re.compile(r"B300", re.I), "B300"),
    (re.compile(r"B200", re.I), "B200"),
    (re.compile(r"H200", re.I), "H200"),
    (re.compile(r"H100", re.I), "H100"),
    (re.compile(r"A100", re.I), "A100"),
    (re.compile(r"RTX PRO 6000|GB202", re.I), "RTX PRO 6000"),
    (re.compile(r"RTX PRO 4500", re.I), "RTX PRO 4500"),
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
    (re.compile(r"Qualcomm AI 100", re.I), "Qualcomm AI 100"),
]

# When Vantage leaves the model empty, the instance family still says what it is.
AWS_FAMILY_MODEL = {"g7e": "RTX PRO 6000", "g7": "RTX PRO 4500", "p6-b300": "B300"}


def _family_size(instance_type: str) -> tuple[str, str]:
    family, _, size = (instance_type or "").partition(".")
    return family, size


def aws_accelerators(instance_type: str) -> float | None:
    """Chip count for AWS's own accelerators (Vantage reports them as GPU = 0)."""
    family, size = _family_size(instance_type)
    if family in AWS_CUSTOM_SILICON:
        return AWS_CUSTOM_SILICON[family][1].get(size)
    return None


def aws_model(instance_type: str, raw_model: str | None) -> str:
    family, _ = _family_size(instance_type)
    if family in AWS_CUSTOM_SILICON:
        return AWS_CUSTOM_SILICON[family][0]
    for pattern, model in AWS_MODEL_PATTERNS:
        if pattern.search(raw_model or ""):
            return model
    if family in AWS_FAMILY_MODEL:
        return AWS_FAMILY_MODEL[family]
    raw = (raw_model or "").strip()
    return raw if raw and raw.lower() != "unknown" else "unknown"


# --------------------------------------------------------------------------- Azure

# GPUs per VM. Fractional values = partitioned GPUs (NVads A10 v5 sells 1/6 of an A10).
# SKUs not listed (e.g. NC A10 v4, NGads V620, ND40s_v2) keep an unknown count and stay out
# of per-GPU comparisons rather than being guessed.
AZURE_GPU_COUNT = {
    # A100
    "Standard_NC24ads_A100_v4": 1, "Standard_NC48ads_A100_v4": 2,
    "Standard_NC96ads_A100_v4": 4, "Standard_ND96asr_v4": 8,
    "Standard_ND96asr_A100_v4": 8,  # same 96-vCPU, 8-GPU size, alternate name
    "Standard_ND96amsr_A100_v4": 8, "Standard_ND96ams_A100_v4": 8,
    # H100 (ND96 variants are the same 8-GPU size with/without InfiniBand or flex billing)
    "Standard_NC40ads_H100_v5": 1, "Standard_NC80adis_H100_v5": 2,
    "Standard_NCC40ads_H100_v5": 1,
    "Standard_ND96isr_H100_v5": 8, "Standard_ND96is_H100_v5": 8,
    "Standard_ND96isrf_H100_v5": 8, "Standard_ND96isf_H100_v5": 8,
    "Standard_ND96is_flex_H100_v5": 8, "Standard_ND96is_noIB_H100_v5": 8,
    # H200, GB200, MI300X
    "Standard_ND96isr_H200_v5": 8, "Standard_ND96is_H200_v5": 8,
    "Standard_ND96isrf_H200_v5": 8,
    "Standard_ND128isr_NDR_GB200_v6": 4, "Standard_ND128isrf_NDR_GB200_v6": 4,
    "Standard_ND96isr_MI300X_v5": 8, "Standard_ND96is_MI300X_v5": 8,
    # T4, V100
    "Standard_NC4as_T4_v3": 1, "Standard_NC8as_T4_v3": 1,
    "Standard_NC16as_T4_v3": 1, "Standard_NC64as_T4_v3": 4,
    "Standard_NC6s_v3": 1, "Standard_NC12s_v3": 2, "Standard_NC24s_v3": 4,
    "Standard_NC24rs_v3": 4, "Standard_ND40rs_v2": 8,
    # A10 (partitioned)
    "Standard_NV6ads_A10_v5": 1 / 6, "Standard_NV12ads_A10_v5": 1 / 3,
    "Standard_NV18ads_A10_v5": 1 / 2, "Standard_NV36ads_A10_v5": 1,
    "Standard_NV36adms_A10_v5": 1, "Standard_NV72ads_A10_v5": 2,
    # legacy: M60 (NVv3 and promo NV), MI25 (NVv4, partitioned), K80 (promo NC)
    "Standard_NV12s_v3": 1, "Standard_NV24s_v3": 2, "Standard_NV48s_v3": 4,
    "Standard_NV6_Promo": 1, "Standard_NV12_Promo": 2, "Standard_NV24_Promo": 4,
    "Standard_NV4as_v4": 1 / 8, "Standard_NV8as_v4": 1 / 4,
    "Standard_NV16as_v4": 1 / 2, "Standard_NV32as_v4": 1,
    "Standard_NC6_Promo": 1, "Standard_NC12_Promo": 2,
    "Standard_NC24_Promo": 4, "Standard_NC24r_Promo": 4,
}

# Models whose per-GPU price headlines the report: a missing GPU count here is a bug.
FRONTIER_MODELS = {"GB200", "B300", "B200", "H200", "H100", "MI300X", "A100"}


# --------------------------------------------------------------------------- all providers


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Re-derive price types, model names and GPU counts from the stored SKU text."""
    out = df.copy()

    gcp = out["provider"] == "GCP"
    if gcp.any():
        # The stored label came from usageType (OnDemand -> ondemand, Preemptible -> spot).
        usage = out.loc[gcp, "price_type"].map({"spot": "Preemptible"}).fillna("OnDemand")
        out.loc[gcp, "price_type"] = [
            gcp_price_type(desc, u) for desc, u in zip(out.loc[gcp, "sku"], usage)]

    aws = out["provider"] == "AWS"
    if aws.any():
        out.loc[aws, "gpu_model"] = [
            aws_model(sku, model)
            for sku, model in zip(out.loc[aws, "sku"], out.loc[aws, "gpu_model"])]

    azure = out["provider"] == "Azure"
    if azure.any():
        known = out.loc[azure, "sku"].map(AZURE_GPU_COUNT)
        out.loc[azure, "gpu_count"] = out.loc[azure, "gpu_count"].fillna(known)

    out["gpu_count"] = pd.to_numeric(out["gpu_count"], errors="coerce")
    out["price_usd_per_gpu_hour"] = out["price_usd_hour"] / out["gpu_count"]
    return out.loc[out["price_type"].notna()].reset_index(drop=True)


def implausible(df: pd.DataFrame, min_ratio: float = 0.05, min_group: int = 5) -> pd.Series:
    """Rows whose per-GPU price is under 5% of the same week's median for that provider,
    model and price type. Azure published $0.0005-$0.06 per GPU-hour for A10s in ukwest and
    T4s in spaincentral from 2026-08-03 to 2026-08-17; genuine spot prices sit at 12-19%."""
    price = df["price_usd_per_gpu_hour"]
    keys = [df["snapshot_date"], df["provider"], df["gpu_model"], df["price_type"]]
    grouped = price.groupby(keys)
    median = grouped.transform("median")
    size = grouped.transform("count")
    return price.notna() & (size >= min_group) & (price < min_ratio * median)


def plausible(df: pd.DataFrame) -> pd.DataFrame:
    """The history with implausible prices removed (the raw snapshots keep them)."""
    return df.loc[~implausible(df)]
