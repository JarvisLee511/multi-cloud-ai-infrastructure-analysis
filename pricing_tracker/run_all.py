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
                        "build_analysis_report"):
        try:
            __import__(module_name).build()
        except FileNotFoundError as exc:
            print(f"{module_name} skipped (missing data): {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
