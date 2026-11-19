"""Tests for merge_data.py. Run with:  python -m unittest -v test_merge_data
(pytest also works if you have it installed.)"""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import merge_data as md


SPREADSHEETML = """<?xml version="1.0"?>
<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <ss:Worksheet ss:Name="Overview">
  <ss:Table>
   <ss:Row><ss:Cell><ss:Data ss:Type="String">iShares Fund & Co</ss:Data></ss:Cell></ss:Row>
  </ss:Table>
 </ss:Worksheet>
 <ss:Worksheet ss:Name="Historical">
  <ss:Table>
   <ss:Row>
    <ss:Cell><ss:Data ss:Type="String">As Of</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="String">NAV per Share</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="String">Shares Outstanding</ss:Data></ss:Cell>
   </ss:Row>
   <ss:Row>
    <ss:Cell><ss:Data ss:Type="String">Mar 20, 2020</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="Number">115.25</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="Number">1000</ss:Data></ss:Cell>
   </ss:Row>
   <ss:Row>
    <ss:Cell><ss:Data ss:Type="String">Mar 19, 2020</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="Number">116.50</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="Number">1000</ss:Data></ss:Cell>
   </ss:Row>
   <ss:Row>
    <ss:Cell><ss:Data ss:Type="String">Mar 18, 2020</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="String">--</ss:Data></ss:Cell>
    <ss:Cell><ss:Data ss:Type="Number">1000</ss:Data></ss:Cell>
   </ss:Row>
  </ss:Table>
 </ss:Worksheet>
</ss:Workbook>
"""


