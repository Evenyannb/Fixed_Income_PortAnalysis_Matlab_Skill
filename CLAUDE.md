---
name: matlab-mcp
description: >
  Use this skill whenever the user wants to run MATLAB code, fetch live market data,
  build financial models, analyze or forecast yield curves, model rate sensitivity,
  price bonds or swaps, analyze SOFR curves, European rates, JGB yields, or do any
  quantitative fixed income or rates modeling. Trigger for any request involving
  MATLAB execution, yield curves, rate shocks, bond pricing, DV01, duration, swap
  rates, swaptions, Nelson-Siegel fitting, PCA on rates, or cross-market curve
  comparison — even if the user doesn't explicitly say "MATLAB" or "fetch data".
  Examples: "what does the US curve look like today", "model a 25bps ECB hike",
  "compare USD SOFR vs EUR swap curve", "price a 10y JGB", "run a rate shock scenario".
---
## STRICT PLOTTING RULE
NEVER use HTML/SVG/widget to plot financial data.
ALWAYS generate plots in MATLAB using this exact pattern:

figure('Visible', 'off');
% ... plot code ...
saveas(gcf, '/Users/yanliang/matlab-mcp/output/plot.png');
fprintf('Plot saved: /Users/yanliang/matlab-mcp/output/plot.png\n');
close(gcf);


# MATLAB MCP — Rates & Yield Curve Modeling Skill

This skill enables Claude to fetch live market data and run real MATLAB models
on the user's local machine via MCP tools.

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `run_matlab` | Execute MATLAB code, returns stdout |
| `get_variable` | Read a workspace variable by name |
| `fetch_market_data` | Fetch live yield/swap/rate data by market |

**Critical rule:** Always use `fprintf()` to print MATLAB results.
Silent assignments (e.g. `x = 42`) produce NO output. Never use `disp()` for
numbers — use `fprintf('label: %.4f\n', value)`.

---

## Step 1 — Always Fetch Live Data First

Before any modeling, call `fetch_market_data` to get current rates.
Then inject those rates directly into MATLAB as the starting point.

```
fetch_market_data(market="US_TREASURY", date="latest")
fetch_market_data(market="SOFR_SWAP",   date="latest")
fetch_market_data(market="EUR_SWAP",    date="latest")
fetch_market_data(market="JGB",         date="latest")
fetch_market_data(market="UK_GILT",     date="latest")
fetch_market_data(market="ECB_RATE",    date="latest")
```

See references/data-sources.md for full source list, FRED series IDs,
fallback logic, and data freshness notes.

---

## Step 2 — Inject Fetched Data into MATLAB

After fetching, always inject data explicitly and confirm:

```matlab
maturities = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30];
yields     = [/* paste fetched values here */];
fprintf('Data as of: %s\n', date_str);
fprintf('2Y: %.4f%%  5Y: %.4f%%  10Y: %.4f%%\n', ...
    interp1(maturities,yields,2), ...
    interp1(maturities,yields,5), ...
    interp1(maturities,yields,10));
```

---

## Core Modeling Patterns

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
% Inputs: face, coupon_rate, maturity, freq, maturities, yields
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

### Cross-Market Comparison (e.g. USD vs EUR)
1. fetch_market_data for both markets
2. Fit Nelson-Siegel to each independently
3. Print side-by-side tenor table with spread column
4. Compute spread at 2Y, 5Y, 10Y, 30Y
5. Interpret: steepness, inversion, cross-over points, macro implications

See references/modeling-patterns.md for: SOFR bootstrap, swaption vol
surface basics, PCA on yield curve, cross-currency basis analysis.

---

## Standard Workflow

1. fetch_market_data → get live rates for required market(s)
2. run_matlab → inject data, print confirmation of key tenors
3. run_matlab → fit model, print parameters + RMSE
4. run_matlab → shock/pricing/spread analysis
5. Interpret results with market context
6. Suggest logical next step to user

---

## Toolbox Requirements

| Task | Required |
|------|----------|
| lsqcurvefit, fmincon | Optimization Toolbox |
| arima, estimate | Econometrics Toolbox |
| fitlm, regress | Statistics & ML Toolbox |
| ode45, fft, interp1 | Built-in, no toolbox needed |

If a toolbox is missing, fall back to manual implementation.
See references/modeling-patterns.md for toolbox-free alternatives.

## Visualization Preference
Always save MATLAB figures as PNG to ~/matlab-mcp/output/ using:
figure('Visible','off');
% ... plot code ...
saveas(gcf, '/Users/yanliang/matlab-mcp/output/plot.png');
close;
Then tell the user the file location to open it.

## Data Notes
US Treasury XML may be empty on weekends/holidays — 
if fetch_market_data fails, fall back to web search for latest yields.