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
import theme

REGION_GEO_CSV = Path(__file__).resolve().parent / "region_geo.csv"
# Spread per-provider dots that share a metro so all three stay visible.
MAP_JITTER = {"AWS": (0.9, -1.6), "Azure": (-0.9, 0.0), "GCP": (0.9, 1.6)}

COLORS = theme.PROVIDER
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
            f"<div><h3 class='is-{provider.lower()}'>{provider}</h3>"
            f"<p class='big'>{floor}</p>"
            f"<p class='sub'>cheapest H100 per GPU-hour</p>"
            f"<p class='sub'>{d['region'].nunique()} regions · "
            f"{d['sku'].nunique()} GPU SKUs</p></div>")
    return "<div class='figures'>" + "".join(cards) + "</div>"


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

    cheapest = (_ondemand_per_gpu(latest)
                .groupby("provider")["price_usd_per_gpu_hour"].min())
    lead = cheapest.idxmin() if len(cheapest) else None

    body = kpi_cards(latest) + theme.render(figs) + f"""
<p class="caption"><b>How these prices are collected, and what they are not.</b>
Azure comes from the public Retail Prices API (pay-as-you-go and Spot, Linux); AWS from the
Vantage mirror of the official Price List (on-demand and spot, Linux); Google Cloud from the
Cloud Billing Catalog API (on-demand and preemptible). <b>The three are not like for
like.</b> AWS and Azure per-GPU figures are derived from whole GPU instances, so they carry
bundled vCPU and RAM; Google bills GPUs as standalone per-GPU-hour SKUs that exclude the host
VM. Read roughly the host-VM cost as the wedge between them{
    f" — which is most of why {lead} looks cheapest here" if lead else ""}.
List prices only: negotiated and committed-use discounts are not reflected anywhere on this
page. The map shows primary cloud regions; AWS Local Zones, Wavelength and operator edge zones
are in the dataset but off the map, and same-metro dots are nudged apart so all three providers
stay visible.</p>"""

    html = theme.page(
        slug="index.html",
        title="AI Cloud GPU Pricing Tracker — AWS, Azure and Google Cloud",
        description=(f"GPU and accelerator list prices across AWS, Azure and Google Cloud, "
                     f"re-collected weekly. Latest snapshot {snapshot_date}, "
                     f"{n_snapshots} snapshots since collection began."),
        kicker="Live pricing",
        headline="What an hour of GPU costs, across three clouds",
        standfirst=("Re-collected every week from each provider's own pricing API, and kept "
                    "so the series grows. The interesting number is not today's floor but "
                    "which way it is moving."),
        byline=(f"Snapshot {snapshot_date} &middot; {n_snapshots} weekly "
                f"snapshot{'s' if n_snapshots != 1 else ''} collected"),
        body=body,
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    (DOCS_DIR / "LATEST.md").write_text(latest_md(latest, snapshot_date), encoding="utf-8")
    print(f"report built -> {DOCS_DIR / 'index.html'}")


if __name__ == "__main__":
    from common import consolidate
    build(consolidate())
