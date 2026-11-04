"""The outlook page scores every frozen forecast against what was later reported."""
import pandas as pd

import build_outlook as bo


def _vintage(path):
    rows = []
    for provider, actual_q in (("AWS", ["2026Q2", "2026Q3"]), ("Azure", ["2026Q2", "2026Q3"])):
        for h, q in enumerate(actual_q, start=1):
            rows.append({"vintage": "2026Q1", "provider": provider, "basis": "x", "quarter": q, "h": h,
                         "point_musd": 100.0, "lo95_musd": 95.0, "hi95_musd": 105.0, "naive_musd": 90.0})
    pd.DataFrame(rows).to_csv(path / "forecast_vintage_2026Q1.csv", index=False)


def test_scorecard_scores_only_reported_quarters(tmp_path, monkeypatch):
    _vintage(tmp_path)
    monkeypatch.setattr(bo, "MARKET_DIR", tmp_path)
    actuals = pd.DataFrame({
        "provider": ["AWS", "AWS", "Azure"],      # Azure's segment stopped after 2026Q2
        "quarter": ["2026Q2", "2026Q3", "2026Q2"],
        "revenue_musd": [102.0, 120.0, 110.0],
    })
    html = bo.scorecard(actuals)
    assert "How the 2026Q1 forecast did" in html
    assert "<b>3 of 3</b>" in html          # model beat naive in all three scored checks
    assert "inside its 95% band in <b>1 of 3</b>" in html   # only AWS 2026Q2 (102) is in 95-105
    assert "Azure is scored on fewer quarters" in html


def test_scorecard_is_empty_until_a_vintage_quarter_is_reported(tmp_path, monkeypatch):
    _vintage(tmp_path)
    monkeypatch.setattr(bo, "MARKET_DIR", tmp_path)
    early = pd.DataFrame({"provider": ["AWS"], "quarter": ["2026Q1"], "revenue_musd": [90.0]})
    assert bo.scorecard(early) == ""


def test_azure_is_forecast_on_disclosed_azure_revenue():
    s = bo._series(bo._fin(), "Azure")
    assert s["quarter"].min() == "2024Q3"
    assert (s["provider"] == "Azure").all() and s["revenue_musd"].notna().all()
