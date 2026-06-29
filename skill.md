---
name: matlab-mcp rates and yield curve construction
description: >
  Use this skill whenever the user wants to run MATLAB code, fetch live market data, 
  build financial models, analyze or forecast yield curves, model rate sensitivity, 
  price bonds or swaps, or do any quantitative fixed income/rates modeling — for ANY country or market, 
  not just the curated ones. Trigger for any request involving MATLAB execution, yield curves, rate shocks, 
  bond pricing, DV01, duration, swap rates, Nelson-Siegel fitting, PCA on rates, or cross-market comparison.
---

# MATLAB MCP — Rates & Yield Curve Modeling Skill

## STRICT RULES

1. **fprintf only.** Always use `fprintf()` to print MATLAB results. Silent
   assignments (`x = 42`) produce NO output.

2. **No HTML/SVG plots for financial charts.** Always generate plots in MATLAB:
   ```matlab
   figure('Visible','off');
   % ... plot code ...
   saveas(gcf, '/Users/yanliang/matlab-mcp/output/<descriptive_name>.png');
   fprintf('Plot saved: /Users/yanliang/matlab-mcp/output/<descriptive_name>.png\n');
   close(gcf);
   ```
   Create the folder first if needed: `mkdir -p /Users/yanliang/matlab-mcp/output`

3. **Data sourcing — official sources only, never improvise numbers.**

---

## Available Tools

| Tool | Purpose |
|------|---------|
| `run_matlab` | Execute MATLAB code, returns stdout |
| `get_variable` | Read a workspace variable by name |
| `fetch_market_data` | Fetch curated yield/rate data by market code |
| `fetch_url` | Fetch raw CSV/XML/JSON/text from any URL |

---

## Data Sourcing Decision Tree

**Step 1 — Is the market curated?**

`fetch_market_data` directly supports:
- `US_TREASURY` — US Treasury (treasury.gov), full curve 1M–30Y
- `JGB` — Ministry of Finance Japan (mof.go.jp), full curve 1Y–40Y
- `EUR_SWAP` — ECB AAA Euro Area Yield Curve, 1Y–30Y spot rates
- `ECB_RATE` — ECB deposit facility rate (single rate)

If the user asks for one of these → call `fetch_market_data(market=...)` directly.
Inject the returned `maturities` and `yields` into MATLAB.

**Step 2 — Market NOT curated (e.g. Australia, UK Gilts, Canada, Korea,
South Africa, India, China, etc.)**

First check `references/data-sources.md` — it has a "Tier 2: Known Leads"
section with specific URLs/APIs that have worked or look promising for
common markets (UK, Australia, Canada, etc.). If a lead exists there, try
`fetch_url` on it directly before doing a fresh web search.

If no lead exists, or the lead no longer works, follow this procedure —
do not skip steps, do not estimate numbers from memory or web-search
snippets directly:

1. **Web search** for the OFFICIAL source: the country's central bank,
   debt management office, or treasury/finance ministry. Look for a data
   page with a downloadable CSV/XML/JSON, not a news article.
   - Example queries: "Reserve Bank of Australia government bond yields
     CSV download", "Bank of Canada bond yield curve data API",
     "UK DMO gilt yields daily CSV"

2. **`fetch_url`** on the official data endpoint (prefer the raw
   CSV/XML/JSON link over an HTML page). If the page is HTML, fetch it
   anyway — `fetch_url` returns raw text and you can parse the table.

3. **Parse the data yourself** from the returned content: extract tenor
   (maturity in years) and yield (%) pairs for the latest date. State the
   source name, URL, and as-of date explicitly to the user.

4. **Continue with the SAME modeling workflow** as curated markets:
   - Inject `maturities` and `yields` into MATLAB via `run_matlab`
   - Fit Nelson-Siegel (see pattern below)
   - Print parameters + RMSE via `fprintf`
   - Plot via MATLAB and save PNG (per STRICT RULES above)
   - Interpret results in market context

5. **If no official machine-readable source can be found** after a
   reasonable search, tell the user clearly which sources were tried and
   why they didn't work — do not silently fall back to approximate or
   memorized numbers.

**Known official sources for common markets** are in
`references/data-sources.md` (Tier 2: Known Leads) — covers UK, Australia,
Canada, South Korea, Switzerland, China as starting points. These are
leads, not guaranteed endpoints — always verify via fetch_url/web search
since URLs and formats change over time.

**After successfully fetching a new (previously Tier 3) market**, tell the
user the working source/URL and suggest it be added to
`references/data-sources.md` under Tier 2 for next time.

