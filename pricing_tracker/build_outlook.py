"""Build docs/outlook.html — forecast, AI momentum index, and the auto-generated
market pulse brief.

1. Revenue forecast: log-linear trend on the last 8 quarters per provider,
   normal prediction intervals on the log scale, 12-quarter horizon. Azure uses
   only the FY25-basis quarters (2024Q3+) to respect the segment break. The
   AWS-vs-Google-Cloud crossover quarter is solved from the fitted trends.
   Assumption-laden by design and labeled as such — constant-growth
   extrapolation, no saturation, no competitive response.
2. AI Momentum Index: a documented 0-100 composite built ONLY from this
   project's own datasets (GPU breadth, frontier-region reach, frontier price
   aggressiveness, capex acceleration, cloud revenue growth).
3. Market Pulse: an auto-written brief that refreshes with every weekly run.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from common import CONSOLIDATED_CSV, DOCS_DIR, REPO_ROOT

MARKET_DIR = REPO_ROOT / "data" / "market_history"
COLORS = {"AWS": "#FF9900", "Azure": "#0078D4", "GCP": "#34A853"}
LABELS = {"AWS": "AWS", "Azure": "Azure (Intelligent Cloud, FY25 basis)",
          "GCP": "Google Cloud"}
HORIZON = 12
FRONTIER = {"H100", "H200", "B200", "B300", "GB200", "MI300X"}
NAV = ('<nav><a href="index.html">Live GPU Pricing</a>'
       '<a href="market.html">Market History</a>'
       '<a href="regional.html">Regional Deep-Dive</a>'
       '<a href="analysis.html">Event Study &amp; Experiments</a>'
       '<a href="outlook.html">Outlook &amp; Pulse</a></nav>')


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _fin() -> pd.DataFrame:
    df = pd.read_csv(MARKET_DIR / "quarterly_financials.csv")
    df["date"] = pd.PeriodIndex(df["quarter"], freq="Q").to_timestamp()
    df["t"] = (df["date"].dt.year - 2016) * 4 + df["date"].dt.quarter - 1
    return df.sort_values("t")


def _fit(d: pd.DataFrame, window: int = 8) -> dict:
    d = d.dropna(subset=["revenue_musd"]).tail(window)
    slope, intercept = np.polyfit(d["t"], np.log(d["revenue_musd"]), 1)
    resid = np.log(d["revenue_musd"]) - (intercept + slope * d["t"])
    return {"a": intercept, "b": slope, "sigma": float(resid.std(ddof=2)),
            "last_t": int(d["t"].max()), "last_date": d["date"].max()}


def forecast_frame(fit: dict) -> pd.DataFrame:
    ts = np.arange(fit["last_t"] + 1, fit["last_t"] + 1 + HORIZON)
    dates = [fit["last_date"] + pd.DateOffset(months=3 * (i + 1)) for i in range(HORIZON)]
    point = np.exp(fit["a"] + fit["b"] * ts)
    band = 1.96 * fit["sigma"]
    return pd.DataFrame({"date": dates, "point": point,
                         "lo": point * np.exp(-band), "hi": point * np.exp(band)})


def fig_forecast(df: pd.DataFrame) -> tuple[go.Figure, dict]:
    fig = go.Figure()
    fits = {}
    for provider in ("AWS", "Azure", "GCP"):
        d = df[df["provider"] == provider]
        if provider == "Azure":
            d = d[d["quarter"] >= "2024Q3"]  # FY25 basis only
        fit = _fit(d, window=8)
        fits[provider] = fit
        fc = forecast_frame(fit)
        hist = d.dropna(subset=["revenue_musd"]).tail(16)
        fig.add_trace(go.Scatter(
            x=hist["date"], y=hist["revenue_musd"], name=LABELS[provider],
            mode="lines", line=dict(color=COLORS[provider], width=2.5),
            hovertemplate="%{x|%Y Q%q}: $%{y:,.0f}M<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=fc["date"], y=fc["point"], showlegend=False, mode="lines",
            line=dict(color=COLORS[provider], width=2, dash="dash"),
            hovertemplate="%{x|%Y Q%q}: $%{y:,.0f}M (forecast)<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=list(fc["date"]) + list(fc["date"][::-1]),
            y=list(fc["hi"]) + list(fc["lo"][::-1]),
            fill="toself", fillcolor=_rgba(COLORS[provider], 0.13),
            line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.update_layout(
        title=f"Revenue forecast — log-linear trend on the last 8 quarters, "
              f"{HORIZON}-quarter horizon (shaded = 95% interval)",
        yaxis_title="revenue $M / quarter", height=520,
        legend=dict(orientation="h", y=1.1), hovermode="x unified")
    return fig, fits


def crossover_quarter(fits: dict) -> str | None:
    """Solve where the GCP fitted line crosses the AWS fitted line."""
    a1, b1 = fits["AWS"]["a"], fits["AWS"]["b"]
    a2, b2 = fits["GCP"]["a"], fits["GCP"]["b"]
    if b2 <= b1:
        return None
    t_star = (a1 - a2) / (b2 - b1)
    year = 2016 + int(t_star) // 4
    q = int(t_star) % 4 + 1
    return f"{year}Q{q}"


def momentum_index() -> tuple[pd.DataFrame, str]:
    prices = pd.read_csv(CONSOLIDATED_CSV)
    latest = prices[prices["snapshot_date"] == prices["snapshot_date"].max()]
    od = latest[(latest["price_type"] == "ondemand")]

    fin = _fin()
    cap = pd.read_csv(MARKET_DIR / "quarterly_capex.csv").sort_values("quarter")
    cap_map = {"AWS": "amazon_capex_musd", "Azure": "microsoft_capex_musd",
               "GCP": "alphabet_capex_musd"}
    az_growth = pd.read_csv(MARKET_DIR / "azure_yoy_growth.csv")

    rows = {}
    for p in ("AWS", "Azure", "GCP"):
        d = od[od["provider"] == p]
        frontier = d[d["gpu_model"].isin(FRONTIER)]
        fr_price = frontier["price_usd_per_gpu_hour"].dropna()
        col = cap_map[p]
        capex_growth = cap[col].tail(4).sum() / cap[col].iloc[-8:-4].sum() - 1
        f = fin[fin["provider"] == p].dropna(subset=["revenue_musd"])
        if p == "Azure":
            growth = az_growth["azure_yoy_growth_pct"].iloc[-1]
        else:
            growth = (f["revenue_musd"].iloc[-1] / f["revenue_musd"].iloc[-5] - 1) * 100
        rows[p] = {
            "GPU breadth (models)": d["gpu_model"].nunique(),
            "Frontier reach (regions)": frontier["region"].nunique(),
            "Frontier price ($/GPU-hr, median)": fr_price.median(),
            "Capex acceleration (YoY %)": capex_growth * 100,
            "Cloud revenue growth (YoY %)": growth,
        }
    raw = pd.DataFrame(rows).T

    score = pd.DataFrame(index=raw.index)
    for col in raw.columns:
        if "price" in col.lower():
            score[col] = raw[col].min() / raw[col] * 100  # cheaper = better
        else:
            score[col] = raw[col] / raw[col].max() * 100
    weights = {"GPU breadth (models)": 0.20, "Frontier reach (regions)": 0.25,
               "Frontier price ($/GPU-hr, median)": 0.15,
               "Capex acceleration (YoY %)": 0.20,
               "Cloud revenue growth (YoY %)": 0.20}
    score["AI Momentum Index"] = sum(score[c] * w for c, w in weights.items()).round(1)

    head = "<tr><th>Component (weight)</th>" + "".join(
        f"<th style='color:{COLORS[p]}'>{p}</th>" for p in raw.index) + "</tr>"
    body = ""
    for col in raw.columns:
        cells = "".join(
            f"<td>{raw.loc[p, col]:,.1f} <span class='small'>(score {score.loc[p, col]:.0f})</span></td>"
            for p in raw.index)
        body += f"<tr><td>{col} ({weights[col]:.0%})</td>{cells}</tr>"
    total = "".join(f"<td><b>{score.loc[p, 'AI Momentum Index']:.1f}</b></td>"
                    for p in raw.index)
    table = (f"<table class='tbl'>{head}{body}"
             f"<tr><td><b>AI Momentum Index (0–100)</b></td>{total}</tr></table>")
    return score, table


def pulse(df: pd.DataFrame, fits: dict) -> str:
    prices = pd.read_csv(CONSOLIDATED_CSV)
    snaps = sorted(prices["snapshot_date"].unique())
    latest = prices[prices["snapshot_date"] == snaps[-1]]
    od = latest[(latest["price_type"] == "ondemand")
                & latest["price_usd_per_gpu_hour"].notna()]
    h100 = od[od["gpu_model"] == "H100"].groupby("provider")["price_usd_per_gpu_hour"].min()

    move = ""
    if len(snaps) >= 2:
        prev = prices[prices["snapshot_date"] == snaps[-2]]
        prev_h100 = (prev[(prev["price_type"] == "ondemand") & (prev["gpu_model"] == "H100")]
                     .groupby("provider")["price_usd_per_gpu_hour"].min())
        deltas = ((h100 - prev_h100) / prev_h100 * 100).dropna().round(1)
        move = "<li>Cheapest-H100 moves since last snapshot: " + ", ".join(
            f"{p} {v:+.1f}%" for p, v in deltas.items()) + "</li>"

    last_q = df["quarter"].max()
    rev = df[df["quarter"] == last_q].set_index("provider")["revenue_musd"]
    cap = pd.read_csv(MARKET_DIR / "quarterly_capex.csv").iloc[-1]
    cap_total = cap[["amazon_capex_musd", "microsoft_capex_musd",
                     "alphabet_capex_musd"]].sum()
    cross = crossover_quarter(fits)
    cross_li = (f"<li>If the last-8-quarter trends simply continued, Google Cloud's run-rate "
                f"would cross AWS's around <b>{cross}</b> — treat as an illustration of the "
                f"growth gap, not a prediction.</li>" if cross else "")
    return f"""
