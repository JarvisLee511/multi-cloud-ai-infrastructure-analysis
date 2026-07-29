"""Build docs/analysis.html — causal-flavored analyses on the market data.

1. Interrupted time-series (event study) around the ChatGPT launch (2022-11-30):
   fit a log-linear pre-trend on 2021Q1-2022Q4 segment revenue (AWS, Google
   Cloud), project it forward as the counterfactual, and compare with actuals.
   Azure is shown via Microsoft's own disclosed growth metric instead (the
   Intelligent Cloud series has a 2024Q3 definition break that invalidates ITS).
2. The capex supercycle: firm-wide quarterly capex for the three parents.
3. A designed A/B experiment (clearly labeled SIMULATED) demonstrating power
   analysis, SRM check, and a two-proportion z-test. See ab_experiment.py.

This is observational data: the ITS estimates describe deviation from pre-trend,
not a clean causal effect — confounders (2023 'optimization' slowdown, rate
environment) are named in the page itself.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import ab_experiment
from common import DOCS_DIR, REPO_ROOT

MARKET_DIR = REPO_ROOT / "data" / "market_history"
COLORS = {"AWS": "#FF9900", "Azure": "#0078D4", "GCP": "#34A853"}
PARENT_COLORS = {"Amazon": "#FF9900", "Microsoft": "#0078D4", "Alphabet": "#34A853"}
CHATGPT = pd.Timestamp("2022-11-30")
PRE_WINDOW = ("2021Q1", "2022Q4")

NAV = ('<nav><a href="index.html">Live GPU Pricing</a>'
       '<a href="market.html">Market History</a>'
       '<a href="regional.html">Regional Deep-Dive</a>'
       '<a href="analysis.html">Event Study &amp; Experiments</a>'
       '<a href="outlook.html">Outlook &amp; Pulse</a></nav>')


def _fin() -> pd.DataFrame:
    df = pd.read_csv(MARKET_DIR / "quarterly_financials.csv")
    df["date"] = pd.PeriodIndex(df["quarter"], freq="Q").to_timestamp()
    df["t"] = (df["date"].dt.year - 2016) * 4 + df["date"].dt.quarter - 1
    return df


def event_study(df: pd.DataFrame, provider: str) -> tuple[go.Figure, dict]:
    d = df[(df["provider"] == provider) & df["revenue_musd"].notna()].sort_values("t")
    pre = d[(d["quarter"] >= PRE_WINDOW[0]) & (d["quarter"] <= PRE_WINDOW[1])]
    post = d[d["date"] > CHATGPT]
    slope, intercept = np.polyfit(pre["t"], np.log(pre["revenue_musd"]), 1)
    d = d[d["quarter"] >= PRE_WINDOW[0]].copy()
    d["counterfactual"] = np.exp(intercept + slope * d["t"])

    post_cf = d[d["date"] > CHATGPT]
    lift_musd = (post_cf["revenue_musd"] - post_cf["counterfactual"]).sum()
    last = post_cf.iloc[-1]
    stats = {
        "pre_growth_qoq": math_growth(slope),
        "cum_lift_busd": lift_musd / 1000,
        "last_q": last["quarter"],
        "last_gap_pct": (last["revenue_musd"] / last["counterfactual"] - 1) * 100,
    }

    label = "Google Cloud" if provider == "GCP" else provider
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["revenue_musd"], name=f"{label} actual",
        mode="lines+markers", line=dict(color=COLORS[provider], width=2.5),
        hovertemplate="%{x|%Y Q%q}: $%{y:,.0f}M<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["counterfactual"],
        name="counterfactual (pre-ChatGPT trend continued)",
        mode="lines", line=dict(color="#8b949e", width=2, dash="dash"),
        hovertemplate="%{x|%Y Q%q}: $%{y:,.0f}M<extra></extra>"))
    fig.add_vline(x=CHATGPT, line_dash="dot", line_color="#d1242f")
    fig.add_annotation(x=CHATGPT, yref="paper", y=1.05, text="ChatGPT launch",
                       showarrow=False, font=dict(size=11, color="#d1242f"))
    fig.update_layout(
        title=(f"{label}: actual revenue vs continued pre-trend "
               f"(fit {PRE_WINDOW[0]}–{PRE_WINDOW[1]})"),
        yaxis_title="revenue $M / quarter", height=440,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig, stats


def math_growth(slope: float) -> float:
    return (np.exp(slope) - 1) * 100


def fig_growth_event(df: pd.DataFrame) -> tuple[go.Figure, dict]:
    """YoY revenue growth around the ChatGPT launch — the growth-rate
    event view: deceleration into the 2023 optimization trough, then
    re-acceleration as AI workloads scaled."""
    fig = go.Figure()
    stats = {}
    series = {}
    for provider in ("AWS", "GCP"):
        d = df[(df["provider"] == provider) & df["revenue_musd"].notna()].copy()
        d["yoy"] = d["revenue_musd"].pct_change(4) * 100
        series[provider] = d.dropna(subset=["yoy"])[["date", "quarter", "yoy"]]
    az = pd.read_csv(MARKET_DIR / "azure_yoy_growth.csv")
    az["date"] = pd.PeriodIndex(az["quarter"], freq="Q").to_timestamp()
    az["yoy"] = az["azure_yoy_growth_pct"]
    series["Azure"] = az[["date", "quarter", "yoy"]]

    names = {"AWS": "AWS", "GCP": "Google Cloud",
             "Azure": "Azure (as disclosed by Microsoft)"}
    for provider, d in series.items():
        d = d[d["quarter"] >= "2021Q1"]
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["yoy"], name=names[provider], mode="lines+markers",
            line=dict(color=COLORS[provider], width=2.5),
            hovertemplate="%{x|%Y Q%q}: %{y:.0f}%<extra></extra>"))
        post = d[d["date"] > CHATGPT]
        trough = post.loc[post["yoy"].idxmin()]
        latest = post.iloc[-1]
        stats[provider] = {"trough_q": trough["quarter"], "trough": trough["yoy"],
                           "latest_q": latest["quarter"], "latest": latest["yoy"]}
    fig.add_vline(x=CHATGPT, line_dash="dot", line_color="#d1242f")
    fig.add_annotation(x=CHATGPT, yref="paper", y=1.05, text="ChatGPT launch",
                       showarrow=False, font=dict(size=11, color="#d1242f"))
    fig.update_layout(
        title="Revenue growth bent twice: down into the 2023 cost-optimization trough, "
              "then back up as AI workloads scaled",
        yaxis_title="YoY revenue growth %", height=470,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig, stats


def fig_azure_growth():
    az = pd.read_csv(MARKET_DIR / "azure_yoy_growth.csv")
    az["date"] = pd.PeriodIndex(az["quarter"], freq="Q").to_timestamp()
    az = az[az["quarter"] >= "2020Q1"]
    fig = go.Figure(go.Scatter(
        x=az["date"], y=az["azure_yoy_growth_pct"], mode="lines+markers",
        line=dict(color=COLORS["Azure"], width=2.5),
        hovertemplate="%{x|%Y Q%q}: %{y:.0f}%<extra></extra>"))
    fig.add_vline(x=CHATGPT, line_dash="dot", line_color="#d1242f")
    fig.add_annotation(x=CHATGPT, yref="paper", y=1.05, text="ChatGPT launch",
                       showarrow=False, font=dict(size=11, color="#d1242f"))
    fig.update_layout(
        title="Azure YoY growth as disclosed by Microsoft — deceleration bottomed two quarters "
              "after ChatGPT, then re-accelerated 26% → 40%",
        yaxis_title="Azure & other cloud services, YoY %", height=400,
        showlegend=False, hovermode="x unified")
    return fig


def fig_capex():
    cap = pd.read_csv(MARKET_DIR / "quarterly_capex.csv")
    cap["date"] = pd.PeriodIndex(cap["quarter"], freq="Q").to_timestamp()
    fig = go.Figure()
    for company, col in (("Amazon", "amazon_capex_musd"),
                         ("Microsoft", "microsoft_capex_musd"),
                         ("Alphabet", "alphabet_capex_musd")):
        fig.add_trace(go.Scatter(
            x=cap["date"], y=cap[col], name=company, stackgroup="capex",
            line=dict(color=PARENT_COLORS[company], width=1),
            hovertemplate="%{x|%Y Q%q}: $%{y:,.0f}M<extra>" + company + "</extra>"))
    fig.add_vline(x=CHATGPT, line_dash="dot", line_color="#d1242f")
    fig.add_annotation(x=CHATGPT, yref="paper", y=1.05, text="ChatGPT launch",
                       showarrow=False, font=dict(size=11, color="#d1242f"))
    total_now = cap.iloc[-1][["amazon_capex_musd", "microsoft_capex_musd",
                              "alphabet_capex_musd"]].sum()
    fig.update_layout(
        title=(f"The capex supercycle — combined quarterly capex hit "
               f"${total_now/1000:,.0f}B in {cap.iloc[-1]['quarter']} "
               "(firm-wide, from SEC XBRL)"),
        yaxis_title="capex $M / quarter (stacked)", height=460,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig


def ab_section() -> str:
    r = ab_experiment.run()
    decision = ("<b style='color:#1a7f37'>Ship it</b> — the lift is statistically "
                "significant and the CI lower bound exceeds zero."
                if r["significant"] and r["ci_pp"][0] > 0 else
                "<b style='color:#d1242f'>Do not ship yet</b> — effect not distinguishable "
                "from zero at α=0.05.")
    return f"""