---

## Core Modeling Patterns

**Note on curve fitting models:** Nelson-Siegel below is the default, but
not the only option. If the user asks for Svensson/NSS or a spline, or if
NS gives a poor RMSE / degenerate lambda, see
`references/modeling-patterns.md` section 0 for alternatives
(Nelson-Siegel-Svensson, cubic spline, pchip) and guidance on when to
switch.

### Nelson-Siegel Curve Fitting
```matlab
ns_model = @(b, m) b(1) ...
    + b(2) .* (1 - exp(-m/b(4))) ./ (m/b(4)) ...
    + b(3) .* ((1 - exp(-m/b(4))) ./ (m/b(4)) - exp(-m/b(4)));

b0    = [2.0, -1.5, 0.5, 2.0];
opts  = optimset('Display', 'off');
b_fit = lsqcurvefit(ns_model, b0, maturities, yields, [], [], opts);

fprintf('Beta0 (level):     %.4f\n', b_fit(1));
fprintf('Beta1 (slope):     %.4f\n', b_fit(2));
fprintf('Beta2 (curvature): %.4f\n', b_fit(3));
fprintf('Lambda:            %.4f yrs\n', b_fit(4));
rmse = sqrt(mean((ns_model(b_fit, maturities) - yields).^2));
fprintf('RMSE: %.2f bps\n', rmse * 100);
```

If `lsqcurvefit` gives a degenerate lambda (very large, e.g. >40yrs) or
RMSE is poor (e.g. >10 bps): first retry with bounds —
`lsqcurvefit(ns_model, b0, maturities, yields, [-10,-10,-10,0.5], ...
[10,10,10,15], opts)`. If still poor, tell the user and offer
Nelson-Siegel-Svensson or a spline instead (see
references/modeling-patterns.md section 0) — don't silently present a
bad NS fit as if it were fine.

### Rate Shock / Scenario Table
```matlab
shocks_bps = [25, 50, 100, -25];
tenors_out = [1, 2, 5, 10, 30];
fprintf('\n%-6s', 'Tenor');
for s = shocks_bps; fprintf('  %+dbps', s); end
fprintf('\n');
for i = 1:length(tenors_out)
    base_y = ns_model(b_fit, tenors_out(i));
    fprintf('%-6dy', tenors_out(i));
    for s = shocks_bps; fprintf('  %+.3f%%', base_y + s/100); end
    fprintf('\n');
end
```

### Bond Pricing + DV01
```matlab
periods  = maturity * freq;
coupon   = face * coupon_rate / freq;
cf       = [repmat(coupon,1,periods-1), coupon+face];
times    = (1:periods) / freq;
y_interp = interp1(maturities, yields, times, 'linear','extrap') / 100;
df       = exp(-y_interp .* times);
price    = sum(cf .* df);
duration = sum(times .* cf .* df) / price;
dv01     = price * duration * 0.0001;
fprintf('Price: %.4f | Duration: %.4f yrs | DV01: %.4f\n', price, duration, dv01);
```

### Cross-Market Comparison
1. Fetch each market (curated via `fetch_market_data`, others via the
   decision tree above)
2. Fit Nelson-Siegel to each independently
3. Print side-by-side tenor table with spread column
4. Compute spread at 2Y, 5Y, 10Y, 30Y
5. Interpret: steepness, inversion, cross-over points, macro implications

See references/modeling-patterns.md for: SOFR bootstrap, swaption Black's
model approximation, PCA on yield curve, carry & roll-down.

---

## Standard Workflow (any market)

1. Determine if market is curated → `fetch_market_data`, else follow the
   non-curated decision tree (web search → `fetch_url` → parse)
2. `run_matlab` → inject data, print confirmation of key tenors with source + date
3. `run_matlab` → fit Nelson-Siegel, print parameters + RMSE
4. `run_matlab` → plot and save PNG (per STRICT RULES)
5. `run_matlab` → shock/pricing/spread analysis as requested
6. Interpret results with market context, citing the data source used

---

## Toolbox Requirements

| Task | Required |
|------|----------|
| lsqcurvefit, fmincon | Optimization Toolbox |
| arima, estimate | Econometrics Toolbox |
| fitlm, regress | Statistics & ML Toolbox |
| ode45, fft, interp1, fminsearch | Built-in, no toolbox needed |

If a toolbox is missing, fall back to `fminsearch` for curve fitting.
See references/modeling-patterns.md for toolbox-free alternatives.

---

## Portfolio & Snapshot Tools

