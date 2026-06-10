"""Derive developer cloud-adoption rates by country/region from the
Stack Overflow Developer Survey microdata (2023-2025).

Source: the survey's public dataset (via the Hugging Face mirror
`yeper/stack-overflow-developer-survey`, parquet per year). For each year:
among respondents who answered PlatformHaveWorkedWith, the share who used
AWS / Azure / Google Cloud, per country. This measures DEVELOPER adoption
(multi-select, sums can exceed 100%) — a demand-side proxy, not revenue share.

Outputs (committed; raw microdata is not):
  data/regional/so_cloud_adoption_by_country.csv
  data/regional/so_cloud_adoption_by_region.csv
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import requests

from common import REPO_ROOT

HF_BASE = ("https://huggingface.co/datasets/yeper/"
           "stack-overflow-developer-survey/resolve/main/")
YEARS = (2023, 2024, 2025)
OUT_DIR = REPO_ROOT / "data" / "regional"
MIN_RESPONDENTS = 100  # per country-year, below this we don't report

CLOUD_LABELS = {
    "AWS": {"Amazon Web Services (AWS)", "AWS"},
    "Azure": {"Microsoft Azure", "Azure"},
    "GCP": {"Google Cloud", "Google Cloud Platform"},
}

REGION_MAP = {
    # North America
    "United States of America": "North America", "Canada": "North America",
    "Mexico": "North America",
    # Europe
    "Germany": "Europe", "United Kingdom of Great Britain and Northern Ireland": "Europe",
    "France": "Europe", "Poland": "Europe", "Netherlands": "Europe",
    "Italy": "Europe", "Spain": "Europe", "Sweden": "Europe",
    "Switzerland": "Europe", "Austria": "Europe", "Czech Republic": "Europe",
    "Denmark": "Europe", "Norway": "Europe", "Finland": "Europe",
    "Belgium": "Europe", "Portugal": "Europe", "Romania": "Europe",
    "Greece": "Europe", "Hungary": "Europe", "Ireland": "Europe",
    "Bulgaria": "Europe", "Slovakia": "Europe", "Croatia": "Europe",
    "Lithuania": "Europe", "Serbia": "Europe", "Slovenia": "Europe",
    "Estonia": "Europe", "Latvia": "Europe", "Ukraine": "Europe",
    "Russian Federation": "Europe",
    # Asia (developed + emerging, ex-Middle East)
    "India": "Asia", "Japan": "Asia", "China": "Asia", "Taiwan": "Asia",
    "South Korea": "Asia", "Republic of Korea": "Asia",
    "Hong Kong (S.A.R.)": "Asia", "Singapore": "Asia", "Viet Nam": "Asia",
    "Indonesia": "Asia", "Philippines": "Asia", "Malaysia": "Asia",
    "Thailand": "Asia", "Bangladesh": "Asia", "Pakistan": "Asia",
    "Sri Lanka": "Asia", "Nepal": "Asia",
    # Middle East
    "Israel": "Middle East", "Turkey": "Middle East",
    "Iran, Islamic Republic of...": "Middle East",
    "United Arab Emirates": "Middle East", "Saudi Arabia": "Middle East",
    # Oceania
    "Australia": "Oceania", "New Zealand": "Oceania",
    # South / Latin America
    "Brazil": "South America", "Argentina": "South America",
    "Colombia": "South America", "Chile": "South America",
    "Peru": "South America", "Uruguay": "South America",
    "Venezuela, Bolivarian Republic of...": "South America",
    # Africa
    "South Africa": "Africa", "Nigeria": "Africa", "Egypt": "Africa",
    "Kenya": "Africa", "Morocco": "Africa", "Ghana": "Africa",
}


def _flags(series: pd.Series) -> pd.DataFrame:
    """Per-respondent booleans for each cloud, from the multi-select column."""
    parts = series.str.split(";")
    out = {}
    for cloud, labels in CLOUD_LABELS.items():
        out[cloud] = parts.map(lambda lst: any(p in labels for p in lst))
    return pd.DataFrame(out, index=series.index)


def load_year(year: int) -> pd.DataFrame:
    cache = Path(tempfile.gettempdir()) / f"so_survey_{year}.parquet"
    if not cache.exists():
        r = requests.get(HF_BASE + f"survey_{year}.parquet", timeout=600)
        r.raise_for_status()
        cache.write_bytes(r.content)
    df = pd.read_parquet(cache, columns=["Country", "PlatformHaveWorkedWith"])
    df = df.dropna(subset=["Country", "PlatformHaveWorkedWith"])
    flags = _flags(df["PlatformHaveWorkedWith"])
    flags["Country"] = df["Country"]
    flags["year"] = year
    return flags


def main() -> None:
    frames = [load_year(y) for y in YEARS]
    all_years = pd.concat(frames, ignore_index=True)

    by_country = (all_years.groupby(["year", "Country"])
                  .agg(respondents=("AWS", "size"),
                       aws_pct=("AWS", "mean"), azure_pct=("Azure", "mean"),
                       gcp_pct=("GCP", "mean")).reset_index())
    for c in ("aws_pct", "azure_pct", "gcp_pct"):
        by_country[c] = (by_country[c] * 100).round(1)
    by_country = by_country[by_country["respondents"] >= MIN_RESPONDENTS]
    by_country = by_country.rename(columns={"Country": "country"})

    all_years["region"] = all_years["Country"].map(REGION_MAP)
    by_region = (all_years.dropna(subset=["region"])
                 .groupby(["year", "region"])
                 .agg(respondents=("AWS", "size"),
                      aws_pct=("AWS", "mean"), azure_pct=("Azure", "mean"),
                      gcp_pct=("GCP", "mean")).reset_index())
    for c in ("aws_pct", "azure_pct", "gcp_pct"):
        by_region[c] = (by_region[c] * 100).round(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_country.to_csv(OUT_DIR / "so_cloud_adoption_by_country.csv", index=False)
    by_region.to_csv(OUT_DIR / "so_cloud_adoption_by_region.csv", index=False)
    print(f"{len(by_country)} country-years (>= {MIN_RESPONDENTS} respondents), "
          f"{len(by_region)} region-years")
    print(by_region[by_region['year'] == max(YEARS)].to_string(index=False))


if __name__ == "__main__":
    main()
