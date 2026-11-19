# Bond ETF discount project: Day 1 merge

## Setup
```
pip install -r requirements.txt
mkdir -p data/raw/nav
```

## Before running
1. Download each fund's data file from its iShares page.
2. Rename each one so it starts with the ticker: `LQD.xls`, `HYG.xls`, ...
3. Put all 9 in `data/raw/nav/`. Don't edit them; the script reads them as-is.
   If a file won't open, re-save it from Excel as CSV with the same name (`LQD.csv`).
4. Documented fixes in `data/corrections/` (excluded prices, verified missing distributions)
   are applied automatically at processing time; raw files are never edited. See its README.

## Run
```
python merge_data.py            # first run: pulls prices from yfinance and caches them
python merge_data.py --offline  # later runs: uses the cached prices
python -m unittest -v test_merge_data   # run the tests
```

## Outputs
- `data/clean/panel.csv`: one row per fund per day (close, nav, div, discount, log_gap, event)
- `data/clean/events.csv`: just the large-discount events
- `data/clean/validation_report.txt`: coverage, duplicates, worst discount, the LQD March 2020 check
- `figures/discount_<TICKER>.png`: each fund's discount over time, events marked in red

## Check before Day 2
- LQD on 2020-03-19 should show a discount of roughly 5%.
- Compare the holiday list in `bond_market_holidays()` against SIFMA's calendar.
- Every fund's chart should look sensible: no huge spikes outside March 2020.
