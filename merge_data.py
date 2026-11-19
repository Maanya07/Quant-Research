"""
merge_data.py  -  Day 1 merge script for the bond ETF discount project.

What it does
  1. Reads each fund's iShares NAV download (the "Historical" sheet).
  2. Pulls RAW closing prices and dividends from yfinance (auto_adjust=False) and caches them.
  3. Joins price and NAV by date, drops bond-market holidays, moves any dividend that
     falls on a dropped day to the next trading day.
  4. Computes the daily discount (close / NAV - 1) and log gap (ln(close / NAV)).
  5. Flags "large discount" events (PROVISIONAL): bottom 5% of each fund's own history,
     first day of each continuous episode, events at least 5 trading days apart.
  6. Writes a validation report and one discount chart per fund.

Folder layout (relative to where you run it)
  data/raw/nav/      one iShares download per fund, RENAMED to start with the ticker,
                     e.g. LQD.xls, HYG.xlsx, or LQD.csv if you re-saved it
  data/raw/prices/   filled automatically with cached yfinance pulls
  data/corrections/  documented fixes applied at processing time (raw files stay untouched):
                     price_exclusions.csv, dividend_supplements.csv
  data/clean/        outputs: panel.csv, events.csv, validation_report.txt
  figures/           outputs: discount_<TICKER>.png

Usage
  python merge_data.py              # pulls prices from yfinance (needs internet) and caches them
  python merge_data.py --offline    # re-runs using cached prices only
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = ["SHY", "IEF", "TLT", "LQD", "IGSB", "HYG", "SHYG", "MUB", "EMB"]
START = "2015-01-01"
EVENT_PCT = 0.05   # "large discount" = bottom 5% of a fund's own discount history
MIN_GAP = 5        # events at least 5 trading days apart
EVENT_STATUS = "provisional"   # event rule/threshold not yet agreed (see docs/spec_comparison.md)

SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"


# --------------------------------------------------------------------------- NAV files

def load_ishares_nav(path: str | Path) -> pd.DataFrame:
    """Return a DataFrame with columns [date, nav], sorted by date, from an iShares download.

    Handles: real Excel files (.xlsx/.xls), the old XML "SpreadsheetML" format iShares
    often serves with a .xls extension, and CSVs you re-saved yourself.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _standardize_nav(pd.read_csv(path))

    raw = path.read_bytes()
    if raw.lstrip()[:5] == b"<?xml" or SS_NS.encode() in raw[:2000]:
        return _standardize_nav(_read_spreadsheetml_sheet(raw, "Historical"))

    return _standardize_nav(pd.read_excel(path, sheet_name="Historical"))


def _read_spreadsheetml_sheet(raw: bytes, sheet_name: str) -> pd.DataFrame:
    text = raw.decode("utf-8-sig", errors="replace")
    # iShares files sometimes contain bare "&" characters, which break XML parsers.
    text = re.sub(r"&(?!(?:amp|lt|gt|quot|apos);|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    root = ET.fromstring(text)

    for ws in root.iter(f"{{{SS_NS}}}Worksheet"):
        if ws.get(f"{{{SS_NS}}}Name", "").strip().lower() != sheet_name.lower():
            continue
        rows = []
        for row in ws.iter(f"{{{SS_NS}}}Row"):
            cells: list[str | None] = []
            for cell in row.findall(f"{{{SS_NS}}}Cell"):
                idx = cell.get(f"{{{SS_NS}}}Index")      # SpreadsheetML can skip empty cells
                if idx is not None:
                    cells.extend([None] * (int(idx) - 1 - len(cells)))
                data = cell.find(f"{{{SS_NS}}}Data")
                cells.append(data.text if data is not None else None)
            rows.append(cells)

        header_i = next((i for i, r in enumerate(rows)
                         if any(c and "nav" in c.lower() for c in r)), None)
        if header_i is None:
            raise ValueError(f"No header row containing 'NAV' in sheet '{sheet_name}'")
        header = [c.strip() if c else f"col{j}" for j, c in enumerate(rows[header_i])]
        body = [r + [None] * (len(header) - len(r)) for r in rows[header_i + 1:]]
        return pd.DataFrame([r[:len(header)] for r in body], columns=header)

    raise ValueError(f"No worksheet named '{sheet_name}' found")


def _standardize_nav(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c: str(c).strip().lower() for c in df.columns}
    date_col = next((c for c, l in cols.items() if "as of" in l or l == "date" or "date" in l), None)
    nav_col = next((c for c, l in cols.items() if "nav per share" in l), None) \
        or next((c for c, l in cols.items() if "nav" in l), None)
    if date_col is None or nav_col is None:
        raise ValueError(f"Could not find date and NAV columns. Columns were: {list(df.columns)}")

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce", format="mixed"),
        "nav": pd.to_numeric(df[nav_col].astype(str).str.replace(",", "").str.strip(),
                             errors="coerce"),
    })
    out = out.dropna()
    out["date"] = out["date"].dt.normalize()
    out = out.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- prices

