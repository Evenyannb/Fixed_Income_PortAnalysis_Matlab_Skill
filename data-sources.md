# Market Data Sources Reference

## Supported Markets & Sources

### US_TREASURY
- **Source:** US Treasury XML feed (free, no key)
- **URL:** `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=YYYYMM`
- **Tenors:** 1M, 2M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y
- **Freshness:** Updated daily by 6pm ET
- **Fallback:** FRED series (see below)

FRED series IDs (backup):
```
DGS1MO  → 1-month
DGS3MO  → 3-month
DGS6MO  → 6-month
DGS1    → 1-year
DGS2    → 2-year
DGS5    → 5-year
DGS10   → 10-year
DGS30   → 30-year
```
FRED CSV endpoint: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10`

---

### SOFR_SWAP
- **Source:** FRED (New York Fed data)
- **SOFR overnight:** `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR`
- **Term SOFR rates:** CME Group publishes term SOFR (requires free registration)
- **Swap rates:** Yieldwatch.io API (free tier)
- **Tenors:** Overnight, 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 30Y
- **Note:** Full SOFR swap curve (OIS-based) requires bootstrapping from
  deposit + swap quotes. Use Term SOFR as approximation for short end.

FRED SOFR series:
```
SOFR        → overnight SOFR
SOFRINDEX   → SOFR index
```

---

### EUR_SWAP (€STR / EURIBOR swaps)
- **Source:** ECB Data Portal (free, no key)
- **ECB API base:** `https://data-api.ecb.europa.eu/service/data/`
- **€STR:** `FM.B.U2.EUR.FR.BB.ESTRVOLW.ST` (overnight)
- **EUR swap rates:** ECB publishes AAA-rated euro area yield curves
  - Dataset: `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{TENOR}Y`
  - Tenors: 1Y through 30Y

Yieldwatch.io fallback (Tier 2):
```
GET https://yieldwatch.io/api/v1/yields/eur-swap/latest
```

ECB Policy rates via FRED:
```
ECBDFR   → ECB deposit facility rate
ECBMRRFR → ECB main refinancing rate
```

---

### JGB (Japanese Government Bonds)
- **Source:** Ministry of Finance Japan (free, no key)
- **URL:** `https://www.mof.go.jp/english/jgbs/reference/interest_rate/`
- **CSV download:** `https://www.mof.go.jp/english/jgbs/reference/interest_rate/historical/jgbcme_all.csv`
- **Tenors:** 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 15Y, 20Y, 25Y, 30Y, 40Y
- **Freshness:** Updated daily

FRED backup series:
```
IRLTLT01JPM156N → Japan 10Y government bond (monthly, OECD)
```
Note: FRED only has Japan 10Y monthly. For full curve use MoF directly.

---

### UK_GILT
- **Source:** Bank of England (free, no key)
- **URL:** `https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp?Travel=NIxRSxSUx&FromSeries=1&ToSeries=50&DAT=RNG&FD=1&FM=Jan&FY=2024&TD=31&TM=Dec&TY=2026&VFD=Y&html.x=66&html.y=26&C=BLC&C=BLD&C=BLE&C=BLF&C=BLG&C=BLH&Filter=N`
- **FRED backup series:**
```
IRLTLT01GBM156N → UK 10Y gilt (monthly)
GBGBOND10Y      → 10Y gilt daily (if available)
```

---

### ECB_RATE (Policy rates only)
- **FRED series:**
```
ECBDFR   → Deposit facility rate (overnight, daily)
ECBMRRFR → Main refinancing rate (daily)
```
- Use for: rate hike/cut scenario analysis, spread to swap curve

---

## How to Fetch in Python (MCP server)

```python
import urllib.request
import csv
import json
from datetime import datetime, timedelta

def fetch_us_treasury(date='latest'):
    """Fetch from Treasury XML, fall back to FRED CSV"""
    if date == 'latest':
        # Try last 5 business days
        for days_back in range(1, 6):
            d = datetime.now() - timedelta(days=days_back)
            ym = d.strftime('%Y%m')
            url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
                   f"interest-rates/pages/xml?data=daily_treasury_yield_curve"
                   f"&field_tdr_date_value={ym}")
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    content = r.read().decode()
                    # Parse XML for latest entry
                    # Returns dict of {tenor: yield}
                    return parse_treasury_xml(content)
            except:
                continue
    return None

def fetch_fred_series(series_id):
    """Fetch single FRED series, no API key needed for CSV"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urllib.request.urlopen(url, timeout=10) as r:
        lines = r.read().decode().splitlines()
    reader = csv.DictReader(lines)
    rows = list(reader)
    # Return most recent non-empty value
    for row in reversed(rows):
        if row['VALUE'] != '.':
            return {'date': row['DATE'], 'value': float(row['VALUE'])}
    return None

def fetch_sofr_curve():
    """Build SOFR curve from FRED overnight + term structure approximation"""
    sofr_on = fetch_fred_series('SOFR')
    # Fetch Treasury curve as base, apply SOFR-Treasury spread approximation
    # For production: use CME Term SOFR API
    treasury = fetch_us_treasury()
    return {'overnight': sofr_on, 'curve': treasury, 'note': 'approx from Treasury'}

def fetch_jgb():
    """Fetch JGB curve from MoF Japan"""
    url = "https://www.mof.go.jp/english/jgbs/reference/interest_rate/historical/jgbcme_all.csv"
    with urllib.request.urlopen(url, timeout=15) as r:
        content = r.read().decode('utf-8', errors='replace')
    # Parse CSV, return latest row
    lines = content.splitlines()
    # MoF format: Date, 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 15Y, 20Y, 25Y, 30Y, 40Y
    reader = csv.reader(lines)
    rows = [r for r in reader if len(r) > 10 and r[0] != 'Date']
    latest = rows[-1]
    tenors = [1,2,3,4,5,6,7,8,9,10,15,20,25,30,40]
    yields = [float(v) if v.strip() else None for v in latest[1:len(tenors)+1]]
    return {'date': latest[0], 'maturities': tenors, 'yields': yields}
```

---

## Data Freshness & Limitations

| Market | Delay | Gaps | Notes |
|--------|-------|------|-------|
| US Treasury | Same day (6pm ET) | Weekends/holidays | Most reliable free source |
| SOFR overnight | 1 business day | Weekends | Via FRED |
| SOFR swap curve | Approximation only | — | Full curve needs CME API |
| EUR swap | 1 business day | Weekends | ECB AAA curve, not interbank |
| JGB | Same day | Weekends/holidays | MoF direct, very reliable |
| UK Gilt | 1 business day | Weekends | BoE API |
| ECB policy rate | Same day | — | Via FRED, very reliable |

## For Production / Swaptions

Tier 2 upgrades to consider:
- **yieldwatch.io** — clean REST API, US Treasury + some EUR data, free tier
- **EODHD** — broader coverage including real yields, free tier available
- **CME Group API** — Term SOFR rates (free with registration)
- For swaption vol surfaces: no free source exists; need Bloomberg or Refinitiv