<h2>Designed experiment: pricing-page A/B test <span class="sim">SIMULATED DATA</span></h2>
<p><b>Scenario.</b> A cloud provider tests whether adding a live per-GPU price-comparison
widget to the pricing page lifts trial sign-ups vs the static price list.
Real experiment data is proprietary, so outcomes here are <b>simulated</b> (numpy,
fixed seed) — the point is the design discipline, not the numbers.</p>
<table class="tbl">
<tr><th>Design</th><th>Value</th></tr>
<tr><td>Hypothesis</td><td>price-comparison widget raises sign-up conversion (baseline 4.0%)</td></tr>
<tr><td>Minimum detectable effect</td><td>+0.5pp (α=0.05 two-sided, power 0.80)</td></tr>
<tr><td>Required sample (power analysis)</td><td>{r['n_target_per_arm']:,} per arm → {r['days_needed']} days at ~1,400 visitors/day</td></tr>
<tr><td>Sample-ratio mismatch check</td><td>χ²={r['srm_chi2']:.2f} → {'OK (no SRM)' if r['srm_ok'] else 'FAILED — investigate assignment'}</td></tr>
<tr><th>Result</th><th>Value</th></tr>
<tr><td>Control conversion</td><td>{r['cvr_control']:.2%} ({r['conv_control']:,}/{r['n_control']:,})</td></tr>
<tr><td>Treatment conversion</td><td>{r['cvr_treatment']:.2%} ({r['conv_treatment']:,}/{r['n_treatment']:,})</td></tr>
<tr><td>Lift</td><td>{r['lift_pp']:+.2f}pp (95% CI {r['ci_pp'][0]:+.2f} to {r['ci_pp'][1]:+.2f}pp)</td></tr>
<tr><td>Two-proportion z-test</td><td>z={r['z']:.2f}, p={r['p_value']:.4f}</td></tr>
<tr><td>Decision</td><td>{decision}</td></tr>
</table>
<p class="small">Caveats handled in the design: novelty effects argue for running the full
pre-committed duration even after early significance; the SRM check guards against broken
randomization; conversion is a binomial metric so no variance-reduction (CUPED) was needed.
Code: <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis/blob/main/pricing_tracker/ab_experiment.py">ab_experiment.py</a>.</p>
"""


CSS = """
 body{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}
 .wrap{max-width:1100px;margin:0 auto;padding:32px 20px 64px}
 h1{margin-bottom:4px} h2{margin-top:36px} .byline{color:#57606a;margin-top:0}
 nav{margin:10px 0 0} nav a{color:#0969da;margin-right:18px;font-weight:600;text-decoration:none}
 .chart{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:8px;margin:20px 0}
 .note{background:#fff8c5;border:1px solid #d4a72c66;border-radius:8px;padding:12px 16px;font-size:14px}
 .sim{background:#d1242f;color:#fff;font-size:12px;padding:2px 8px;border-radius:6px;vertical-align:middle}
 .tbl{border-collapse:collapse;background:#fff;border:1px solid #d0d7de;border-radius:10px;font-size:14px}
 .tbl th,.tbl td{border:1px solid #d0d7de;padding:7px 12px;text-align:left}
 .tbl th{background:#f6f8fa}
 .small{font-size:13px;color:#57606a}
 footer{color:#57606a;font-size:13px;margin-top:40px}
 a{color:#0969da}
 /* a11y + layout safety — slop-test gates 26, 34, 51 (no CSS motion here, so 27 passes trivially) */
 html,body{overflow-x:clip}
 h1,h2,h3{overflow-wrap:anywhere;min-width:0}
 a:focus-visible,button:focus-visible,select:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:2px solid #0969da;outline-offset:2px;border-radius:4px}
"""


def build() -> None:
    df = _fin()
    fig_g, gs = fig_growth_event(df)
    fig_aws, s_aws = event_study(df, "AWS")
    fig_gcp, s_gcp = event_study(df, "GCP")
    figs = [fig_g, fig_aws, fig_gcp, fig_capex()]

    charts, include_js = [], "cdn"
    for f in figs:
        charts.append(f.to_html(full_html=False, include_plotlyjs=include_js))
        include_js = False

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Event Study & Experiments — Cloud Market Analysis</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Did ChatGPT bend the cloud revenue curve?</h1>
<p class="byline">Interrupted time-series around the ChatGPT launch, the capex supercycle,
and a designed A/B experiment.</p>
{NAV}
<h2>The growth-rate event view</h2>
<p>Growth decelerated INTO the AI era first — enterprises were cutting cloud bills through 2023 —
and then bent back up as AI workloads scaled:
AWS bottomed at <b>{gs['AWS']['trough']:.0f}%</b> YoY in {gs['AWS']['trough_q']} and is back to
<b>{gs['AWS']['latest']:.0f}%</b>; Google Cloud {gs['GCP']['trough']:.0f}% → {gs['GCP']['latest']:.0f}%;
Azure (Microsoft's own metric) {gs['Azure']['trough']:.0f}% → {gs['Azure']['latest']:.0f}%.
A growth re-acceleration of this size, simultaneous across all three providers, two years into
a maturing market, is the clearest fingerprint of the AI demand shock.</p>
<div class="chart">{charts[0]}</div>
<h2>Sensitivity: level counterfactual vs the boom-era path</h2>
<p>A different counterfactual gives a humbler answer. Fit the 2021–22 boom-era trend
({PRE_WINDOW[0]}–{PRE_WINDOW[1]}, log-linear) and project it forward: through {s_gcp['last_q']},
Google Cloud sits <b>{s_gcp['last_gap_pct']:.0f}%</b> and AWS <b>{s_aws['last_gap_pct']:.0f}%</b>
relative to that path — i.e. even the AI surge has not restored boom-era compounding;
it reversed the 2023 slide. The conclusion depends on the counterfactual you choose,
which is exactly why both are shown.</p>
<div class="chart">{charts[1]}</div>
<div class="chart">{charts[2]}</div>
<div class="note"><b>Why this is not a clean causal estimate.</b> One event, no control group:
the 2023 enterprise cost-optimization wave and the rate environment are confounders, the level
counterfactual assumes the 2021–22 growth path would have persisted, Google Cloud includes
Workspace, and Azure is excluded from the level ITS because Microsoft's segment was re-defined
mid-post-period (its own disclosed growth metric is used instead). This is an interrupted
time-series — a descriptive deviation-from-trend, the honest observational cousin of an A/B test.</div>
<h2>The capex supercycle</h2>
<div class="chart">{charts[3]}</div>
<p class="small">Firm-wide capex from SEC XBRL (not cloud-segment-only; excludes finance-lease
additions — see the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis/blob/main/data/market_history/README.md">data README</a>).</p>
{ab_section()}
<footer>Part of the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis">Multi-Cloud AI Infrastructure Market Analysis</a> project
· Che-Wei (Jarvis) Lee · built {built}</footer>
</div></body></html>"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "analysis.html").write_text(html, encoding="utf-8")
    print(f"analysis report -> {DOCS_DIR / 'analysis.html'}")
    print(f"AWS: gap {s_aws['last_gap_pct']:+.1f}% / cum ${s_aws['cum_lift_busd']:+,.1f}B | "
          f"GCP: gap {s_gcp['last_gap_pct']:+.1f}% / cum ${s_gcp['cum_lift_busd']:+,.1f}B")


if __name__ == "__main__":
    build()