<ul>
<li>Cheapest on-demand H100 per GPU-hour right now:
{" · ".join(f"<b style='color:{COLORS[p]}'>{p} ${v:,.2f}</b>" for p, v in h100.items())}
(GCP's GPU SKUs exclude the host VM — see tracker methodology).</li>
{move}
<li>{last_q} cloud revenue: AWS ${rev.get('AWS', float('nan'))/1000:,.1f}B ·
Intelligent Cloud ${rev.get('Azure', float('nan'))/1000:,.1f}B ·
Google Cloud ${rev.get('GCP', float('nan'))/1000:,.1f}B; Google Cloud is growing roughly
twice as fast as the other two.</li>
<li>Combined parent capex hit <b>${cap_total/1000:,.0f}B</b> in {cap['quarter']} —
the AI buildout is still accelerating, not peaking.</li>
{cross_li}
</ul>"""


CSS = """
 body{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}
 .wrap{max-width:1100px;margin:0 auto;padding:32px 20px 64px}
 h1{margin-bottom:4px} h2{margin-top:36px} .byline{color:#57606a;margin-top:0}
 nav{margin:10px 0 0} nav a{color:#0969da;margin-right:18px;font-weight:600;text-decoration:none}
 .chart{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:8px;margin:20px 0}
 .note{background:#fff8c5;border:1px solid #d4a72c66;border-radius:8px;padding:12px 16px;font-size:14px}
 .pulse{background:#fff;border:1px solid #d0d7de;border-left:5px solid #1a7f37;border-radius:10px;padding:8px 22px;margin:20px 0}
 .pulse li{margin:10px 0;font-size:15px}
 .tbl{border-collapse:collapse;background:#fff;border:1px solid #d0d7de;font-size:14px;margin:16px 0}
 .tbl th,.tbl td{border:1px solid #d0d7de;padding:7px 12px;text-align:left}
 .tbl th{background:#f6f8fa}
 .small{font-size:12px;color:#57606a}
 footer{color:#57606a;font-size:13px;margin-top:40px}
 a{color:#0969da}
"""


def build() -> None:
    df = _fin()
    fig, fits = fig_forecast(df)
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn")
    _, index_table = momentum_index()
    pulse_html = pulse(df, fits)
    cross = crossover_quarter(fits)

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outlook & Market Pulse — Cloud Market Analysis</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Outlook &amp; Market Pulse</h1>
<p class="byline">Forecast, the AI Momentum Index, and an auto-generated brief that refreshes
with every weekly pipeline run.</p>
{NAV}
<h2>Market Pulse <span class="small">(auto-generated {built})</span></h2>
<div class="pulse">{pulse_html}</div>
<h2>Revenue outlook</h2>
<div class="chart">{chart}</div>
<div class="note"><b>Assumptions, stated plainly.</b> Log-linear extrapolation of the last
8 quarters: constant growth, no saturation, no competitive or macro response — useful for sizing
the growth gap, not for betting. Azure is fit only on FY25-basis quarters (the segment was
re-defined 2024Q3) and is a segment proxy, not Azure alone.
{f"On these trends Google Cloud's quarterly revenue would cross AWS's around <b>{cross}</b>." if cross else ""}</div>
<h2>AI Momentum Index</h2>
<p>A documented composite built only from this project's own datasets — weekly GPU pricing
snapshots, SEC-filed capex, and segment revenue. Each component is normalized to the best
performer (=100) and weighted as shown; for frontier price, cheaper scores higher.
Frontier set: {", ".join(sorted(FRONTIER))}.</p>
{index_table}
<div class="note">Index-design caveats: components correlate (capex buys frontier regions),
the price component inherits the bundling wedge (GCP's per-GPU SKUs exclude the host VM),
and breadth counts SKU variety, not installed capacity. Weights are judgment calls — the
table shows raw values so you can re-weight.</div>
<footer>Part of the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis">Multi-Cloud AI Infrastructure Market Analysis</a> project
· Che-Wei (Jarvis) Lee · built {built}</footer>
</div></body></html>"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "outlook.html").write_text(html, encoding="utf-8")
    print(f"outlook report -> {DOCS_DIR / 'outlook.html'}")
    if cross:
        print(f"GCP-AWS fitted crossover: {cross}")


if __name__ == "__main__":
    build()
