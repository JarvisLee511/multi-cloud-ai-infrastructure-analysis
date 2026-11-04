"""Build docs/outlook.html — forecast, AI momentum index, and the auto-generated
market pulse brief.

1. Revenue forecast: log-linear trend on the last 8 quarters per provider,
   normal prediction intervals on the log scale, 12-quarter horizon. Azure is
   Microsoft's directly disclosed Azure revenue (from FY27, restated to 2024Q3);
   the Intelligent Cloud segment it replaced ended in 2026Q2. The
   AWS-vs-Google-Cloud crossover quarter is solved from the fitted trends.
   Assumption-laden by design and labeled as such — constant-growth
   extrapolation, no saturation, no competitive response.
   Each published forecast is frozen in data/market_history/forecast_vintage_*.csv
   before new quarters are added, and the page scores it against what happened.
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

from common import DOCS_DIR, REPO_ROOT, load_history
import theme

MARKET_DIR = REPO_ROOT / "data" / "market_history"
COLORS = theme.PROVIDER
LABELS = {"AWS": "AWS", "Azure": "Azure (Azure revenue, as disclosed)",
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


def _quarters(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.PeriodIndex(df["quarter"], freq="Q").to_timestamp()
    df["t"] = (df["date"].dt.year - 2016) * 4 + df["date"].dt.quarter - 1
    return df.sort_values("t")


def _fin() -> pd.DataFrame:
    return _quarters(pd.read_csv(MARKET_DIR / "quarterly_financials.csv"))


def _azure() -> pd.DataFrame:
    """Azure revenue as Microsoft discloses it from FY27 (restated back to 2024Q3)."""
    az = pd.read_csv(MARKET_DIR / "azure_revenue.csv")
    az = az.rename(columns={"azure_revenue_musd": "revenue_musd"}).assign(provider="Azure")
    return _quarters(az)


def _series(df: pd.DataFrame, provider: str) -> pd.DataFrame:
    """The revenue series each provider is forecast on."""
    return _azure() if provider == "Azure" else df[df["provider"] == provider]


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
        d = _series(df, provider)
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
    Azure is excluded: its directly disclosed series has 9 quarters — too short
    for six rolling origins."""
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
    return ("<div class='table-wrap'><table class='tbl'><tr><th>Provider</th><th>Horizon</th>"
            "<th>Log-linear MAPE</th><th>Naive (last value) MAPE</th></tr>"
            + body + "</table></div>")


def momentum_index() -> tuple[pd.DataFrame, str]:
    prices = load_history()
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
    table = (f"<div class='table-wrap'><table class='tbl'>{head}{body}"
             f"<tr><td><b>AI Momentum Index (0–100)</b></td>{total}</tr></table></div>")
    return score, table


def buyers_guide() -> str:
    """The 'so what' — data-driven guidance for a GPU-compute buyer,
    every claim computed from the latest snapshot."""
    prices = load_history()
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


def latest_revenue(df: pd.DataFrame) -> dict:
    """provider -> (quarter, revenue $M, YoY %) on the series each provider is forecast on."""
    out = {}
    for p in ("AWS", "Azure", "GCP"):
        d = _series(df, p).dropna(subset=["revenue_musd"]).sort_values("t")
        last = d.iloc[-1]
        prior = d[d["t"] == last["t"] - 4]
        yoy = ((last["revenue_musd"] / prior["revenue_musd"].iloc[0] - 1) * 100
               if len(prior) else float("nan"))
        out[p] = (last["quarter"], last["revenue_musd"], yoy)
    return out


