"""Build docs/regional.html — who wins where, and why.

Three independent regional lenses, each with its own data source:
1. Developer adoption by country/region (Stack Overflow survey microdata,
   derived by prepare_so_adoption.py) — demand-side proxy.
2. Analyst regional share series (Canalys/IDC China, Synergy Europe) compiled
   from public press releases — data/regional/analyst_regional_share.csv.
3. The narrative: why China is closed, why Europe consolidated to the big-3,
   why everywhere else looks the same — each claim tied to its source.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from common import DOCS_DIR, REPO_ROOT

REG_DIR = REPO_ROOT / "data" / "regional"
COLORS = {"AWS": "#FF9900", "Azure": "#0078D4", "GCP": "#34A853"}
CN_COLORS = {"Alibaba Cloud": "#FF6A00", "Huawei Cloud": "#C7000B",
             "Tencent Cloud": "#0052D9", "Baidu AI Cloud": "#2932E1",
             "Others (incl. AWS & Azure)": "#8b949e"}

NAV = ('<nav><a href="index.html">Live GPU Pricing</a>'
       '<a href="market.html">Market History</a>'
       '<a href="regional.html">Regional Deep-Dive</a>'
       '<a href="analysis.html">Event Study &amp; Experiments</a>'
       '<a href="outlook.html">Outlook &amp; Pulse</a></nav>')


def _period_date(p: str) -> pd.Timestamp:
    if p.startswith("FY"):
        return pd.Timestamp(f"{p[2:]}-07-01")
    if "H1" in p:
        return pd.Timestamp(f"{p[:4]}-04-01")
    if "H2" in p:
        return pd.Timestamp(f"{p[:4]}-10-01")
    return pd.PeriodIndex([p], freq="Q").to_timestamp()[0]


def fig_region_adoption():
    d = pd.read_csv(REG_DIR / "so_cloud_adoption_by_region.csv")
    d = d[d["year"] == d["year"].max()]
    long = d.melt(id_vars=["region", "respondents"],
                  value_vars=["aws_pct", "azure_pct", "gcp_pct"],
                  var_name="provider", value_name="pct")
    long["provider"] = long["provider"].str.replace("_pct", "").str.upper().replace(
        {"AWS": "AWS", "AZURE": "Azure", "GCP": "GCP"})
    order = d.sort_values("respondents", ascending=False)["region"].tolist()
    fig = px.bar(long, x="region", y="pct", color="provider", barmode="group",
                 color_discrete_map=COLORS, category_orders={"region": order},
                 labels={"pct": "% of developers who used it", "region": "", "provider": ""},
                 title=f"Developer adoption by region — Stack Overflow survey "
                       f"{d['year'].iloc[0]} (multi-select; n = "
                       f"{int(d['respondents'].sum()):,})")
    fig.update_layout(legend=dict(orientation="h", y=1.1), height=440)
    return fig


def fig_country_adoption():
    d = pd.read_csv(REG_DIR / "so_cloud_adoption_by_country.csv")
    d = d[d["year"] == d["year"].max()]
    top = d.sort_values("respondents", ascending=False).head(15)
    top["country"] = top["country"].replace({
        "United States of America": "United States",
        "United Kingdom of Great Britain and Northern Ireland": "United Kingdom"})
    long = top.melt(id_vars=["country"],
                    value_vars=["aws_pct", "azure_pct", "gcp_pct"],
                    var_name="provider", value_name="pct")
    long["provider"] = long["provider"].str.replace("_pct", "").map(
        {"aws": "AWS", "azure": "Azure", "gcp": "GCP"})
    fig = px.bar(long, y="country", x="pct", color="provider", barmode="group",
                 orientation="h", color_discrete_map=COLORS,
                 category_orders={"country": top["country"].tolist()[::-1]},
                 labels={"pct": "% of developers who used it", "country": "", "provider": ""},
                 title="Top-15 respondent countries — where Azure closes the gap "
                       "(Germany/UK) and where GCP punches above (India, Brazil)")
    fig.update_layout(legend=dict(orientation="h", y=1.06), height=620)
    return fig


def _analyst() -> pd.DataFrame:
    d = pd.read_csv(REG_DIR / "analyst_regional_share.csv")
    d["date"] = d["period"].map(_period_date)
    return d


def fig_china(analyst: pd.DataFrame):
    d = analyst[(analyst["region"] == "China") & (analyst["firm"] == "Canalys")]
    fig = go.Figure()
    for provider, seg in d.groupby("provider"):
        seg = seg.sort_values("date")
        fig.add_trace(go.Scatter(
            x=seg["date"], y=seg["share_pct"], name=provider,
            mode="lines+markers",
            line=dict(color=CN_COLORS.get(provider, "#8b949e"), width=2.5),
            hovertemplate="%{x|%Y Q%q}: %{y:.0f}%<extra>" + provider + "</extra>"))
    fig.update_layout(
        title="Mainland China cloud market share (Canalys) — every major player is Chinese; "
              "AWS & Azure live inside the grey 'Others' line",
        yaxis_title="market share %", height=460,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig


def fig_europe(analyst: pd.DataFrame):
    d = analyst[analyst["region"] == "Europe"].sort_values("date")
    fig = go.Figure()
    styles = {"Amazon+Microsoft+Google combined": ("#FF9900", "solid"),
              "European providers combined": ("#0969da", "dash")}
    for provider, (color, dash) in styles.items():
        seg = d[d["provider"] == provider]
        fig.add_trace(go.Scatter(
            x=seg["date"], y=seg["share_pct"], name=provider,
            mode="lines+markers", connectgaps=True,
            line=dict(color=color, dash=dash, width=2.5),
            hovertemplate="%{x|%Y}: %{y:.0f}%<extra>" + provider + "</extra>"))
    fig.update_layout(
        title="Europe (Synergy): local providers tripled revenue yet fell 29% → 15% of their "
              "own home market — the market grew ~6x around them",
        yaxis_title="share of European market %", height=420,
        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    return fig


CSS = """
 body{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}
 .wrap{max-width:1100px;margin:0 auto;padding:32px 20px 64px}
 h1{margin-bottom:4px} h2{margin-top:36px} .byline{color:#57606a;margin-top:0}
 nav{margin:10px 0 0} nav a{color:#0969da;margin-right:18px;font-weight:600;text-decoration:none}
 .chart{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:8px;margin:20px 0}
 .note{background:#fff8c5;border:1px solid #d4a72c66;border-radius:8px;padding:12px 16px;font-size:14px}
 .why{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:6px 22px;margin:20px 0}
 .why li{margin:10px 0;font-size:15px}
 footer{color:#57606a;font-size:13px;margin-top:40px}
 a{color:#0969da}
"""

WHY = """
<h2>Why the map looks like this</h2>
<div class="why"><ul>
<li><b>China is structurally closed, not just competitive.</b> Synergy (2024): "western cloud
providers are severely restricted from competing in the Chinese market" — all top-ten providers
in China are Chinese; foreign clouds must operate through local partnerships, which left AWS and
Azure inside a ~20% "others" bucket (Canalys 2021) and AWS at #5 in IaaS with 8.1% (IDC 2023).
(<a href="https://www.srgresearch.com/articles/cloud-is-a-global-market-apart-from-china">Synergy</a>,
<a href="https://www.theregister.com/2021/12/09/china_cloud_market/">Canalys/Register</a>,
<a href="https://kr-asia.com/alibaba-cloud-is-accelerating-its-reform-to-achieve-profitability-this-year">IDC/KrAsia</a>)</li>
<li><b>Europe lost share through scale, not regulation.</b> European providers tripled revenue
2017–2024 but their home-market share fell 29% → 15% because the market grew ~6x and the US big-3
now invest "~€10 billion every quarter" in European capex — "a game of scale… no European companies
have come close" (Synergy's John Dinsdale). Survivors (SAP, Deutsche Telekom at 2% each, OVHcloud,
Orange) settled into sovereignty/niche roles.
(<a href="https://www.srgresearch.com/articles/european-cloud-providers-local-market-share-now-holds-steady-at-15">Synergy 2025</a>)</li>
<li><b>Outside China, the market is strikingly uniform.</b> The big-3 hold the same ranking in the
US, Europe, APAC-ex-China and the rest of the world (Amazon 32 / Microsoft 23 / Google 12, ex-China,
2024Q2); local champions (Fujitsu/NTT in Japan, Naver/KT in Korea, Telstra in Australia) only reach
the top-6. (<a href="https://www.srgresearch.com/articles/cloud-is-a-global-market-apart-from-china">Synergy</a>)</li>
<li><b>The developer data adds texture revenue can't.</b> Azure's adoption gap vs AWS nearly closes
in Germany and the UK (Microsoft's enterprise base), while GCP over-indexes across India, Brazil and
Africa — consistent with Microsoft strength in European enterprises and Google strength with
developer-led, mobile-first markets.</li>
<li><b>China's growth is now AI-driven and consolidating.</b> Spending re-accelerated to +16% YoY
($11.6B, 2025Q1) on AI demand "despite US export restrictions on advanced semiconductor access" —
the AI cycle is happening on both sides of the wall, with different chips.
(<a href="https://www.scmp.com/tech/big-tech/article/3317760/chinas-cloud-services-spending-hits-us116-billion-first-quarter-ai-related-demand">Canalys/SCMP</a>)</li>
</ul></div>
"""


def build() -> None:
    analyst = _analyst()
    figs = [fig_region_adoption(), fig_country_adoption(),
            fig_china(analyst), fig_europe(analyst)]
    charts, include_js = [], "cdn"
    for f in figs:
        charts.append(f.to_html(full_html=False, include_plotlyjs=include_js))
        include_js = False

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Regional Deep-Dive — Who Wins Where, and Why</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Who wins where, and why</h1>
<p class="byline">Regional cloud market structure from three independent lenses: developer
adoption (Stack Overflow survey microdata), analyst regional share series (Canalys, IDC, Synergy
press releases), and infrastructure footprint (see the
<a href="index.html">live tracker map</a>).</p>
{NAV}
<h2>Lens 1 — developer adoption by region</h2>
<div class="chart">{charts[0]}</div>
<div class="chart">{charts[1]}</div>
<div class="note"><b>What this measures.</b> Share of survey respondents who report having worked
with each platform (multi-select — rows do not sum to 100%). It proxies developer mindshare, not
revenue: enterprise spend (where Azure is strongest) is under-represented by developer surveys,
which is itself part of the story. Derivation:
<a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis/blob/main/pricing_tracker/prepare_so_adoption.py">prepare_so_adoption.py</a>;
countries with ≥100 respondents only.</div>
<h2>Lens 2 — the two markets that break the pattern</h2>
<div class="chart">{charts[2]}</div>
<div class="chart">{charts[3]}</div>
{WHY}
<footer>Part of the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis">Multi-Cloud AI Infrastructure Market Analysis</a> project
· Che-Wei (Jarvis) Lee · built {built}</footer>
</div></body></html>"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "regional.html").write_text(html, encoding="utf-8")
    print(f"regional report -> {DOCS_DIR / 'regional.html'}")


if __name__ == "__main__":
    build()
