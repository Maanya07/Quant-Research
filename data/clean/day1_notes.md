# Day 1 notes: NAV merge (updated 2026-11-19)

Reproduce:
```
python -m unittest -v test_merge_data      # 17 tests
python merge_data.py --offline             # Om's caches from commit 1bcf1c4; no network needed
```
Inputs:
- `data/raw/nav/*.xls`: untouched iShares downloads; see `SOURCES.md`.
- `data/raw/prices/*`: Om's untouched cache.
- `data/corrections/*.csv`: documented corrections applied at processing time; see that folder's `README.md`.

The spec comparison for Om is in `docs/spec_comparison.md`.

## Coverage, rows, events (events are PROVISIONAL)

All nine funds cover 2015-01-02 to 2026-11-18 with 2,966 rows each. Of the 2,990 NAV rows per fund, the panel drops:
- 22 Columbus/Veterans Day rows, by design.
- 2 NAV-only dates with no exchange close: 2024-03-29 (Good Friday) and 2024-03-31 (Sunday).

The mid-session 2026-11-19 prices are now excluded explicitly, via `price_exclusions.csv`, rather than only by the lack of a NAV that day.

| Ticker | Rows | Events | 2015–19 | 2020 | 2021–26 | Cutoff (5% quantile) |
|---|---|---|---|---|---|---|
| SHY | 2966 | 101 | 71 | 16 | 14 | -0.01% |
| IEF | 2966 | 93 | 76 | 16 | 1 | -0.05% |
| TLT | 2966 | 88 | 73 | 15 | 0 | -0.16% |
| LQD | 2966 | 80 | 43 | 9 | 28 | -0.12% |
| IGSB | 2966 | 74 | 19 | 6 | 49 | -0.04% |
| HYG | 2966 | 86 | 33 | 15 | 38 | -0.21% |
| SHYG | 2966 | 75 | 17 | 15 | 43 | -0.12% |
| MUB | 2966 | 76 | 38 | 6 | 32 | -0.14% |
| EMB | 2966 | 90 | 22 | 7 | 61 | -0.16% |
| **Total** | 26694 | **763** | 392 | 105 | 266 | |

There are no duplicate (ticker, date) rows and no missing values. Discount and log gap recompute exactly. Events are at least 5 sessions apart, and none falls mid-episode.

## Fixes on this branch

1. **Pre-sample dividends.** All 2002–2014 dividends were piled onto each fund's 2015-01-02 row. They are now skipped, and a regression test covers this.
2. **SHYG distributions.** 2016-03-01 ($0.209028) and 2016-04-01 ($0.21715) were missing from the yfinance cache. They are confirmed in iShares' Distributions sheet, the Historical sheet's Ex-Dividends column, and the product-page distribution table, and are added via `dividend_supplements.csv`.
3. **Incomplete 2026-11-19 prices.** All nine are excluded via `price_exclusions.csv`, and stay out even if a NAV for that date appears later; a test covers this. A warning now fires for any future cache row dated on its pull day.
4. **Event rule.**
   - *Before:* `flag_events` re-fired every 5 sessions inside one continuous run below the cutoff. That contradicts its docstring ("first day of each cluster") and the plan ("persistent discounts are one episode").
   - *Now:* only an episode's first day can be an event, and only if it is at least 5 sessions after the previous event. A focused test failed on the old code (it flagged days 10, 15, 20, 25) and passes now.
   - The threshold is unchanged. Outputs carry `event_status = provisional`, and the report and chart legends say so too.

## Event count reconciliation

The earlier note said "39 extra events", which was wrong. 39 is how many old events fell mid-episode, not the net change. Exact figures from old versus new `panel.csv`:

- Old: 793 events = 754 episode starts + 39 mid-episode.
- New: 763 events. The net change is −30 = −42 + 12:
  - The 42 removed are the 39 mid-episode events plus 3 episode starts that now fall within 5 sessions of a newly unblocked event.
  - The 12 added are episode starts the old mid-episode events had been blocking.
- 979 episodes in total; 216 episode starts are blocked by the 5-session spacing.
- Prices, NAVs, discounts and cutoffs are identical between old and new.

