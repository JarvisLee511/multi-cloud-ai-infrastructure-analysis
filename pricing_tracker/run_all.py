"""Weekly tracker entry point: fetch all providers, consolidate, rebuild report.

A provider failure (e.g. missing GCP credentials) is logged but does not abort
the run — the snapshot is taken with whatever providers succeeded.
"""
from __future__ import annotations

import sys
import traceback

import build_report
import fetch_aws
import fetch_azure
import fetch_gcp
from common import consolidate, save_snapshot

# Data-validation gates: if any fails, the run exits non-zero so the CI run
# turns red and we notice — instead of silently committing thin/broken data.
MIN_ROWS = {"AWS": 800, "Azure": 800, "GCP": 300}
H100_SANE_RANGE = (1.0, 50.0)  # USD per GPU-hour, cheapest on-demand


def validate(history) -> list[str]:
    latest = history[history["snapshot_date"] == history["snapshot_date"].max()]
    problems = []
    for provider, minimum in MIN_ROWS.items():
        n = len(latest[latest["provider"] == provider])
        if n < minimum:
            problems.append(f"{provider}: {n} rows in latest snapshot (expected >= {minimum})")
    h100 = latest[(latest["gpu_model"] == "H100")
                  & (latest["price_type"] == "ondemand")
                  & latest["price_usd_per_gpu_hour"].notna()]
    if h100.empty:
        problems.append("no H100 on-demand prices in latest snapshot")
    else:
        floor = h100["price_usd_per_gpu_hour"].min()
        if not (H100_SANE_RANGE[0] < floor < H100_SANE_RANGE[1]):
            problems.append(f"cheapest H100 ${floor:,.2f}/GPU-hr is outside sane range")
    if (latest["price_usd_hour"] <= 0).any():
        problems.append("non-positive prices present")
    return problems


def main() -> None:
    succeeded = []
    for module, name in ((fetch_aws, "AWS"), (fetch_azure, "Azure"), (fetch_gcp, "GCP")):
        try:
            df = module.fetch()
            path = save_snapshot(df, name)
            print(f"[{name}] {len(df):,} rows, {df['region'].nunique()} regions -> {path.name}")
            succeeded.append(name)
        except Exception:
            traceback.print_exc()
            print(f"[{name}] FAILED - continuing with remaining providers", file=sys.stderr)

    if not succeeded:
        sys.exit("all providers failed")

    history = consolidate()
    print(f"history: {len(history):,} rows, {history['snapshot_date'].nunique()} snapshot date(s)")
    build_report.build(history)

    for module_name in ("build_market_report", "build_regional_report",
                        "build_analysis_report", "build_outlook"):
        try:
            __import__(module_name).build()
        except FileNotFoundError as exc:
            print(f"{module_name} skipped (missing data): {exc}", file=sys.stderr)

    problems = validate(history)
    if problems:
        for p in problems:
            print(f"VALIDATION FAILED: {p}", file=sys.stderr)
        sys.exit(1)  # reports are built & committed (workflow commits on always())
    print("validation passed")


if __name__ == "__main__":
    main()