def normalize_close(raw: pd.DataFrame) -> pd.Series:
    """Pull the RAW 'Close' column out of a yfinance download (never 'Adj Close')."""
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs("Close", axis=1, level=0)
    else:
        close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    idx = pd.DatetimeIndex(close.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    close = pd.Series(close.to_numpy(dtype=float), index=idx.normalize(), name="close")
    return close.dropna()


def normalize_dividends(divs: pd.Series) -> pd.Series:
    """Ex-dividend dates as tz-naive dates, amounts summed per day."""
    if divs is None or len(divs) == 0:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]), name="div")
    idx = pd.DatetimeIndex(divs.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(np.asarray(divs, dtype=float), index=idx.normalize(), name="div")
    return s.groupby(level=0).sum()


def fetch_prices(ticker: str, start: str, cache_dir: Path, offline: bool):
    """Return (close, dividends) for a ticker, using/refreshing the local cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    close_f = cache_dir / f"{ticker}_close.csv"
    div_f = cache_dir / f"{ticker}_dividends.csv"

    if not offline:
        import yfinance as yf  # imported here so --offline works without it installed
        raw = yf.download(ticker, start=start, auto_adjust=False, actions=False, progress=False)
        if raw is None or raw.empty:
            raise RuntimeError(f"yfinance returned no price data for {ticker}")
        close = normalize_close(raw)
        divs = normalize_dividends(yf.Ticker(ticker).dividends)
        close.rename_axis("date").to_csv(close_f)
        divs.rename_axis("date").to_csv(div_f)
        (cache_dir / f"{ticker}_pulled_on.txt").write_text(dt.date.today().isoformat())

    if not close_f.exists():
        raise FileNotFoundError(f"No cached prices for {ticker}. Run once without --offline.")
    close = pd.read_csv(close_f, parse_dates=["date"]).set_index("date")["close"]
    divs = (pd.read_csv(div_f, parse_dates=["date"]).set_index("date")["div"]
            if div_f.exists() else normalize_dividends(None))
    return close, divs


# --------------------------------------------------------------------------- corrections
# Documented corrections live in data/corrections/ and are applied here, at processing
# time. The raw caches in data/raw/ are never edited.

def load_corrections(path: Path, date_col: str) -> pd.DataFrame:
    """Read a corrections CSV (ticker + date column + notes); empty frame if absent."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", date_col])
    df = pd.read_csv(path, dtype={"ticker": str})
    df[date_col] = pd.to_datetime(df[date_col]).dt.normalize()
    return df


def apply_price_exclusions(close: pd.Series, ticker: str, exclusions: pd.DataFrame) -> pd.Series:
    """Drop listed (ticker, date) closes so they can never enter the merge, even if a
    NAV for that date is supplied later."""
    bad = set(exclusions.loc[exclusions["ticker"] == ticker, "date"])
    return close[~pd.DatetimeIndex(close.index).normalize().isin(bad)]


def apply_dividend_supplements(divs: pd.Series, ticker: str, supplements: pd.DataFrame) -> pd.Series:
    """Add verified distributions missing from the cache. An ex-date the cache already
    has is left alone, so a later re-pull that fills the gap cannot double count."""
    divs = normalize_dividends(divs)
    add = supplements[supplements["ticker"] == ticker]
    add = add[~add["ex_date"].isin(divs.index)]
    if add.empty:
        return divs
    extra = pd.Series(add["amount"].astype(float).to_numpy(), index=pd.DatetimeIndex(add["ex_date"]), name="div")
    return pd.concat([divs, extra]).groupby(level=0).sum().rename("div")


# --------------------------------------------------------------------------- calendar

