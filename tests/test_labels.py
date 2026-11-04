"""Each case is a SKU string or situation the live tracker actually hit."""
from pathlib import Path

import pandas as pd
import pytest

import labels

H100 = "Nvidia H100 80GB GPU running in Americas"
H100_DWS = "Nvidia H100 80GB GPU attached to DWS Defined Duration VMs running in Americas"
B200_CAL = "DWS Calendar Mode A4 Nvidia B200 (1 gpu slice) running in Americas"
B200_SPOT_ODD = "Spot Preemptible A4 Nvidia B200 (1 gpu slice) running in Americas"
H100_SPOT = "Nvidia H100 80GB GPU attached to Spot Preemptible VMs running in Americas"


@pytest.mark.parametrize("desc, usage, expected", [
    (H100, "OnDemand", "ondemand"),
    (H100_DWS, "OnDemand", "dws_duration"),     # was counted as on-demand until 2026-11
    (B200_CAL, "OnDemand", "dws_calendar"),
    (B200_SPOT_ODD, "OnDemand", "spot"),        # description says spot, usageType does not
    (H100_SPOT, "Preemptible", "spot"),
    ("Commitment v1: Nvidia H100 80GB GPU in Americas for 1 Year", "Commit1Yr", None),
])
def test_gcp_price_type(desc, usage, expected):
    assert labels.gcp_price_type(desc, usage) == expected


@pytest.mark.parametrize("itype, raw, expected", [
    ("trn1.32xlarge", "AWS Inferentia", "Trainium"),  # Vantage's June label was wrong
    ("trn1n.32xlarge", None, "Trainium"),
    ("inf2.48xlarge", None, "Inferentia2"),
    ("g7e.48xlarge", "NVIDIA GB202", "RTX PRO 6000"),  # renamed upstream on 2026-08-10
    ("g7e.48xlarge", "NVIDIA RTX PRO 6000 Blackwell", "RTX PRO 6000"),
    ("g7.2xlarge", "unknown", "RTX PRO 4500"),
    ("p6-b300.48xlarge", "NVIDIA B300", "B300"),
    ("p5.48xlarge", "NVIDIA H100", "H100"),
    ("dl2q.24xlarge", "Qualcomm AI 100 Accelerators", "Qualcomm AI 100"),
])
def test_aws_model(itype, raw, expected):
    assert labels.aws_model(itype, raw) == expected


def test_aws_custom_silicon_counts():
    assert labels.aws_accelerators("trn2.48xlarge") == 16
    assert labels.aws_accelerators("inf2.24xlarge") == 6
    assert labels.aws_accelerators("trn1.8xlarge") is None  # unknown size: not guessed
    assert labels.aws_accelerators("p5.48xlarge") is None   # GPUs come from Vantage itself


def _rows(rows):
    cols = ["snapshot_date", "provider", "region", "sku", "gpu_model", "gpu_count",
            "price_type", "price_usd_hour", "price_usd_per_gpu_hour", "source"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def test_normalise_relabels_history_and_is_idempotent():
    df = _rows([
        ("2026-06-10", "GCP", "us-central1", H100_DWS, "H100", 1.0, "ondemand", 4.2, 4.2, "x"),
        ("2026-06-10", "GCP", "us-central1", H100, "H100", 1.0, "ondemand", 9.8, 9.8, "x"),
        ("2026-06-10", "AWS", "us-east-1", "trn1.32xlarge", "AWS Inferentia", 16.0,
         "ondemand", 21.5, 21.5 / 16, "x"),
        ("2026-06-10", "Azure", "eastus", "Standard_ND96is_flex_H100_v5", "H100", None,
         "ondemand", 80.0, None, "x"),
    ])
    once = labels.normalise(df)
    assert once["price_type"].tolist() == ["dws_duration", "ondemand", "ondemand", "ondemand"]
    assert once.loc[2, "gpu_model"] == "Trainium"
    assert once.loc[3, "gpu_count"] == 8
    assert once.loc[3, "price_usd_per_gpu_hour"] == pytest.approx(10.0)
    pd.testing.assert_frame_equal(labels.normalise(once), once)


def _week(prices, model="A10", provider="Azure", price_type="ondemand"):
    return _rows([("2026-08-03", provider, f"r{i}", f"sku{i}", model, 1.0, price_type, p, p, "x")
                  for i, p in enumerate(prices)])


def test_implausible_catches_the_azure_cent_prices():
    df = _week([4.0] * 9 + [0.005])  # ukwest A10, 2026-08-03
    assert labels.implausible(df).tolist() == [False] * 9 + [True]


def test_implausible_leaves_real_spot_prices_alone():
    df = _week([1.0] * 9 + [0.15], price_type="spot")  # 15% of median: deep but real
    assert not labels.implausible(df).any()


def test_implausible_needs_a_group_to_compare_against():
    assert not labels.implausible(_week([4.0, 4.0, 0.005])).any()


def test_history_on_disk_has_no_discounted_gcp_rows_left_as_ondemand():
    path = Path(__file__).resolve().parents[1] / "data" / "gpu_price_history.csv"
    if not path.exists():
        pytest.skip("consolidated history not built")
    df = pd.read_csv(path)
    gcp_od = df[(df["provider"] == "GCP") & (df["price_type"] == "ondemand")]
    assert not gcp_od["sku"].str.contains("DWS|Spot").any()