def scorecard(df: pd.DataFrame) -> str:
    """Score every frozen forecast vintage against the quarters reported since. Each vintage
    is scored on the basis it was fitted on (Azure: the Intelligent Cloud segment)."""
    actual = df.dropna(subset=["revenue_musd"]).set_index(["provider", "quarter"])["revenue_musd"]
    names = {"AWS": "AWS", "Azure": "Azure (Intelligent Cloud)", "GCP": "Google Cloud"}
    html = []
    for path in sorted(MARKET_DIR.glob("forecast_vintage_*.csv")):
        v = pd.read_csv(path)
        rows = []
        for r in v.itertuples():
            a = actual.get((r.provider, r.quarter))
            if a is None:
                continue
            rows.append({"provider": r.provider, "quarter": r.quarter, "h": r.h, "point": r.point_musd,
                         "lo": r.lo95_musd, "hi": r.hi95_musd, "actual": a,
                         "err": (r.point_musd - a) / a * 100, "naive": (r.naive_musd - a) / a * 100,
                         "inside": r.lo95_musd <= a <= r.hi95_musd})
        if not rows:
            continue
        n = len(rows)
        beat = sum(abs(x["err"]) < abs(x["naive"]) for x in rows)
        inside = sum(x["inside"] for x in rows)
        under = sum(x["err"] < 0 for x in rows)
        body = "".join(
            f"<tr><td>{names[x['provider']]}</td><td>{x['quarter']} "
            f"<span class='small'>({x['h']}q ahead)</span></td>"
            f"<td>${x['point']:,.0f}M <span class='small'>(${x['lo']:,.0f}–{x['hi']:,.0f}M)</span></td>"
            f"<td><b>${x['actual']:,.0f}M</b></td><td>{x['err']:+.1f}%</td><td>{x['naive']:+.1f}%</td>"
            f"<td>{'yes' if x['inside'] else 'no'}</td></tr>" for x in rows)
        last_q = max(x["quarter"] for x in rows)
        missing = set(v["provider"]) - {x["provider"] for x in rows if x["quarter"] == last_q}
        azure_note = (" Azure is scored on fewer quarters: the forecast was fitted on the "
                      "Intelligent Cloud segment, which Microsoft stopped reporting after 2026Q2."
                      if "Azure" in missing else "")
        html.append(f"""
<h3>How the {v['vintage'].iloc[0]} forecast did</h3>
<p>The forecast this page showed until new quarters arrived, frozen before they were added
(<code>{path.name}</code>) and scored against what was reported.</p>
<div class='table-wrap'><table class='tbl'><tr><th>Provider</th><th>Quarter</th><th>Forecast (95% band)</th>
<th>Actual</th><th>Forecast error</th><th>Naive error</th><th>In band?</th></tr>{body}</table></div>
<div class="note">The trend model beat the naive last-value forecast in <b>{beat} of {n}</b>
checks, but the actual landed inside its 95% band in <b>{inside} of {n}</b>, and {under} of {n}
came in above the forecast: cloud growth accelerated past its own eight-quarter trend. The band
is built from scatter around a fixed trend, so it has no room for the trend itself bending, which
is exactly what happened.{azure_note}</div>""")
    return "".join(html)


def pulse(df: pd.DataFrame, fits: dict) -> str:
    prices = load_history()
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

    lr = latest_revenue(df)
    quarters = {q for q, _, _ in lr.values()}
    qlabel = quarters.pop() if len(quarters) == 1 else "Latest-quarter"
    names = {"AWS": "AWS", "Azure": "Azure", "GCP": "Google Cloud"}
    rev_li = (f"<li>{qlabel} cloud revenue: " + " · ".join(
        f"{names[p]} ${v / 1000:,.1f}B ({g:+.0f}% YoY)" for p, (_, v, g) in lr.items())
        + (f"; Google Cloud is growing {lr['GCP'][2] / lr['AWS'][2]:.1f}× as fast as AWS"
           if lr["AWS"][2] > 0 else "") + ".</li>")
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
{rev_li}
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
the growth gap, not for betting. Azure is Microsoft's directly disclosed Azure revenue (from
fiscal 2027, restated back to 2024Q3), so it is Azure alone rather than the Intelligent Cloud
segment it replaced; all three are therefore closer to like for like than before, though Google
Cloud still includes Workspace.
{f"On these trends Google Cloud's quarterly revenue would cross AWS's around <b>{cross}</b>." if cross else ""}</div>
<h3>How good is this forecaster? (rolling-origin backtest)</h3>
<p>Before trusting any extrapolation, test it on quarters we already know the answer to:
re-fit the model at six past origins and score out-of-sample errors against a naive
last-value baseline.</p>
{backtest_table}
<p class="small">MAPE = mean absolute percentage error across 6 rolling origins.
The model needs to beat naive convincingly at 4 quarters out to justify the fan chart above;
1-quarter-ahead is nearly unbeatable by anything (revenue is highly persistent).</p>
{scorecard(df)}
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