def bond_market_holidays(start_year: int, end_year: int) -> set[pd.Timestamp]:
    """Days the US bond market is closed but stocks trade: Columbus Day and Veterans Day.

    Columbus Day = 2nd Monday of October. Veterans Day = Nov 11 if a weekday,
    the following Monday if it falls on a Sunday, none if it falls on a Saturday.
    Double-check against SIFMA's published calendar for your sample years.
    """
    days: set[pd.Timestamp] = set()
    for y in range(start_year, end_year + 1):
        oct1 = pd.Timestamp(y, 10, 1)
        first_monday = oct1 + pd.Timedelta(days=(0 - oct1.weekday()) % 7)
        days.add(first_monday + pd.Timedelta(days=7))

        vet = pd.Timestamp(y, 11, 11)
        if vet.weekday() < 5:
            days.add(vet)
        elif vet.weekday() == 6:
            days.add(vet + pd.Timedelta(days=1))
    return days


# --------------------------------------------------------------------------- merge

def merge_fund(ticker: str, close: pd.Series, nav: pd.DataFrame, divs: pd.Series,
               holidays: set[pd.Timestamp]) -> pd.DataFrame:
    """Join price and NAV for one fund, drop holidays, align dividends, compute the gap."""
    px = close.rename("close").rename_axis("date").reset_index()
    px["date"] = pd.to_datetime(px["date"]).dt.normalize()
    df = nav.merge(px, on="date", how="inner")
    df = df[~df["date"].isin(holidays)].sort_values("date").reset_index(drop=True)

    # Put each dividend on the first remaining trading day on or after its ex-date,
    # so a dividend on a dropped day is not silently lost.
    df["div"] = 0.0
    dates = df["date"].to_numpy()
    # Ex-dates before the first merged day are outside the sample: skip them rather than
    # letting searchsorted pile every earlier dividend onto row 0.
    for d, amt in normalize_dividends(divs).items():
        if len(dates) == 0 or np.datetime64(d) < dates[0]:
            continue
        i = np.searchsorted(dates, np.datetime64(d))
        if i < len(df):
            df.loc[i, "div"] += float(amt)

    df["discount"] = df["close"] / df["nav"] - 1.0
    df["log_gap"] = np.log(df["close"] / df["nav"])
    df.insert(0, "ticker", ticker)
    return df[["ticker", "date", "close", "nav", "div", "discount", "log_gap"]]


# --------------------------------------------------------------------------- events

def flag_events(panel: pd.DataFrame, pct: float = EVENT_PCT, min_gap: int = MIN_GAP) -> pd.DataFrame:
    """Flag large-discount events within each fund. PROVISIONAL pending the agreed spec.

    A day is a candidate if its discount is at or below the fund's own `pct` quantile.
    An episode is an unbroken run of candidate rows; only its first day can be an event,
    and only if it is at least `min_gap` rows (trading days in the panel) after the
    previous event. A run starting too soon produces no event at all; later days of the
    same run never fire. The first row of the sample counts as an episode start.
    """
    out = []
    for _, g in panel.sort_values(["ticker", "date"]).groupby("ticker", sort=False):
        g = g.copy()
        thr = g["discount"].quantile(pct)
        cand = (g["discount"] <= thr).to_numpy()
        starts = cand & ~np.r_[False, cand[:-1]]
        event = np.zeros(len(g), dtype=bool)
        last = -10**9
        for i in np.flatnonzero(starts):
            if i - last >= min_gap:
                event[i] = True
                last = i
        g["event_threshold"] = thr
        g["event"] = event
        g["event_status"] = EVENT_STATUS
        out.append(g)
    return pd.concat(out).reset_index(drop=True)


# --------------------------------------------------------------------------- checks + plots

def validation_report(panel: pd.DataFrame, notes: list[str] | None = None) -> str:
    lines = ["VALIDATION REPORT", "=" * 60,
             f"Events are {EVENT_STATUS.upper()}: first day of each episode at or below the fund's",
             f"full-sample {EVENT_PCT:.0%} discount quantile, >= {MIN_GAP} sessions apart. Rule and",
             "threshold pending specification agreement.", "=" * 60]
    for t, g in panel.groupby("ticker"):
        worst = g.loc[g["discount"].idxmin()]
        lines += [
            f"{t}: {g['date'].min().date()} to {g['date'].max().date()}, {len(g)} days, "
            f"{int(g['event'].sum())} events",
            f"   duplicate dates: {int(g['date'].duplicated().sum())} | "
            f"missing values: {int(g[['close', 'nav']].isna().sum().sum())} | "
            f"days with |gap| > 10%: {int((g['discount'].abs() > 0.10).sum())}",
            f"   worst discount: {worst['discount']:.2%} on {worst['date'].date()} | "
            f"event cutoff: {g['event_threshold'].iloc[0]:.2%}",
        ]
    lqd = panel[(panel["ticker"] == "LQD") & (panel["date"] == "2020-03-19")]
    lines.append("=" * 60)
    if len(lqd):
        lines.append(f"LQD on 2020-03-19: {lqd['discount'].iloc[0]:.2%}  (expect roughly -5%)")
    else:
        lines.append("LQD on 2020-03-19: not in data, so the March 2020 check could not run")
    if notes:
        lines += ["=" * 60, "Corrections and warnings (data/corrections/):"] + [f"   {n}" for n in notes]
    return "\n".join(lines)


