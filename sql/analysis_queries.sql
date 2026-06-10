-- Analysis queries for cloud_market.db (build with: py sql/build_db.py)
-- Star schema: dim_provider / dim_region / dim_gpu  ×  fact_gpu_price,
-- fact_quarterly_financials, fact_market_share.

-- 1. Cheapest H100 per provider right now (window function over latest snapshot)
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price)
SELECT *
FROM (
    SELECT p.name AS provider, r.region_code, r.city, f.sku,
           f.price_usd_per_gpu_hour,
           ROW_NUMBER() OVER (PARTITION BY p.name
                              ORDER BY f.price_usd_per_gpu_hour) AS rn
    FROM fact_gpu_price f
    JOIN dim_gpu g       ON g.gpu_id = f.gpu_id
    JOIN dim_region r    ON r.region_id = f.region_id
    JOIN dim_provider p  ON p.provider_id = r.provider_id
    WHERE g.model = 'H100' AND f.price_type = 'ondemand'
      AND f.price_usd_per_gpu_hour IS NOT NULL
      AND f.snapshot_date = (SELECT d FROM latest)
)
WHERE rn = 1;

-- 2. Week-over-week price change per provider × GPU (LAG over weekly snapshots)
WITH weekly AS (
    SELECT f.snapshot_date, p.name AS provider, g.model,
           AVG(f.price_usd_per_gpu_hour) AS avg_price
    FROM fact_gpu_price f
    JOIN dim_gpu g      ON g.gpu_id = f.gpu_id
    JOIN dim_region r   ON r.region_id = f.region_id
    JOIN dim_provider p ON p.provider_id = r.provider_id
    WHERE f.price_type = 'ondemand' AND f.price_usd_per_gpu_hour IS NOT NULL
      AND g.model IN ('H200','H100','A100','L4','T4')
    GROUP BY 1, 2, 3
)
SELECT snapshot_date, provider, model, ROUND(avg_price, 3) AS avg_price,
       ROUND(100.0 * (avg_price / LAG(avg_price) OVER (
           PARTITION BY provider, model ORDER BY snapshot_date) - 1), 2)
           AS wow_change_pct
FROM weekly
ORDER BY provider, model, snapshot_date;

-- 3. Spot discount by provider × GPU (self-join on matched region + SKU)
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price)
SELECT p.name AS provider, g.model,
       COUNT(*)                                          AS matched_skus,
       ROUND(AVG(1 - s.price_usd_hour / o.price_usd_hour), 3) AS avg_spot_discount
FROM fact_gpu_price o
JOIN fact_gpu_price s
     ON s.region_id = o.region_id AND s.sku = o.sku
    AND s.snapshot_date = o.snapshot_date
    AND s.price_type = 'spot' AND o.price_type = 'ondemand'
JOIN dim_gpu g      ON g.gpu_id = o.gpu_id
JOIN dim_region r   ON r.region_id = o.region_id
JOIN dim_provider p ON p.provider_id = r.provider_id
WHERE o.snapshot_date = (SELECT d FROM latest) AND o.price_usd_hour > 0
GROUP BY 1, 2
HAVING COUNT(*) >= 3
ORDER BY avg_spot_discount DESC;

-- 4. GPU-equipped regions per continent per provider (the footprint view)
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price)
SELECT r.continent, p.name AS provider,
       COUNT(DISTINCT r.region_code) AS gpu_regions,
       COUNT(DISTINCT f.sku)         AS distinct_skus
FROM fact_gpu_price f
JOIN dim_region r   ON r.region_id = f.region_id
JOIN dim_provider p ON p.provider_id = r.provider_id
WHERE f.snapshot_date = (SELECT d FROM latest) AND r.continent IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 3 DESC;

-- 5. Regional price dispersion: where is the same GPU most/least expensive?
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price)
SELECT p.name AS provider, g.model,
       ROUND(MIN(f.price_usd_per_gpu_hour), 2) AS cheapest,
       ROUND(MAX(f.price_usd_per_gpu_hour), 2) AS priciest,
       ROUND(MAX(f.price_usd_per_gpu_hour) / MIN(f.price_usd_per_gpu_hour), 2)
           AS max_over_min
FROM fact_gpu_price f
JOIN dim_gpu g      ON g.gpu_id = f.gpu_id
JOIN dim_region r   ON r.region_id = f.region_id
JOIN dim_provider p ON p.provider_id = r.provider_id
WHERE f.price_type = 'ondemand' AND f.price_usd_per_gpu_hour IS NOT NULL
  AND f.snapshot_date = (SELECT d FROM latest)
GROUP BY 1, 2
HAVING COUNT(*) >= 5
ORDER BY max_over_min DESC;

-- 6. Top-3 cheapest regions per GPU model across all clouds (DENSE_RANK)
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price),
ranked AS (
    SELECT g.model, p.name AS provider, r.region_code, r.city,
           f.price_usd_per_gpu_hour,
           DENSE_RANK() OVER (PARTITION BY g.model
                              ORDER BY f.price_usd_per_gpu_hour) AS rk
    FROM fact_gpu_price f
    JOIN dim_gpu g      ON g.gpu_id = f.gpu_id
    JOIN dim_region r   ON r.region_id = f.region_id
    JOIN dim_provider p ON p.provider_id = r.provider_id
    WHERE f.price_type = 'ondemand' AND f.price_usd_per_gpu_hour IS NOT NULL
      AND f.snapshot_date = (SELECT d FROM latest)
      AND g.model IN ('H200','H100','A100','L4','T4')
)
SELECT * FROM ranked WHERE rk <= 3 ORDER BY model, rk;

-- 7. NVIDIA vs AMD vs custom-silicon offering mix per provider
WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_gpu_price)
SELECT p.name AS provider, g.vendor,
       COUNT(DISTINCT f.sku) AS skus,
       COUNT(DISTINCT g.model) AS models
FROM fact_gpu_price f
JOIN dim_gpu g      ON g.gpu_id = f.gpu_id
JOIN dim_region r   ON r.region_id = f.region_id
JOIN dim_provider p ON p.provider_id = r.provider_id
WHERE f.snapshot_date = (SELECT d FROM latest)
GROUP BY 1, 2
ORDER BY 1, 3 DESC;

-- 8. Cloud revenue YoY growth per provider (needs fact_quarterly_financials,
--    populated from data/market_history/quarterly_financials.csv)
SELECT quarter, p.name AS provider, revenue_musd,
       ROUND(100.0 * (revenue_musd * 1.0 / LAG(revenue_musd, 4) OVER (
           PARTITION BY p.name ORDER BY quarter) - 1), 1) AS yoy_growth_pct,
       ROUND(100.0 * operating_income_musd / revenue_musd, 1) AS op_margin_pct
FROM fact_quarterly_financials f
JOIN dim_provider p ON p.provider_id = f.provider_id
ORDER BY p.name, quarter;
