# Spec comparison: research plan vs Day 1 pipeline

For Om, from Maanya. Branch `maanya/day1-nav`, uncommitted, on top of `1bcf1c4`.
Status: **nothing below has been decided**. The pipeline keeps its current settings, and its
events are labelled `provisional` until we agree.

- **Plan** = `Bond_ETF_Research_Plan.md`. It is not in the repo yet; it should be added.
- **Pipeline** = `README.md` + `merge_data.py`.

## Side by side

| Topic | Plan | Pipeline (current) | Data facts relevant to the choice |
|---|---|---|---|
| **Universe** | 6 funds in pairs: IG LQD/IGIB, HY HYG/SHYG, MUNI MUB/SUB. Pilot LQD, HYG, MUB. `category` column required. | 9 funds: SHY, IEF, TLT, LQD, IGSB, HYG, SHYG, MUB, EMB. No category. | In both: LQD, HYG, SHYG, MUB. Plan only: IGIB, SUB (no NAV downloaded yet). Pipeline only: 3 Treasuries, IGSB (1–5y IG, not IGIB's 5–10y), EMB (EM sovereign). TLT/IEF show an unexplained break in premium behaviour at 2021-01-11 (see `data/clean/day1_notes.md`). |
| **Sample endpoint** | 2015–2025, complete years only, plus a 2014 warm-up if available. Fit 2015–18, validate 2019, evaluate 2020–25. | 2015-01-01 to the latest data, currently 2026-11-18. No fixed end date, no warm-up. | iShares NAV covers 2014 for all 9 current funds (SHYG starts 2013-10-15). The price cache starts 2015-01-02, so a 2014 warm-up needs a price re-pull. |
| **Threshold** | Fixed 25bp. At most one documented revision, based on development-period counts only, then frozen. 10bp and 50bp as robustness checks. | Each fund's own 5% quantile over the **full** 2015–2026 sample: −0.01% (SHY) to −0.21% (HYG). This uses future data relative to the plan's split. | Cutoffs are listed in `validation_report.txt`. No counts at 25bp have been computed yet. The plan wants that audit limited to the development period. |
| **Event rule** | First upward crossing of the threshold. A persistent discount is one episode until it crosses back and re-enters. No new event "within the next five trading sessions". Valid history and the next 5 sessions must exist. Don't bridge missing NAV dates. | Now: first day of each run at or below the cutoff, ≥5 rows after the previous event, so an event at t allows the next at t+5. No check for the next 5 sessions. The first sample day can be an event. Dropped holidays are bridged. | The plan's wording would block t+5, so it may differ by one session. 4 events lack 5 following sessions. EMB and SHYG have events on 2015-01-02 (left-censored). 763 provisional events. |
| **Sign convention** | `discount_bps = 10000·(nav − close)/nav`; **positive = discount**. | `discount = close/nav − 1`; **negative = discount**; also `log_gap = ln(close/nav)`. | Exact conversion: `discount_bps = −10000·discount`. |
| **Outcome horizon** | h = 3 trading days (main), with 1 and 5 as supporting horizons. Signed price/NAV/remaining-gap contributions in bp of initial NAV, with distributions counted on the ex-date. | None. Day 1 is only the merge. | The pipeline moves a dividend whose ex-date is a dropped bond holiday to the next row; the plan counts distributions on the ex-date. |

## Other differences to settle at the same time

- **Trading days.** The plan says "actual exchange sessions"; the pipeline also drops Columbus Day and Veterans Day (NYSE open, bond market closed).
- **Schema.** The plan's `daily.csv` needs `category`, `volume`, `split_flag` and a `distribution` column; `panel.csv` has none of these.
- **Ownership.** The plan gives `data/raw/` and downloads to the partner. This branch added the NAV files and SOURCES.md.

## Decisions needed (one short note, then freeze in `docs/spec.md`)

1. Universe: plan's 6, pipeline's 9, or another set. If IGIB/SUB are added, they still need downloading.
2. End date: 2025-12-31 or latest available. Also whether to re-pull prices for a 2014 warm-up.
3. Threshold: 25bp fixed, a quantile, or something else. If a quantile, it must be computed without the evaluation period.
4. Spacing: exactly t+5 allowed (pipeline) or not (plan's wording). Also, do left-censored first-day events and events without 5 following sessions count?
5. Sign convention for shared files.
6. Whether Columbus Day and Veterans Day stay excluded.

Not done on purpose: no thresholds or rules were changed, and no outcome or model work was started.