Consequence: LQD and IGSB now have one March 2020 event, on 03-05, not three. The deepest days (LQD -5.08% on 03-19, IGSB -6.93% on 03-19) are days inside an episode, not events. TLT's event moves from 03-11 to 03-24.

## LQD 2020-03-19 check

Close 105.05 against same-day NAV 110.6726 gives -5.08%, consistent with the README's "roughly 5%".
- Using the 3/18 or 3/20 NAV instead gives -7.08% or -4.32%, so the match supports same-day alignment.
- Caveats: 2020-03-12 is nearly as deep (-5.02%). The close is yfinance's last trade, while iShares' own premium figure uses the 4pm bid/ask midpoint, which these downloads don't include.

## Price spikes: unresolved

Each case is a one-day jump in the close with a flat NAV, reversing the next day:
- MUB, 2016-07-07: close 114.08 → 115.19 → 113.98, NAV about 113.93 (+1.10%).
- MUB, 2018-10-23: close 106.99 → 108.15 → 107.32, NAV about 107.19 (+0.90%).
- SHY, 2017-10-04: close 84.39 → 84.55 → 84.37, NAV about 84.36 (+0.23%).

No independent close source was reachable:
- Nasdaq's historical API returned no rows, even for 2025.
- Stooq and MarketWatch block automated access with JavaScript/bot challenges, which I did not try to get around.

**Verified:** these are the values in the yfinance cache, and NAV did not move on those days.
**Hypothesis, not verified:** a bad or outlier closing print. The observations are kept.
**To resolve:** compare against a second source with official closing prices for 2016-07-07, 2018-10-23 and 2017-10-04, such as CRSP via WRDS, Bloomberg, or the listing exchange's records.

## TLT/IEF discontinuity at 2021-01-11/12: unresolved

**Verified from the data:**
- Premium standard deviation falls from 16.1bp to 4.9bp for TLT and from 6.5bp to 2.3bp for IEF, excluding Feb–May 2020.
- Before the break, today's premium predicts tomorrow's NAV return: correlation +0.19 (TLT) and +0.20 (IEF). After the break it is about 0 (-0.02 and +0.02).
- The same holds in 18-month windows on each side of the break.
- SHY shows no comparable break. LQD and IGSB weaken only modestly (correlation +0.27 → +0.13 and +0.18 → +0.10).
- NAV precision (6 decimal places) does not change at the break.

**Verified from external sources:**
- The TLT and IEF listing moves from NYSE Arca to Nasdaq happened in Feb 2016 and Aug 2017 ([Nasdaq ETA2016-20](https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2016-20), [ETF Strategy](https://www.etfstrategy.com/blackrock-to-transfer-50-ishares-etfs-to-nasdaq-or-bats-81946/)), so they cannot explain a 2021 break.
- EDGAR full-text searches of iShares Trust filings (CIK 1100663) from Oct 2020 to Mar 2021 found no documented change in NAV valuation time. The "3:00 p.m." matches are settlement deadlines.

**Hypothesis, not verified:** before 2021, the Treasury NAVs reflected bond prices taken earlier than the 4pm ETF close, or a different pricing method. Under that hypothesis, most pre-2021 Treasury "discounts" are timing gaps, not dislocations.

**To resolve:** check iShares Trust SAI/prospectus supplements from late 2020, or ask iShares, about any change in Treasury-fund valuation time, pricing vendor or methodology around 2021-01-11.

**Decision needed:** whether Treasury funds stay in the universe; the plan excludes them anyway.

## Other open items

- **Holiday list:** checks out against SIFMA releases for 2016-10-10, 2016-11-11 and 2024-10-14, and against SIFMA's 2025–2026 listings. A full year-by-year check against SIFMA's [U.S. Holiday Archive](https://www.sifma.org/resources/general/us-holiday-archive/) is still pending.
- **Sample edges:** 4 events have fewer than 5 following sessions (EMB 2026-11-16, IGSB 2026-11-17, MUB 2026-11-12, SHY 2026-11-16). EMB and SHYG have events on the first sample day, which is left-censored. Both are kept; see the spec comparison.
- **Fund-history audit:** name, index and mandate changes (for example, IGSB's earlier ticker and index) are not yet checked.
