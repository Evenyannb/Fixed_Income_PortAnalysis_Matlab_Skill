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

**What these yields are:**
US Treasury yields are **sovereign government bond par yields** — the rate
the US government pays to borrow. They are NOT SOFR and NOT LIBOR.

| Rate | What it is | Use for |
|------|-----------|---------|
| US Treasury yield | US govt borrowing rate, risk-free, sovereign | Government bond pricing, risk-free base curve |
| SOFR | Overnight secured interbank rate (replaced LIBOR 2023) | USD swap pricing, floating rate instruments |
| LIBOR | Was unsecured interbank rate — **defunct as of June 2023** | Legacy contracts only, do not use for new analysis |

**Relationship:** SOFR swap rates ≈ Treasury yield + swap spread (typically
+10 to +30 bps depending on tenor and market conditions). The swap spread
reflects credit, liquidity, and supply/demand differences between govvies
and the interbank market.

**Implication for this tool:** `US_TREASURY` data is correct for a
government bond book. If the PM trades USD interest rate swaps or
floating-rate instruments, a separate SOFR swap curve is needed —
see the SOFR section below.

### SOFR (USD Swap Curve) — NOT currently curated
**SOFR is not the same as US Treasury yields.** It is the Secured Overnight
Financing Rate — the benchmark rate for USD interest rate swaps since LIBOR
was discontinued in June 2023.

**What you need for a full SOFR swap curve:**
- **Short end (overnight to 1Y):** CME Term SOFR rates — free with
  registration at `cmegroup.com/market-data/sofr-benchmark-data.html`
- **Long end (2Y–30Y):** SOFR OIS swap rates — no free public machine-readable
  source; requires Bloomberg, Refinitiv, or a broker feed
- **Bootstrap:** deposit rates (short end) + swap rates (long end) →
  zero/discount curve (see `modeling-patterns.md` section 1)

**Practical options:**
1. Use US Treasury curve as a **proxy** — directionally correct, understates
   rates by the swap spread (typically 10–30bps). Flag this to the PM.
2. Register for CME Term SOFR (free) for short-end rates
3. Manually input long-end swap rates from a Bloomberg/Reuters screen

**Note for EUR:** The equivalent is €STR (Euro Short-Term Rate), which
replaced EURIBOR as the RFR. The ECB AAA curve fetched by `EUR_SWAP` is
a government bond curve — not a swap curve. The same distinction applies.

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

**Important — this is NOT an interbank swap curve:**
The ECB AAA curve is the yield on AAA-rated euro area government bonds
(Germany, Netherlands, Finland etc.) — it is a **sovereign bond curve**,
not a €STR/EURIBOR swap curve.

| Rate | What it is |
|------|-----------|
| ECB AAA curve (what we fetch) | AAA euro govt bond yields — sovereign, risk-free proxy |
| €STR swap curve | Euro overnight index swap rates — interbank, replaced EURIBOR |
| EURIBOR | Term interbank rate — still exists but no longer the RFR benchmark |

**For EUR swap pricing:** the €STR OIS curve is needed, which has no
free machine-readable public source. Use the ECB AAA curve as a proxy
for government bond analysis; flag the distinction to the PM if they
are pricing swaps against this curve.

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

### AUSTRALIA (Australian Government Bonds / ACGBs) — VERIFIED
- **Source:** RBA Table F16 — "Indicative Mid Rates of Selected Australian
  Government Securities"
- **URL:** `https://www.rba.gov.au/statistics/tables/` → search "F16" or
  fetch directly — RBA also lists on the AOFM Data Hub
  (`https://www.aofm.gov.au/data-hub`)
- **Format:** CSV, individual bond-by-bond mid yields — NOT interpolated
  tenors. As of Sep 2026: 30 nominal lines from ~0.6y (e.g. Apr-27) out to
  ~28y (e.g. Jun-54)
- **Why F16 over F2:** Table F2 ("Capital Market Yields — Government
  Bonds") only gives 4 interpolated points (2Y/3Y/5Y/10Y). F16 gives the
  real bond-by-bond curve — 30 individual securities — which is what you
  want for a proper Nelson-Siegel fit. Prefer F16.
- **Freshness:** ~2 business day lag (e.g. a file published 4 Sep
  contained data as of 2 Sep). Expect Australia to run a few sessions
  behind US/JGB/EUR in any cross-market comparison.
- **Known data-quality note:** the file can include a very short-dated
  line (e.g. maturing in under 3 weeks) priced off money-market
  conventions rather than bond conventions — this typically sits well
  off the fitted curve and is standard practice to exclude from a
  Nelson-Siegel fit. Worth a sanity check on the shortest maturity before
  fitting.
- **Verified working:** 2026-09-08 — fetched via `fetch_url`, fit
  Nelson-Siegel successfully (RMSE 2.4bp, R²=0.9921, n=30 bonds)

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

**MATLAB CSV parsing gotcha — always use `'CollapseDelimiters', false`**
When parsing a fetched CSV in MATLAB with `strsplit`, the default behavior
collapses consecutive delimiters (e.g. `,,` from an empty field). For any
CSV with sparse/empty fields — common in government data tables where not
every bond has a value in every column — this silently drops the empty
field and shifts every subsequent value onto the wrong column. The
failure is silent: it produces a plausible-looking curve with no error,
just wrong numbers (symptom: RMSE much worse than expected, or the curve
doing something structurally odd like going negative at long tenors).

Always parse with:
```matlab
fields = strsplit(line, ',', 'CollapseDelimiters', false);
```
This was first hit on the RBA F16 fetch (2026-09-08) — first attempt gave
RMSE 92bp and a curve going negative past 15Y before the fix. Apply this
flag proactively to any new sparse-matrix CSV source, not just RBA.
