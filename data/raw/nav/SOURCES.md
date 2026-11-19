# iShares NAV downloads: provenance

All nine files are the unmodified "Data Download" spreadsheets from each fund's official iShares
product page, renamed only (`<TICKER>.xls`). Byte-for-byte copies; do not edit. Format is the
XML "SpreadsheetML" workbook that iShares serves with an `.xls` extension, with sheets
`Disclaimers, Holdings, Historical, Performance, Distributions`. The pipeline reads only
`Historical` (columns `As Of, NAV per Share, Ex-Dividends, Shares Outstanding`), which is the
daily NAV-per-share history, not the holdings snapshot.

Retrieved: 2026-11-19 by Maanya, between 21:13:20 and 21:14:23 UTC (HTTP `Date` headers).
Each file's latest NAV is 2026-11-18 (holdings snapshot also dated 2026-11-18).

Download endpoint (the link behind "Data Download" on each product page; only `portfolioId` varies):
`https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=<ID>&component=fundDownload&userType=individual`

| File | Product page | portfolioId | Served filename | Bytes | SHA-256 |
|---|---|---|---|---|---|
| LQD.xls | https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf | 239566 | iShares-iBoxx--Investment-Grade-Corporate-Bond-ETF_fund.xls | 9024433 | fbdf2728f5987ff3522fb0d1eb33e5a2a88e0eb6ce5dd7d08ff0e1a52220d5fc |
| HYG.xls | https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf | 239565 | iShares-iBoxx--High-Yield-Corporate-Bond-ETF_fund.xls | 4697020 | a64e5de8c15e0a9ab48a8ad2e4aa385ccc04944fbc932c82f1f1a79939c83503 |
| MUB.xls | https://www.ishares.com/us/products/239766/ishares-national-muni-bond-etf | 239766 | iShares-National-Muni-Bond-ETF_fund.xls | 18153702 | 6da87a08eae5bf043d1f0e6da83c2e89c40cac48d46bdfa5ee1c64ca7a7dd6a9 |
| SHYG.xls | https://www.ishares.com/us/products/258100/ishares-0-5-year-high-yield-corporate-bond-etf | 258100 | iShares-0-5-Year-High-Yield-Corporate-Bond-ETF_fund.xls | 3662995 | 2a57af65fa211d12316b00d4280c2d5b4811a49eb199c8e55eae12d6911a7302 |
| SHY.xls | https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf | 239452 | iShares-1-3-Year-Treasury-Bond-ETF_fund.xls | 2637148 | efce5ca3ef5170a68ba5e0f917b8b90306d28459be9a6c842a09f7c734a4f536 |
| IEF.xls | https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf | 239456 | iShares-7-10-Year-Treasury-Bond-ETF_fund.xls | 2494091 | a61d69bb65a181def456f90bbff9cf861a6a6c24e13e063dbb43758818615e30 |
| TLT.xls | https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf | 239454 | iShares-20-Year-Treasury-Bond-ETF_fund.xls | 2552914 | 9cc94d1901d5018b5e0387fc2c93877ec9c662476c803eac6d9f31813d17067b |
| IGSB.xls | https://www.ishares.com/us/products/239451/ishares-short-term-corporate-bond-etf | 239451 | iShares-1-5-Year-Investment-Grade-Corporate-Bond-ETF_fund.xls | 11752480 | af0bfbafb3a7bba68ad443cf36380fc2962f2e49f853755ef4d5f69a65828380 |
| EMB.xls | https://www.ishares.com/us/products/239572/ishares-jp-morgan-usd-emerging-markets-bond-etf | 239572 | iShares-JP-Morgan-USD-Emerging-Markets-Bond-ETF_fund.xls | 3174137 | 292bd4decb30b14f8c9de015a32aa28dc4842c4b0ad584831d319b2e27409ffa |

## Actual coverage of the `Historical` sheet

| Ticker | First NAV | Last NAV | Rows (all) | Rows 2015-01-02 .. 2026-11-18 |
|---|---|---|---|---|
| LQD | 2002-07-22 | 2026-11-18 | 6125 | 2990 |
| HYG | 2007-04-04 | 2026-11-18 | 4941 | 2990 |
| MUB | 2007-09-07 | 2026-11-18 | 4833 | 2990 |
| SHYG | 2013-10-15 | 2026-11-18 | 3296 | 2990 |
| SHY | 2002-07-22 | 2026-11-18 | 6125 | 2990 |
| IEF | 2002-07-22 | 2026-11-18 | 6125 | 2990 |
| TLT | 2002-07-22 | 2026-11-18 | 6125 | 2990 |
| IGSB | 2007-01-05 | 2026-11-18 | 5003 | 2990 |
| EMB | 2007-12-17 | 2026-11-18 | 4765 | 2990 |

Every row has a numeric NAV; no duplicate dates. Every fund covers January 2015 onward with a
2014 warm-up available.

Quirks found in the raw files (left as-is; the price join drops them):
- 2024-03-29 (Good Friday, NYSE closed) has a NAV in every file.
- 2024-03-31 (Sunday, month-end) has a NAV with no shares outstanding in every file.
- Pre-2015 weekend rows: IGSB 2013-06-30; EMB 2013-06-30 and 2013-08-31.
- Each workbook has six bare `&` characters, which `merge_data.py` already escapes.

Not yet audited: historical fund-name, index, and mandate changes. For example, IGSB's current
name is "1-5 Year Investment Grade Corporate Bond ETF"; check its earlier ticker, name, and index
in fund filings. The download only shows current names.
