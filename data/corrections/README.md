# Processing-time corrections

`merge_data.py` applies these files after loading the cached prices and dividends and before
merging. The raw files in `data/raw/` are never edited. Every applied correction is listed at
the end of `data/clean/validation_report.txt`.

## price_exclusions.csv

Lists (ticker, date) closes that must never enter the panel, even if a NAV for that date
becomes available later. Each row records the cached value, the cache file, the reason, and
the evidence.

- 2026-11-19 for all nine funds. Om's cache was pulled on 2026-11-19 (`*_pulled_on.txt`) and
  committed in `1bcf1c4` at 12:44:43 −0500, before the 4pm ET close. These values are
  mid-session prices, not closes. The values stay in the raw cache; they are only dropped
  during processing.

`merge_data.py` also prints a warning, which the report repeats, if a cached close is dated
on or after its cache's pull date and is not listed here. This catches the same problem
after a future re-pull.

## dividend_supplements.csv

Lists verified distributions that are missing from the yfinance dividend cache. A supplement
is added only if the cache does not already have that ex-date. If a later re-pull fills the
gap, the cache value wins and nothing is counted twice.

- SHYG, ex-date 2016-03-01, $0.209028, and ex-date 2016-04-01, $0.21715. Confirmed in three
  official iShares places: the `Distributions` sheet and the `Historical` sheet's
  `Ex-Dividends` column of `data/raw/nav/SHYG.xls` (sha256 in the CSV), and the distribution
  table on the SHYG product page, all retrieved 2026-11-19. These are all iShares
  publications, not independent sources. Day-over-day NAV changes cannot confirm the
  amounts, because March 2016 high-yield market moves swamp a ~$0.21 drop.
