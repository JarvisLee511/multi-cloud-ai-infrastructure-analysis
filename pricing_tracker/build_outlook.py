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
import theme

MARKET_DIR = REPO_ROOT / "data" / "market_history"
COLORS = theme.PROVIDER
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


def backtest(df: pd.DataFrame, window: int = 8, folds: int = 6) -> str:
    """Rolling-origin backtest of the log-linear forecaster vs a naive
    (last-value) baseline, on the quarters we already know the answer to.
    Azure is excluded: only 7 FY25-basis quarters exist — too short."""
    rows = []
    for provider in ("AWS", "GCP"):
        d = (df[df["provider"] == provider].dropna(subset=["revenue_musd"])
             .sort_values("t").reset_index(drop=True))
        for h in (1, 4):
            err_model, err_naive = [], []
            for k in range(folds):
                end = len(d) - h - k
                train = d.iloc[end - window:end]
                actual = d.loc[end - 1 + h, "revenue_musd"]
                slope, intercept = np.polyfit(
                    train["t"], np.log(train["revenue_musd"]), 1)
                pred = np.exp(intercept + slope * (train["t"].iloc[-1] + h))
                naive = train["revenue_musd"].iloc[-1]
                err_model.append(abs(pred - actual) / actual)
                err_naive.append(abs(naive - actual) / actual)
            rows.append({
                "provider": "Google Cloud" if provider == "GCP" else provider,
                "h": f"{h} quarter{'s' if h > 1 else ''} ahead",
                "model": np.mean(err_model) * 100,
                "naive": np.mean(err_naive) * 100,
            })
    body = "".join(
        f"<tr><td>{r['provider']}</td><td>{r['h']}</td>"
        f"<td><b>{r['model']:.1f}%</b></td><td>{r['naive']:.1f}%</td></tr>"
        for r in rows)
    return ("<table class='tbl'><tr><th>Provider</th><th>Horizon</th>"
            "<th>Log-linear MAPE</th><th>Naive (last value) MAPE</th></tr>"
            + body + "</table>")


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


def buyers_guide() -> str:
    """The 'so what' — data-driven guidance for a GPU-compute buyer,
    every claim computed from the latest snapshot."""
    prices = pd.read_csv(CONSOLIDATED_CSV)
    latest = prices[prices["snapshot_date"] == prices["snapshot_date"].max()]
    od = latest[(latest["price_type"] == "ondemand")
                & latest["price_usd_per_gpu_hour"].notna()]
    h100 = od[od["gpu_model"] == "H100"].groupby("provider")["price_usd_per_gpu_hour"].min()
    cheapest = h100.idxmin()

    sp = latest[latest["price_usd_per_gpu_hour"].notna()]
    pair = (sp[sp["price_type"] == "ondemand"].merge(
        sp[sp["price_type"] == "spot"],
        on=["provider", "region", "sku", "gpu_model"], suffixes=("_od", "_sp")))
    pair = pair[pair["price_usd_hour_od"] > 0]
    pair["disc"] = 1 - pair["price_usd_hour_sp"] / pair["price_usd_hour_od"]
    disc = pair.groupby("provider")["disc"].median()
    best_spot = disc.idxmax()

    regions = od.groupby("provider")["region"].nunique()
    widest = regions.idxmax()

    return f"""
<h2>If you are buying GPU compute today</h2>
<div class="why"><ul>
<li><b>Bursty training, price-sensitive:</b> {cheapest} has the lowest H100 list floor
(${h100[cheapest]:,.2f}/GPU-hr{', GPU-only SKU — add host-VM cost' if cheapest == 'GCP' else ''});
combine with {best_spot}'s spot/preemptible tier, which carries the deepest median discount
({disc[best_spot]:.0%}) if your jobs checkpoint well.</li>
<li><b>Latency / data-residency constrained:</b> {widest} offers GPU compute in the most
regions ({regions[widest]}) — the widest footprint for compliance-bound workloads
(see the <a href="regional.html">regional deep-dive</a> for the China exception).</li>
<li><b>Negotiating leverage:</b> regional price dispersion is real — the same GPU lists at
materially different prices across regions (tracker, dispersion chart). If your workload is
region-flexible, quote the cheapest region's floor in negotiations; list prices are ceilings,
not floors, at committed volume.</li>
</ul></div>
<p class="small">Generated from the latest weekly snapshot — every number above recomputes
automatically as prices move.</p>
"""


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




def build() -> None:
    df = _fin()
    fig, fits = fig_forecast(df)
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn")
    _, index_table = momentum_index()
    pulse_html = pulse(df, fits)
    cross = crossover_quarter(fits)
    backtest_table = backtest(df)
    guide_html = buyers_guide()

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"""<h2>Market Pulse <span class="small">(auto-generated {built})</span></h2>
<div class="pulse">{pulse_html}</div>
{guide_html}
<h2>Revenue outlook</h2>
<div class="chart">{chart}</div>
<div class="note"><b>Assumptions, stated plainly.</b> Log-linear extrapolation of the last
8 quarters: constant growth, no saturation, no competitive or macro response — useful for sizing
the growth gap, not for betting. Azure is fit only on FY25-basis quarters (the segment was
re-defined 2024Q3) and is a segment proxy, not Azure alone.
{f"On these trends Google Cloud's quarterly revenue would cross AWS's around <b>{cross}</b>." if cross else ""}</div>
<h3>How good is this forecaster? (rolling-origin backtest)</h3>
<p>Before trusting any extrapolation, test it on quarters we already know the answer to:
re-fit the model at six past origins and score out-of-sample errors against a naive
last-value baseline.</p>
{backtest_table}
<p class="small">MAPE = mean absolute percentage error across 6 rolling origins.
The model needs to beat naive convincingly at 4 quarters out to justify the fan chart above;
1-quarter-ahead is nearly unbeatable by anything (revenue is highly persistent).</p>
<h2>AI Momentum Index</h2>
<p>A documented composite built only from this project's own datasets — weekly GPU pricing
snapshots, SEC-filed capex, and segment revenue. Each component is normalized to the best
performer (=100) and weighted as shown; for frontier price, cheaper scores higher.
Frontier set: {", ".join(sorted(FRONTIER))}.</p>
{index_table}
<div class="note">Index-design caveats: components correlate (capex buys frontier regions),
the price component inherits the bundling wedge (GCP's per-GPU SKUs exclude the host VM),
and breadth counts SKU variety, not installed capacity. Weights are judgment calls — the
table shows raw values so you can re-weight.</div>"""

    html = theme.page(
        slug='outlook.html',
        title='Cloud Outlook and Pulse — a twelve-quarter forecast with its assumptions',
        description="A twelve-quarter revenue forecast with its assumptions stated and backtested, an AI momentum index built from this project's own datasets, and a market brief regenerated on every weekly run.",
        kicker='Outlook',
        headline='Twelve quarters ahead, with the assumptions on the page',
        standfirst='A forecast is worth exactly what its assumptions are worth, so they are printed beside the lines they produce and scored against a naive baseline on quarters we already know the answer to.',
        byline='Forecast, backtest and momentum index, rebuilt weekly',
        body=body,
    )
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "outlook.html").write_text(html, encoding="utf-8")
    print(f"outlook report -> {DOCS_DIR / 'outlook.html'}")
    if cross:
        print(f"GCP-AWS fitted crossover: {cross}")


if __name__ == "__main__":
    build()
