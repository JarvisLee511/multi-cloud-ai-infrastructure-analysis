"""The validation gates turn a weekly CI run red; each one exists because the data once
went wrong that way without anything noticing."""
import pandas as pd

import run_all

COLS = ["snapshot_date", "provider", "region", "sku", "gpu_model", "gpu_count",
        "price_type", "price_usd_hour", "price_usd_per_gpu_hour", "source"]


def _healthy(date):
    rows = []
    for provider, n in run_all.MIN_ROWS.items():
        for i in range(n):
            rows.append((date, provider, f"r{i}", f"{provider}-sku{i}", "H100", 8.0,
                         "ondemand", 64.0, 8.0, "x"))
    return pd.DataFrame(rows, columns=COLS)


def _with(df, row):
    out = df.copy()
    out.loc[len(out)] = row
    return out


def test_healthy_snapshot_passes():
    assert run_all.validate(_healthy("2026-11-02")) == []


def test_dws_sku_labelled_ondemand_fails():
    df = _with(_healthy("2026-11-02"), (
        "2026-11-02", "GCP", "us-central1",
        "Nvidia H100 80GB GPU attached to DWS Defined Duration VMs running in Americas",
        "H100", 1.0, "ondemand", 4.2, 4.2, "x"))
    assert any("DWS/Spot" in p for p in run_all.validate(df))


def test_frontier_gpu_without_a_count_fails():
    df = _with(_healthy("2026-11-02"), (
        "2026-11-02", "Azure", "eastus", "Standard_ND128isr_NDR_GB200_v6", "GB200",
        None, "ondemand", 108.0, None, "x"))
    assert any("no GPU count" in p for p in run_all.validate(df))


def test_model_that_vanishes_fails():
    before = _healthy("2026-06-22")
    before = pd.concat([before] + [pd.DataFrame([(
        "2026-06-22", "AWS", f"r{i}", "trn1.32xlarge", "Trainium", 16.0, "ondemand",
        21.5, 21.5 / 16, "x")], columns=COLS) for i in range(12)], ignore_index=True)
    history = pd.concat([before, _healthy("2026-07-13")], ignore_index=True)
    assert any("AWS Trainium" in p for p in run_all.validate(history))