class TestLoadNav(unittest.TestCase):
    def test_reads_historical_sheet_from_spreadsheetml_with_bare_ampersand(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "LQD_fund.xls"
            p.write_text(SPREADSHEETML)
            nav = md.load_ishares_nav(p)
        self.assertEqual(list(nav.columns), ["date", "nav"])
        self.assertEqual(len(nav), 2)  # the "--" row is dropped
        self.assertEqual(nav["date"].iloc[0], pd.Timestamp("2020-03-19"))  # sorted ascending
        self.assertAlmostEqual(nav["nav"].iloc[0], 116.50)

    def test_reads_historical_sheet_from_real_xlsx(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "HYG_fund.xlsx"
            with pd.ExcelWriter(p) as w:
                pd.DataFrame({"x": [1]}).to_excel(w, sheet_name="Holdings", index=False)
                pd.DataFrame({"As Of": ["01/03/2017", "01/04/2017"],
                              "NAV per Share": [86.1, "-"]}).to_excel(w, sheet_name="Historical", index=False)
            nav = md.load_ishares_nav(p)
        self.assertEqual(len(nav), 1)
        self.assertEqual(nav["date"].iloc[0], pd.Timestamp("2017-01-03"))
        self.assertAlmostEqual(nav["nav"].iloc[0], 86.1)

    def test_reads_resaved_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "SHY.csv"
            p.write_text("As Of,NAV per Share\n2021-06-01,86.20\n2021-06-02,86.21\n")
            nav = md.load_ishares_nav(p)
        self.assertEqual(len(nav), 2)


class TestPrices(unittest.TestCase):
    def test_uses_raw_close_not_adjusted_close_from_multiindex_frame(self):
        idx = pd.DatetimeIndex(["2020-03-19", "2020-03-20"], name="Date")
        cols = pd.MultiIndex.from_product([["Adj Close", "Close", "Volume"], ["LQD"]],
                                          names=["Price", "Ticker"])
        raw = pd.DataFrame([[100.0, 110.0, 5], [101.0, 111.0, 6]], index=idx, columns=cols)
        close = md.normalize_close(raw)
        self.assertEqual(list(close.values), [110.0, 111.0])

    def test_dividend_index_becomes_tz_naive_dates(self):
        idx = pd.DatetimeIndex(["2020-03-02 00:00:00-05:00"]).tz_convert("America/New_York")
        divs = pd.Series([0.25], index=idx)
        out = md.normalize_dividends(divs)
        self.assertEqual(out.index[0], pd.Timestamp("2020-03-02"))
        self.assertIsNone(out.index.tz)


class TestBondHolidays(unittest.TestCase):
    def test_columbus_and_weekday_veterans_day(self):
        h = md.bond_market_holidays(2020, 2020)
        self.assertIn(pd.Timestamp("2020-10-12"), h)  # 2nd Monday of October
        self.assertIn(pd.Timestamp("2020-11-11"), h)  # Wednesday

    def test_veterans_day_sunday_observed_monday_saturday_skipped(self):
        h = md.bond_market_holidays(2018, 2023)
        self.assertIn(pd.Timestamp("2018-11-12"), h)      # Nov 11 2018 was a Sunday
        self.assertNotIn(pd.Timestamp("2023-11-10"), h)   # Nov 11 2023 was a Saturday
        self.assertIn(pd.Timestamp("2023-10-09"), h)


class TestMerge(unittest.TestCase):
    def _inputs(self):
        dates = pd.to_datetime(["2020-10-09", "2020-10-12", "2020-10-13", "2020-10-14"])
        close = pd.Series([97.0, 98.0, 99.0, 100.0], index=dates)
        nav = pd.DataFrame({"date": dates, "nav": [100.0, 100.0, 100.0, 100.0]})
        divs = pd.Series([0.30], index=pd.to_datetime(["2020-10-12"]))  # lands on Columbus Day
        return close, nav, divs

    def test_computes_discount_and_log_gap(self):
        close, nav, divs = self._inputs()
        out = md.merge_fund("TEST", close, nav, divs, holidays=set())
        first = out.iloc[0]
        self.assertAlmostEqual(first["discount"], -0.03)
        self.assertAlmostEqual(first["log_gap"], math.log(0.97))

    def test_drops_bond_holiday_and_moves_its_dividend_to_next_day(self):
        close, nav, divs = self._inputs()
        out = md.merge_fund("TEST", close, nav, divs, holidays={pd.Timestamp("2020-10-12")})
        self.assertNotIn(pd.Timestamp("2020-10-12"), set(out["date"]))
        self.assertAlmostEqual(out.loc[out["date"] == "2020-10-13", "div"].iloc[0], 0.30)
        self.assertAlmostEqual(out["div"].sum(), 0.30)


class TestEvents(unittest.TestCase):
    def test_first_day_of_cluster_flagged_and_spacing_enforced(self):
        n = 40
        disc = np.zeros(n)
        disc[[10, 11, 12]] = -0.02   # one cluster -> only day 10 flagged
        disc[14] = -0.02             # within 5 trading days of day 10 -> skipped
        disc[20] = -0.02             # far enough -> flagged
        panel = pd.DataFrame({"ticker": "A",
                              "date": pd.bdate_range("2021-01-01", periods=n),
                              "discount": disc})
        out = md.flag_events(panel, pct=0.10, min_gap=5)
        flagged = list(np.flatnonzero(out["event"].to_numpy()))
        self.assertEqual(flagged, [10, 20])

    def test_threshold_is_computed_within_each_fund(self):
        dates = pd.bdate_range("2021-01-01", periods=20)
        a = pd.DataFrame({"ticker": "A", "date": dates, "discount": np.linspace(-0.001, 0.001, 20)})
        b = pd.DataFrame({"ticker": "B", "date": dates, "discount": np.linspace(-0.05, 0.05, 20)})
        out = md.flag_events(pd.concat([a, b]), pct=0.05, min_gap=5)
        # each fund gets its own event even though A's discounts are tiny
        self.assertTrue(out.loc[out["ticker"] == "A", "event"].any())
        self.assertTrue(out.loc[out["ticker"] == "B", "event"].any())


if __name__ == "__main__":
    unittest.main()