### Available Tools (full list)

| Tool | Purpose |
|------|---------|
| `run_matlab` | Execute MATLAB code |
| `get_variable` | Read workspace variable |
| `fetch_market_data` | Fetch curated live data |
| `fetch_url` | Fetch any official URL |
| `save_snapshot` | Persist a curve to disk |
| `load_snapshot` | Load a saved curve |
| `list_snapshots` | Show what's saved |
| `diff_snapshots` | Yield changes between two dates |
| `manage_positions` | Read/add/remove bond positions |

---

### Snapshot Workflow

**After every fetch_market_data call, always save_snapshot immediately.**
This builds the historical record that makes "what moved" questions possible.

```
fetch_market_data(market="JGB")
→ save_snapshot(data={...returned data...})
→ confirms: "Saved JGB_2026-06-14.json"
```

For "what moved since X" questions:
```
list_snapshots(market="JGB")           → see what dates are available
diff_snapshots(market="JGB",
    date1="2026-06-07", date2="2026-06-14")
→ returns bps change at each tenor + max mover + approx parallel shift
→ inject into run_matlab for further analysis or plotting
```

---

### Positions Workflow

Positions file lives at `~/matlab-mcp/positions.csv`. Format:

| Field | Example | Notes |
|-------|---------|-------|
| bond_id | JGB_10Y_2036 | Unique identifier |
| market | JGB | Matches fetch_market_data market codes |
| maturity_yr | 10.5 | Years to maturity from today |
| coupon_pct | 0.8 | Annual coupon in percent |
| face_notional | 1000000000 | Face value in local currency |
| side | long / short | Direction |
| description | 10Y JGB Mar26 | Free text |

**Morning check workflow** (the core PM use case):
1. `manage_positions(action="list")` — load the book
2. `fetch_market_data` for each market in the book + `save_snapshot`
3. If prior snapshot exists: `diff_snapshots` for each market
4. `run_matlab` — for each position, compute price + DV01 vs current curve,
   then aggregate total book DV01 by market
5. Flag positions where curve move × DV01 > threshold (e.g. >$50k impact)
6. Generate summary

**Portfolio DV01 aggregation pattern:**
```matlab
% After loading positions and fitting NS curves per market:
% positions = struct array loaded from manage_positions output

total_dv01_usd = 0;
fprintf('\n%-20s %-8s %-8s %-10s %-12s\n', ...
    'Bond','Side','Mat(yr)','DV01','P&L Impact');
fprintf('%s\n', repmat('-',1,65));

for i = 1:length(positions)
    p = positions(i);
    % Get yield at maturity from fitted NS curve for that market
    y = ns_model(b_fit.(p.market), p.maturity_yr) / 100;
    % Simple price (approximate — no day count)
    freq = 2;
    periods = round(p.maturity_yr * freq);
    coupon = p.face_notional * (p.coupon_pct/100) / freq;
    cf = [repmat(coupon, 1, periods-1), coupon + p.face_notional];
    times = (1:periods) / freq;
    df = exp(-y .* times);
    price = sum(cf .* df);
    duration = sum(times .* cf .* df) / price;
    dv01 = price * duration * 0.0001;
    sign = 1;
    if strcmp(p.side, 'short'); sign = -1; end
    fprintf('%-20s %-8s %-8.1f %-10.0f %-12.0f\n', ...
        p.bond_id, p.side, p.maturity_yr, dv01*sign, dv01*sign*100);
    total_dv01_usd = total_dv01_usd + dv01 * sign;
end
fprintf('%s\n', repmat('-',1,65));
fprintf('%-38s %-10.0f\n', 'TOTAL BOOK DV01 (USD/bp)', total_dv01_usd);
```

---

### Adding Positions

Ask the user to confirm details, then:
```
manage_positions(
    action="add",
    bond_id="JGB_10Y_2036",
    market="JGB",
    maturity_yr=10.0,
    coupon_pct=0.8,
    face_notional=1000000000,
    side="long",
    description="10Y JGB benchmark"
)
```

Always confirm back: "Added JGB_10Y_2036 — your book now has N positions."

---

### Caveats to State Clearly

- Pricing is **approximate**: no day-count convention, no accrued interest,
  no settlement date offset. For indicative DV01/sensitivity analysis only.
  Not for actual trade pricing.
- DV01 is in local currency — USD/JPY/EUR conversion not applied unless
  user asks and provides FX rate.
- "Morning check" depends on snapshots existing — first run will have no
  prior date to diff against; tell the user this and offer to save today's
  as the baseline.