def plot_discounts(panel: pd.DataFrame, fig_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    for t, g in panel.groupby("ticker"):
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.plot(g["date"], g["discount"] * 100, lw=0.8, label="Premium / discount")
        ev = g[g["event"]]
        ax.scatter(ev["date"], ev["discount"] * 100, s=12, color="crimson", zorder=3,
                   label=f"Large-discount event ({EVENT_STATUS})")
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_title(f"{t}: closing price vs NAV")
        ax.set_ylabel("% (negative = discount)")
        ax.legend(loc="lower left", fontsize=8)
        fig.tight_layout()
        fig.savefig(fig_dir / f"discount_{t}.png", dpi=150)
        plt.close(fig)


# --------------------------------------------------------------------------- main

def find_nav_file(nav_dir: Path, ticker: str) -> Path | None:
    hits = [p for p in nav_dir.glob("*") if p.is_file() and p.name.upper().startswith(ticker.upper())
            and p.name.upper()[len(ticker):len(ticker) + 1] in {".", "_", "-", " "}]
    if len(hits) > 1:
        raise RuntimeError(f"More than one NAV file for {ticker}: {[h.name for h in hits]}")
    return hits[0] if hits else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use cached prices only")
    ap.add_argument("--start", default=START)
    ap.add_argument("--root", default=".", help="project folder containing data/ and figures/")
    args = ap.parse_args(argv)

    root = Path(args.root)
    nav_dir, price_dir = root / "data/raw/nav", root / "data/raw/prices"
    clean_dir, fig_dir = root / "data/clean", root / "figures"
    clean_dir.mkdir(parents=True, exist_ok=True)
    corr_dir = root / "data/corrections"
    price_excl = load_corrections(corr_dir / "price_exclusions.csv", "date")
    div_supp = load_corrections(corr_dir / "dividend_supplements.csv", "ex_date")
    notes: list[str] = []

    frames = []
    for t in TICKERS:
        nav_path = find_nav_file(nav_dir, t)
        if nav_path is None:
            print(f"[skip] {t}: no NAV file in {nav_dir} (name it like {t}.xls)")
            continue
        nav = load_ishares_nav(nav_path)
        nav = nav[nav["date"] >= pd.Timestamp(args.start)]
        close, divs = fetch_prices(t, args.start, price_dir, args.offline)

        n_close = len(close)
        close = apply_price_exclusions(close, t, price_excl)
        if len(close) < n_close:
            notes.append(f"{t}: {n_close - len(close)} cached close(s) excluded per price_exclusions.csv")
        pulled = price_dir / f"{t}_pulled_on.txt"
        if pulled.exists() and len(close) and close.index.max() >= pd.Timestamp(pulled.read_text().strip()):
            msg = (f"WARNING {t}: cached close on {close.index.max().date()} is dated on/after the pull "
                   f"date and may be intraday; add it to data/corrections/price_exclusions.csv if so")
            print(msg)
            notes.append(msg)

        n_div = len(normalize_dividends(divs))
        divs = apply_dividend_supplements(divs, t, div_supp)
        if len(divs) > n_div:
            notes.append(f"{t}: {len(divs) - n_div} distribution(s) added per dividend_supplements.csv")

        years = (min(nav["date"].min(), close.index.min()).year,
                 max(nav["date"].max(), close.index.max()).year)
        frames.append(merge_fund(t, close, nav, divs, bond_market_holidays(*years)))
        print(f"[ok]   {t}: {len(frames[-1])} merged days")

    if not frames:
        print("Nothing merged. Put the NAV files in data/raw/nav/ first.")
        return 1

    panel = flag_events(pd.concat(frames, ignore_index=True))
    panel.to_csv(clean_dir / "panel.csv", index=False)
    panel[panel["event"]].to_csv(clean_dir / "events.csv", index=False)
    report = validation_report(panel, notes)
    (clean_dir / "validation_report.txt").write_text(report)
    plot_discounts(panel, fig_dir)

    print("\n" + report)
    print(f"\nWrote {clean_dir/'panel.csv'}, {clean_dir/'events.csv'} and charts in {fig_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
