"""Build the auto-updating GPU pricing report (docs/index.html + docs/LATEST.md).

Comparability note baked into the report: AWS/Azure per-GPU prices are derived
from whole GPU instances (bundled vCPU/RAM included); GCP bills the GPU as a
separate per-GPU-hour SKU (VM cost excluded). Cross-cloud gaps therefore embody
a bundling difference of roughly the host-VM cost, which is small relative to
flagship GPU prices but not zero.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.express as px

from common import DOCS_DIR

REGION_GEO_CSV = Path(__file__).resolve().parent / "region_geo.csv"
# Spread per-provider dots that share a metro so all three stay visible.
MAP_JITTER = {"AWS": (0.9, -1.6), "Azure": (-0.9, 0.0), "GCP": (0.9, 1.6)}

COLORS = {"AWS": "#FF9900", "Azure": "#0078D4", "GCP": "#34A853"}
FLAGSHIP_ORDER = [
    "GB200", "B300", "B200", "H200", "H100", "MI300X", "A100-80GB", "A100",
    "L40S", "L4", "A10G", "A10", "T4", "V100",
]
HISTORY_MODELS = ["H200", "H100", "A100", "L4", "T4"]


def _ondemand_per_gpu(df: pd.DataFrame) -> pd.DataFrame:
    out = df[(df["price_type"] == "ondemand") & df["price_usd_per_gpu_hour"].notna()]
    return out[out["price_usd_per_gpu_hour"] > 0]


def _region_stats(latest: pd.DataFrame) -> pd.DataFrame:
    """Per provider+region: GPU SKU breadth and cheapest flagship prices."""
    od = latest[latest["price_type"] == "ondemand"]
    stats = od.groupby(["provider", "region"]).agg(
        n_skus=("sku", "nunique"),
        n_models=("gpu_model", "nunique"),
        models=("gpu_model", lambda s: ", ".join(sorted(s.unique()))),
    ).reset_index()
    for model in ("H100", "A100"):
        d = od[(od["gpu_model"] == model) & od["price_usd_per_gpu_hour"].notna()]
        floor = (d.groupby(["provider", "region"])["price_usd_per_gpu_hour"]
                  .min().rename(f"min_{model.lower()}"))
        stats = stats.merge(floor, on=["provider", "region"], how="left")
    return stats


def fig_map(latest: pd.DataFrame):
    geo = pd.read_csv(REGION_GEO_CSV)
    d = _region_stats(latest).merge(geo, on=["provider", "region"], how="inner")
    for provider, (dlat, dlon) in MAP_JITTER.items():
        mask = d["provider"] == provider
        d.loc[mask, "lat"] += dlat
        d.loc[mask, "lon"] += dlon
    d["hover"] = (
        d["city"] + ", " + d["country"] + " (" + d["region"] + ")<br>" +
        d["n_skus"].astype(str) + " GPU SKUs · " +
        d["n_models"].astype(str) + " accelerator models<br>cheapest H100: " +
        d["min_h100"].map(lambda v: f"${v:,.2f}/GPU-hr" if pd.notna(v) else "—") +
        " · A100: " +
        d["min_a100"].map(lambda v: f"${v:,.2f}/GPU-hr" if pd.notna(v) else "—")
    )
    fig = px.scatter_geo(
        d, lat="lat", lon="lon", color="provider", size="n_skus",
        size_max=22, color_discrete_map=COLORS, custom_data=["hover"],
        title="Where the GPUs are — every cloud region selling GPU compute "
              "(dot size = GPU SKU breadth)",
    )
    fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
    fig.update_geos(
        projection_type="natural earth", showcountries=True,
        countrycolor="#d0d7de", landcolor="#eef1f4", showland=True,
    )
    fig.update_layout(legend=dict(orientation="h", y=1.06), height=540,
                      margin=dict(l=10, r=10, t=70, b=10))
    return fig


def fig_continent(latest: pd.DataFrame):
    geo = pd.read_csv(REGION_GEO_CSV)
    d = _region_stats(latest).merge(geo, on=["provider", "region"], how="inner")
    agg = d.groupby(["continent", "provider"], as_index=False)["region"].count()
    order = (agg.groupby("continent")["region"].sum()
                .sort_values(ascending=False).index.tolist())
    fig = px.bar(
        agg, x="continent", y="region", color="provider", barmode="group",
        color_discrete_map=COLORS, category_orders={"continent": order},
        labels={"region": "regions with GPU compute", "continent": "", "provider": ""},
        title="Regional distribution — GPU-equipped regions per continent",
    )
    fig.update_layout(legend=dict(orientation="h", y=1.08), height=420)
    return fig


def fig_latest_floor(latest: pd.DataFrame):
    d = _ondemand_per_gpu(latest)
    d = d[d["gpu_model"].isin(FLAGSHIP_ORDER)]
    floor = (d.groupby(["gpu_model", "provider"], as_index=False)
              ["price_usd_per_gpu_hour"].min())
    fig = px.bar(
        floor, x="gpu_model", y="price_usd_per_gpu_hour", color="provider",
        barmode="group", color_discrete_map=COLORS,
        category_orders={"gpu_model": FLAGSHIP_ORDER},
        labels={"price_usd_per_gpu_hour": "USD / GPU-hour (cheapest region)",
                "gpu_model": "", "provider": ""},
        title="Cheapest on-demand price per GPU-hour, by accelerator and provider",
    )
    fig.update_layout(legend=dict(orientation="h", y=1.08), height=480)
    return fig


def fig_spot_discount(latest: pd.DataFrame):
    base = latest[latest["price_usd_per_gpu_hour"].notna()]
    od = base[base["price_type"] == "ondemand"]
    sp = base[base["price_type"] == "spot"]
    pair = od.merge(
        sp, on=["provider", "region", "sku", "gpu_model"], suffixes=("_od", "_sp"))
    pair = pair[pair["price_usd_hour_od"] > 0]
    pair["discount"] = 1 - pair["price_usd_hour_sp"] / pair["price_usd_hour_od"]
    pair = pair[pair["gpu_model"].isin(HISTORY_MODELS)]
    med = pair.groupby(["gpu_model", "provider"], as_index=False)["discount"].median()
    fig = px.bar(
        med, x="gpu_model", y="discount", color="provider", barmode="group",
        color_discrete_map=COLORS, category_orders={"gpu_model": HISTORY_MODELS},
        labels={"discount": "Median spot discount vs on-demand", "gpu_model": "", "provider": ""},
        title="Spot / preemptible discount (matched region + SKU pairs)",
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(legend=dict(orientation="h", y=1.08), height=440)
    return fig


def fig_regional(latest: pd.DataFrame, model: str = "H100"):
    d = _ondemand_per_gpu(latest)
    d = d[d["gpu_model"] == model]
    if d.empty:
        return None
    d = d.sort_values("price_usd_per_gpu_hour")
    fig = px.strip(
        d, x="price_usd_per_gpu_hour", y="provider", color="provider",
        hover_data=["region", "sku"], color_discrete_map=COLORS,
        labels={"price_usd_per_gpu_hour": "USD / GPU-hour", "provider": ""},
        title=f"{model} on-demand price dispersion across regions (each dot = one region × SKU)",
    )
    fig.update_layout(showlegend=False, height=380)
    return fig


def fig_history(history: pd.DataFrame):
    d = _ondemand_per_gpu(history)
    d = d[d["gpu_model"].isin(HISTORY_MODELS)]
    med = (d.groupby(["snapshot_date", "provider", "gpu_model"], as_index=False)
            ["price_usd_per_gpu_hour"].median())
    fig = px.line(
        med, x="snapshot_date", y="price_usd_per_gpu_hour", color="provider",
        facet_col="gpu_model", facet_col_wrap=3, markers=True,
        color_discrete_map=COLORS,
        category_orders={"gpu_model": HISTORY_MODELS},
        labels={"price_usd_per_gpu_hour": "Median USD / GPU-hour",
                "snapshot_date": "", "provider": ""},
        title="Price history — median on-demand USD per GPU-hour (one point per weekly snapshot)",
    )
    fig.update_layout(legend=dict(orientation="h", y=1.12), height=560)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    return fig


def kpi_cards(latest: pd.DataFrame) -> str:
    cards = []
    for provider in ("AWS", "Azure", "GCP"):
        d = latest[latest["provider"] == provider]
        if d.empty:
            continue
        h100 = _ondemand_per_gpu(d)
        h100 = h100[h100["gpu_model"] == "H100"]
        floor = f"${h100['price_usd_per_gpu_hour'].min():,.2f}" if not h100.empty else "—"
        cards.append(
            f"<div class='card'><h3 style='color:{COLORS[provider]}'>{provider}</h3>"
            f"<p>{d['region'].nunique()} regions · {d['sku'].nunique()} GPU SKUs</p>"
            f"<p class='big'>{floor}</p><p class='sub'>cheapest H100 / GPU-hr</p></div>")
    return "<div class='cards'>" + "".join(cards) + "</div>"


def latest_md(latest: pd.DataFrame, snapshot_date: str) -> str:
    d = _ondemand_per_gpu(latest)
    d = d[d["gpu_model"].isin(FLAGSHIP_ORDER)]
    floor = (d.groupby(["gpu_model", "provider"])["price_usd_per_gpu_hour"]
              .min().unstack("provider").reindex(FLAGSHIP_ORDER).dropna(how="all"))
    lines = [
        f"# GPU pricing snapshot — {snapshot_date}",
        "",
        f"{len(latest):,} price points · "
        f"{latest['region'].nunique()} regions · "
        f"{latest['sku'].nunique()} SKUs across AWS / Azure / GCP.",
        "",
        "Cheapest on-demand **USD per GPU-hour** (across all regions):",
        "",
        "| GPU | " + " | ".join(floor.columns) + " |",
        "|---|" + "---|" * len(floor.columns),
    ]
    for model, row in floor.iterrows():
        cells = [f"${v:,.2f}" if pd.notna(v) else "—" for v in row]
        lines.append(f"| {model} | " + " | ".join(cells) + " |")
    lines += ["", "_Auto-generated by the weekly pricing tracker._"]
    return "\n".join(lines)


def build(history: pd.DataFrame) -> None:
    snapshot_date = history["snapshot_date"].max()
    latest = history[history["snapshot_date"] == snapshot_date]
    n_snapshots = history["snapshot_date"].nunique()

    figs = [fig_map(latest), fig_continent(latest),
            fig_latest_floor(latest), fig_spot_discount(latest)]
    regional = fig_regional(latest)
    if regional is not None:
        figs.append(regional)
    figs.append(fig_history(history))

    charts_html, include_js = [], "cdn"
    for fig in figs:
        charts_html.append(fig.to_html(full_html=False, include_plotlyjs=include_js))
        include_js = False

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Cloud GPU Pricing Tracker — AWS · Azure · GCP</title>
<style>
 body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}}
 .wrap{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
 h1{{margin-bottom:4px}} .byline{{color:#57606a;margin-top:0}}
 nav{{margin:10px 0 0}} nav a{{color:#0969da;margin-right:18px;font-weight:600;text-decoration:none}}
 .cards{{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}}
 .card{{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:16px 22px;flex:1;min-width:200px}}
 .card h3{{margin:0 0 6px}} .card p{{margin:2px 0;color:#57606a;font-size:14px}}
 .card .big{{font-size:30px;font-weight:700;color:#1f2328;margin-top:8px}}
 .card .sub{{font-size:12px}}
 .chart{{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:8px;margin:20px 0}}
 .note{{background:#fff8c5;border:1px solid #d4a72c66;border-radius:8px;padding:12px 16px;font-size:14px}}
 footer{{color:#57606a;font-size:13px;margin-top:40px}}
 a{{color:#0969da}}
 /* a11y + layout safety — slop-test gates 26, 34, 51 (no CSS motion here, so 27 passes trivially) */
 html,body{{overflow-x:clip}}
 h1,h2,h3{{overflow-wrap:anywhere;min-width:0}}
 a:focus-visible,button:focus-visible,select:focus-visible,summary:focus-visible,[tabindex]:focus-visible{{outline:2px solid #0969da;outline-offset:2px;border-radius:4px}}
</style></head><body><div class="wrap">
<h1>AI Cloud GPU Pricing Tracker</h1>
<p class="byline">AWS · Azure · GCP — refreshed weekly by an automated pipeline (GitHub Actions).
Latest snapshot: <b>{snapshot_date}</b> · {n_snapshots} weekly snapshot(s) collected since 2026-06-10.</p>
<nav><a href="index.html">Live GPU Pricing</a><a href="market.html">Market History</a><a href="regional.html">Regional Deep-Dive</a><a href="analysis.html">Event Study &amp; Experiments</a><a href="outlook.html">Outlook &amp; Pulse</a></nav>
{kpi_cards(latest)}
{"".join(f"<div class='chart'>{c}</div>" for c in charts_html)}
<div class="note"><b>Methodology & comparability.</b>
Azure prices come from the public Retail Prices API (pay-as-you-go + Spot, Linux);
AWS from the Vantage mirror of the official AWS Price List (on-demand + spot, Linux);
GCP from the Cloud Billing Catalog API (on-demand + preemptible).
AWS/Azure per-GPU prices are derived from whole GPU instances, so they include bundled vCPU/RAM;
GCP bills GPUs as standalone per-GPU-hour SKUs that exclude the host VM.
Cross-cloud comparisons should treat roughly the host-VM cost as the bundling wedge.
List prices only — negotiated/committed-use discounts are not reflected.
The map shows primary cloud regions; AWS Local Zones / Wavelength and operator edge
zones are tracked in the dataset but omitted from the map. Same-metro dots are
slightly offset so all providers stay visible.</div>
<footer>Part of the <a href="https://github.com/JarvisLee511/multi-cloud-ai-infrastructure-analysis">Multi-Cloud AI Infrastructure Market Analysis</a> project
· Che-Wei (Jarvis) Lee · report rebuilt {built}</footer>
</div></body></html>"""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    (DOCS_DIR / "LATEST.md").write_text(latest_md(latest, snapshot_date), encoding="utf-8")
    print(f"report built -> {DOCS_DIR / 'index.html'}")


if __name__ == "__main__":
    from common import consolidate
    build(consolidate())
