# Market Data Sources Reference

This file has three tiers. Check them in order before falling back to a
fresh web search.

- **Tier 1 — Curated & wired in.** Fully implemented in `fetch_market_data`.
  Just call the tool with the market code.
- **Tier 2 — Known leads.** A specific URL/endpoint that has worked before
  or looks promising, but is NOT wired into `fetch_market_data`. Try
  `fetch_url` on these directly — usually faster than a fresh search.
- **Tier 3 — Unknown.** Not documented here. Follow the full decision tree:
  web search for the official source → `fetch_url` → parse.

**When you successfully find a working source for a Tier 2/3 market,
add it here (with the working URL and date format notes) so future
requests can skip straight to Tier 2.**

---

## Tier 1 — Curated & Wired In

### US_TREASURY
- `fetch_market_data(market="US_TREASURY")`
- Source: US Treasury XML feed (treasury.gov), free, no key
- Tenors: 1M, 2M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y
- Freshness: same day, updated ~6pm ET, no weekend/holiday data

### JGB
- `fetch_market_data(market="JGB")`
- Source: Ministry of Finance Japan CSV (mof.go.jp), free, no key
- Tenors: 1Y–10Y, 15Y, 20Y, 25Y, 30Y, 40Y
- Freshness: same day, no weekend/holiday data

### EUR_SWAP
- `fetch_market_data(market="EUR_SWAP")`
- Source: ECB AAA Euro Area Yield Curve, Svensson model spot rates
  (data-api.ecb.europa.eu), free, no key
- Tenors: 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y, 30Y
- Freshness: ~1 business day delay
- Note: this is AAA government bond spot rates, not interbank swap rates —
  close proxy but mention this distinction if precision matters

### ECB_RATE
- `fetch_market_data(market="ECB_RATE")`
- Source: ECB Data Portal, deposit facility rate (single value)
- Freshness: same day, very reliable

---

## Tier 2 — Known Leads (try fetch_url first)

### UK_GILT (UK government bonds)
- **Lead:** Bank of England Interactive Database
- **URL pattern:**
  ```
  https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp?Travel=NIxRSxSUx&FromSeries=1&ToSeries=50&DAT=RNG&FD=1&FM=Jan&FY=2024&TD=31&TM=Dec&TY=2026&VFD=Y&html.x=66&html.y=26&C=BLC&C=BLD&C=BLE&C=BLF&C=BLG&C=BLH&Filter=N
  ```
- **Format:** HTML table with date-indexed columns (BLC, BLD, etc. = different gilt series codes)
- **Status:** untested with fetch_url — series codes (C=BLC etc.) may need
  remapping to specific tenors. Try fetching and inspect column headers.
- **Alternative:** UK Debt Management Office (dmo.gov.uk) publishes daily
  gilt prices/yields as downloadable files — search "DMO gilt market
  prices download"

### AUSTRALIA (Australian Government Bonds / ACGBs)
- **Lead:** Reserve Bank of Australia statistical tables
- **Starting point:** `https://www.rba.gov.au/statistics/tables/` — look for
  "Capital Market Yields - Government Bonds" (table F2 or similar)
- **Format:** typically XLS/CSV download, daily yields for 2Y/3Y/5Y/10Y ACGBs
- **Status:** untested — find current table number via web search
  ("RBA F2 capital market yields government bonds csv")

### CANADA
- **Lead:** Bank of Canada Valet API (machine-readable, free, no key)
- **Starting point:** `https://www.bankofcanada.ca/valet/docs` — series like
  `BD.CDN.2YR.DQ.YLD`, `BD.CDN.10YR.DQ.YLD`
- **Format:** JSON or CSV via Valet API, e.g.
  `https://www.bankofcanada.ca/valet/observations/BD.CDN.10YR.DQ.YLD/json?recent=1`
- **Status:** untested but Valet API is well-documented and historically
  reliable — good first try

### SOUTH KOREA
- **Lead:** Bank of Korea ECOS API
- **Starting point:** `https://ecos.bok.or.kr/api/` — requires free API key
  registration (not "no key" like others)
- **Status:** untested, lower priority due to key requirement

### SWITZERLAND
- **Lead:** SNB data portal (data.snb.ch)
- **Starting point:** search "SNB government bond yields data portal csv"
- **Status:** untested

### CHINA
- **Lead:** ChinaBond (chinabond.com.cn) publishes official yield curves
  but site is primarily Chinese-language and may need translation of
  query parameters
- **Status:** untested, likely needs web search per request

---

## Tier 3 — Unknown Markets

For anything not listed above (India, Brazil, Mexico, Nordic countries,
emerging markets, etc.):

1. Web search: "<country> government bond yield curve official data CSV"
   or "<country central bank> bond yields API"
2. Prefer: central bank statistical databases > debt management office >
   finance ministry > stock exchange
3. Avoid: news aggregators, Investing.com, TradingEconomics (these are
   secondary sources, fine for a sanity check but not as the primary
   number if an official source exists)
4. Once found and working, document it here under Tier 2 for next time

---

## General Notes

- Government bond yields are usually more accessible (official, free) than
  swap rates — for swaps/swaptions in non-USD/EUR markets, expect to need
  Bloomberg/Refinitiv or accept government bond yields as a proxy
- Always state the source name, URL, and as-of date when presenting fetched
  data to the user
- If a Tier 2 lead stops working (URL changed, format changed), note the
  failure and fall back to Tier 3 for that request — then update this file
  with the corrected lead
