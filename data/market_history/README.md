# Market history dataset (2016–2026)

Quarterly cloud-segment financials compiled **row-by-row from SEC EDGAR earnings
releases** (8-K Exhibit 99.1). Every row carries its `source_url`. Compiled
2026-06-10.

## Files

| File | Contents |
|---|---|
| `quarterly_financials.csv` | quarter × provider: revenue & operating income, USD millions |
| `azure_yoy_growth.csv` | Microsoft's disclosed "Azure (and other cloud services)" YoY growth %, the only Azure-specific revenue metric Microsoft publishes |
| `market_share.csv` | analyst-firm (Synergy/Canalys) worldwide IaaS/PaaS market-share estimates, by quarter (compiled from public press releases) |

## Comparability caveats — read before charting

1. **The three "providers" are not the same kind of thing.**
   - **AWS** = a clean reportable segment, unchanged definition since 2015. The gold standard of the three series.
   - **Azure** rows = Microsoft's **Intelligent Cloud segment** (Azure + server products + enterprise services). Microsoft has *never* disclosed quarterly absolute Azure revenue; the only Azure-specific metric is the YoY growth % (see `azure_yoy_growth.csv`). Treat Intelligent Cloud as an upper bound / proxy.
   - **GCP** = Google Cloud segment (GCP + Workspace).
2. **Microsoft segment re-definition at 2024Q3 (FY25 Q1).** EMS & Power BI per-user revenue moved out of Intelligent Cloud; some Search advertising moved in. Rows from 2024Q3 are NOT comparable with earlier rows (the overlap quarter was recast 24,259 → 20,013). Charts must show a break.
3. **Google Cloud history limits.** Quarterly revenue starts 2018Q4 (Q1–Q3 2018 never disclosed; FY2017 = $4,056M annual only). Operating income starts 2019Q4. The Apr-2023 recast (DeepMind moved out of segments) restated 2022 OI; 2021 quarterly OI is as-originally-reported — a small series seam.
4. **Accounting-standard seams.** ASC 606 adoption (2018): Amazon/Microsoft 2016–2017 rows are pre-ASC606 as originally reported. Amazon server useful-life changes (2020 / 2022 / 2024, partial reversal 2025) flatter/penalize AWS operating income across years.
5. **Market share** numbers are analyst *estimates* (Synergy Research / Canalys press releases), not filings. Synergy and Canalys totals differ (e.g. 2023Q3: $68.1B vs $73.5B) — never mix firms within one series; the chart draws them as separate line styles. Specific seams: Synergy 2023Q1–Q3 gave AWS only as a "32–34% band" (omitted rather than guessed); Synergy's Microsoft drop 25%→20% across 2024 reflects Synergy's reclassification after Microsoft's segment restatement, not a business collapse; Canalys later restated 2018Q4 (Google 9.5%→4.9% once Alphabet began disclosing actual Cloud revenue) — rows are as-originally-published. Pre-2018 releases rarely broke out Microsoft/Google at all, hence sparse early coverage (one verified point per year minimum).

These caveats are deliberate scope: the cross-provider revenue chart is honest
only with the proxy/break annotations rendered on it.
