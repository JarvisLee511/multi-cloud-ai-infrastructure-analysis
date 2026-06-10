"""Build docs/market.html — ten years of cloud market history (2016–2026).

Sources: data/market_history/*.csv (SEC filings row-by-row + analyst press
releases). The chart annotations carry the comparability caveats: Azure rows are
Microsoft's Intelligent Cloud segment (a proxy — Azure-only revenue is never
disclosed), and that segment was re-defined at 2024Q3, so the series shows an
explicit break there.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from common import DOCS_DIR, REPO_ROOT

MARKET_DIR = REPO_ROOT / "data" / "market_history"
COLORS = {"AWS": "#FF9900", "Azure": "#0078D4", "GCP": "#34A853"}
LABELS = {"AWS": "AWS", "Azure": "Azure (Intelligent Cloud segment)",
          "GCP": "Google Cloud"}
MSFT_BREAK = pd.Timestamp("2024-07-01")  # FY25 segment re-definition
EVENTS = [
    (pd.Timestamp("2020-03-01"), "COVID-19"),
    (pd.Timestamp("2022-11-30"), "ChatGPT launch"),
]


def _load() -> pd.DataFrame:
    df = pd.read_csv(MARKET_DIR / "quarterly_financials.csv")
    df["date"] = pd.PeriodIndex(df["quarter"], freq="Q").to_timestamp()
    return df.sort_values(["provider", "date"])


def _add_events(fig, df_max_y=None):
    for when, label in EVENTS:
        fig.add_vline(x=when, line_dash="dot", line_color="#8b949e")
        fig.add_annotation(x=when, yref="paper", y=1.04, text=label,
                           showarrow=False, font=dict(size=11, color="#57606a"))
    return fig


def _provider_traces(fig, d: pd.DataFrame, ycol: str, provider: str,
                     hovertemplate: str):
    """One line per provider; Azure is split into solid/dashed at the
    2024Q3 segment re-definition so the basis change is visible."""
    color = COLORS[provider]
    segments = [(d, "solid", LABELS[provider], True)]
    if provider == "Azure":
        segments = [
            (d[d["date"] < MSFT_BREAK], "solid", LABELS["Azure"], True),
            (d[d["date"] >= MSFT_BREAK], "dash",
             "Azure (re-defined segment, FY25 basis)", True),
        ]
    for seg, dash, name, show in segments:
        fig.add_trace(go.Scatter(
            x=seg["date"], y=seg[ycol], name=name, legendgroup=provider,
            showlegend=show, mode="lines",
            line=dict(color=color, dash=dash, width=2.5),
            hovertemplate=hovertemplate))
    return fig


def fig_revenue(df: pd.DataFrame):
    fig = go.Figure()
    for provider in ("AWS", "Azure", "GCP"):
        d = df[(df["provider"] == provider) & df["revenue_musd"].notna()]
        _provider_traces(fig, d, "revenue_musd", provider,
                         "%{x|%Y Q%q}: $%{y:,.0f}M<extra></extra>")
    fig.update_layout(
        title="Quarterly cloud revenue, 2016–2026 (USD millions, from SEC filings)",
        yaxis_title="revenue, $M / quarter", height=520,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return _add_events(fig)


def fig_growth(df: pd.DataFrame):
    fig = go.Figure()
    for provider in ("AWS", "GCP"):
        d = df[(df["provider"] == provider) & df["revenue_musd"].notna()].copy()
        d["yoy"] = d["revenue_musd"].pct_change(4) * 100
        d = d.dropna(subset=["yoy"])
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["yoy"], name=f"{LABELS[provider]} (computed YoY)",
            mode="lines", line=dict(color=COLORS[provider], width=2.5),
            hovertemplate="%{x|%Y Q%q}: %{y:.0f}%<extra></extra>"))
    az = pd.read_csv(MARKET_DIR / "azure_yoy_growth.csv")
    az["date"] = pd.PeriodIndex(az["quarter"], freq="Q").to_timestamp()
    fig.add_trace(go.Scatter(
        x=az["date"], y=az["azure_yoy_growth_pct"],
        name="Azure & other cloud services (as disclosed by Microsoft)",
        mode="lines", line=dict(color=COLORS["Azure"], width=2.5),
        hovertemplate="%{x|%Y Q%q}: %{y:.0f}%<extra></extra>"))
    fig.update_layout(
        title="Revenue growth, year over year — the AI inflection is visible after 2023",
        yaxis_title="YoY growth %", height=480,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return _add_events(fig)


def fig_margin(df: pd.DataFrame):
    fig = go.Figure()
    for provider in ("AWS", "Azure", "GCP"):
        d = df[(df["provider"] == provider)
               & df["operating_income_musd"].notna()
               & df["revenue_musd"].notna()].copy()
        d["margin"] = d["operating_income_musd"] / d["revenue_musd"] * 100
        _provider_traces(fig, d, "margin", provider,
                         "%{x|%Y Q%q}: %{y:.0f}%<extra></extra>")
    fig.add_hline(y=0, line_color="#8b949e", line_width=1)
    fig.update_layout(
        title="Operating margin — Google Cloud's climb from deep loss to profit",
        yaxis_title="operating margin %", height=480,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return _add_events(fig)


def fig_share():
    path = MARKET_DIR / "market_share.csv"
    if not path.exists():
        return None
    share = pd.read_csv(path)
    share["date"] = pd.PeriodIndex(share["quarter"], freq="Q").to_timestamp()
    fig = go.Figure()
    styles = {"Synergy": ("solid", 2.5), "Canalys": ("dot", 1.8)}
    for firm, (dash, width) in styles.items():
        d = share[share["firm"] == firm].sort_values("date")
        for provider in ("AWS", "Azure", "GCP"):
            s = d[d["provider"] == provider]
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=s["date"], y=s["share_pct"], name=f"{provider} ({firm})",
                legendgroup=provider, mode="lines+markers", connectgaps=True,
                line=dict(color=COLORS[provider], dash=dash, width=width),
                marker=dict(size=6),
                hovertemplate="%{x|%Y Q%q}: %{y:.0f}% (" + firm + ")<extra></extra>"))
    fig.update_layout(
        title="Worldwide cloud-infrastructure market share — analyst estimates "
              "(solid = Synergy, dotted = Canalys; firms differ and are never mixed)",
        yaxis_title="market share %", height=500,
        legend=dict(orientation="h", y=1.14), hovermode="x unified")
    return _add_events(fig)


def kpis(df: pd.DataFrame) -> str:
    latest_q = df["quarter"].max()
    cards = []
    for provider in ("AWS", "Azure", "GCP"):
        d = df[df["provider"] == provider].sort_values("date")
        now = d[d["quarter"] == latest_q]
        if now.empty:
            continue
        rev = now["revenue_musd"].iloc[0]
        prior = d[d["date"] == now["date"].iloc[0] - pd.DateOffset(years=1)]
        yoy = (f"{(rev / prior['revenue_musd'].iloc[0] - 1) * 100:+.0f}% YoY"
               if not prior.empty else "")
        cards.append(
            f"<div class='card'><h3 style='color:{COLORS[provider]}'>{LABELS[provider]}</h3>"
            f"<p class='big'>${rev / 1000:,.1f}B</p>"
            f"<p class='sub'>{latest_q} revenue · {yoy}</p></div>")
    return "<div class='cards'>" + "".join(cards) + "</div>"


CSS = """
 body{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}
 .wrap{max-width:1100px;margin:0 auto;padding:32px 20px 64px}
 h1{margin-bottom:4px} .byline{color:#57606a;margin-top:0}
 nav{margin:10px 0 0} nav a{color:#0969da;margin-right:18px;font-weight:600;text-decoration:none}
 .cards{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}
 .card{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:16px 22px;flex:1;min-width:200px}
 .card h3{margin:0 0 6px;font-size:15px} .card p{margin:2px 0;color:#57606a;font-size:14px}
 .card .big{font-size:30px;font-weight:700;color:#1f2328;margin-top:8px}
 .card .sub{font-size:12px}
 .chart{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:8px;margin:20px 0}
 .note{background:#fff8c5;border:1px solid #d4a72c66;border-radius:8px;padding:12px 16px;font-size:14px}
 footer{color:#57606a;font-size:13px;margin-top:40px}
 a{color:#0969da}
"""


def build() -> None:
    df = _load()
    figs = [fig_revenue(df), fig_growth(df), fig_margin(df)]
    share = fig_share()
    if share is not None:
        figs.insert(0, share)

    charts_html, include_js = [], "cdn"
    for fig in figs:
        charts_html.append(fig.to_html(full_html=False, include_plotlyjs=include_js))
        include_js = False

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cloud Market History 2016–2026 — AWS · Azure · GCP</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Cloud Market History, 2016–2026</h1>
<p class="byline">Ten years of the cloud wars, compiled quarter-by-quarter from SEC filings
(every row in the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis/tree/main/data/market_history">dataset</a> carries its source URL).</p>
<nav><a href="index.html">Live GPU Pricing</a><a href="market.html">Market History</a><a href="regional.html">Regional Deep-Dive</a><a href="analysis.html">Event Study &amp; Experiments</a><a href="outlook.html">Outlook &amp; Pulse</a></nav>
{kpis(df)}
{"".join(f"<div class='chart'>{c}</div>" for c in charts_html)}
<div class="note"><b>Comparability.</b>
AWS is a clean reportable segment (unchanged since 2015).
<b>Azure lines show Microsoft's Intelligent Cloud segment</b> — Microsoft has never
disclosed quarterly absolute Azure revenue; the growth chart uses Microsoft's own
disclosed "Azure and other cloud services" YoY rate instead. The dashed portion marks the
FY25 segment re-definition (2024Q3) — not comparable with the solid line.
Google Cloud includes Workspace; quarterly disclosure starts 2018Q4, operating income 2019Q4
(Apr-2023 recast applied to 2022). Market share, where shown, is an analyst estimate
(Synergy/Canalys press releases), not a filing. Full caveats:
<a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis/blob/main/data/market_history/README.md">data README</a>.</div>
<footer>Part of the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis">Multi-Cloud AI Infrastructure Market Analysis</a> project
· Che-Wei (Jarvis) Lee · built {built}</footer>
</div></body></html>"""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "market.html").write_text(html, encoding="utf-8")
    print(f"market report -> {DOCS_DIR / 'market.html'}")


if __name__ == "__main__":
    build()
