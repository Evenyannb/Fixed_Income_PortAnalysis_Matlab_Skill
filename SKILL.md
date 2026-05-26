---
name: matlab-mcp
description: >
  Use this skill whenever the user wants to run MATLAB code, build financial models,
  analyze yield curves, forecast interest rates, run Simulink simulations, or do any
  quantitative modeling through the MATLAB MCP server. Trigger this skill for any
  request involving MATLAB execution, financial time series, bond pricing, rate curve
  modeling, signal processing, control systems, or numerical computation — even if the
  user doesn't explicitly say "MATLAB". Examples: "forecast the yield curve", "model
  rate sensitivity", "run a simulation", "calculate eigenvalues", "fit a Nelson-Siegel
  curve", "price a bond", "analyze my time series data".
---

# MATLAB MCP Skill

This skill guides Claude on how to effectively use the MATLAB MCP server to run
real MATLAB code on the user's local machine, interpret results, and build
financial or engineering models iteratively.

---

## How the MCP Server Works

The user has a running MCP server (`matlab_server.py`) that exposes two tools:

| Tool | What it does |
|------|-------------|
| `run_matlab` | Executes any MATLAB code string and returns stdout output |
| `get_variable` | Reads a named variable from the MATLAB workspace |

**Key facts:**
- MATLAB engine stays alive between calls — workspace variables persist across tool calls in the same conversation
- stdout is captured and returned as text
- Errors are caught and returned as readable messages
- No GUI is shown — everything is headless

---

## Workflow: How to Approach a Modeling Request

### Step 1 — Understand the goal
Before writing any MATLAB code, clarify:
- What is the input data? (user-provided, synthetic, or fetched?)
- What is the expected output? (numbers, a plot, a forecast, a table?)
- What model or method should be used?

### Step 2 — Build incrementally
Never write one giant MATLAB script. Instead:
1. Set up data / parameters first
2. Run a small verification step (e.g. `disp(size(data))`)
3. Build the core model
4. Extract and interpret results

### Step 3 — Interpret results for the user
Don't just return raw MATLAB output. Explain:
- What the numbers mean
- Whether results look reasonable
- What to try next
- Has to put visualization, example: graphs and tables

---

## Financial Modeling Patterns

### Yield Curve — Nelson-Siegel Model
Use when: user asks to fit, forecast, or shift a yield curve.

```matlab
% Maturities in years
maturities = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30];

% Example Japanese JGB yields (in %)
yields = [-0.10, -0.09, -0.08, 0.02, 0.05, 0.20, 0.40, 0.65, 1.20, 1.50];

% Nelson-Siegel factors: [beta0, beta1, beta2, lambda]
% beta0 = long-run level, beta1 = slope, beta2 = curvature
ns_curve = @(b, m) b(1) + b(2)*(1-exp(-m/b(4)))./(m/b(4)) + ...
           b(3)*((1-exp(-m/b(4)))./(m/b(4)) - exp(-m/b(4)));

% Fit the curve
b0 = [1.5, -1.5, 0.5, 2.0];
opts = optimset('Display','off');
b_fit = lsqcurvefit(ns_curve, b0, maturities, yields, [], [], opts);

% Display fitted parameters
fprintf('Beta0 (level): %.4f\n', b_fit(1));
fprintf('Beta1 (slope): %.4f\n', b_fit(2));
fprintf('Beta2 (curvature): %.4f\n', b_fit(3));
fprintf('Lambda: %.4f\n', b_fit(4));
```

### Rate Shock / Sensitivity Analysis
Use when: user asks "what happens if rates rise by X bps".

```matlab
% Apply parallel shift to fitted curve
shock_bps = 25; % e.g. 25 basis points
shock = shock_bps / 100;

m_fine = linspace(0.25, 30, 200);
base_curve = ns_curve(b_fit, m_fine);
shocked_curve = base_curve + shock;

% Show key tenors
tenors = [1, 2, 5, 10, 30];
for i = 1:length(tenors)
    base_y = ns_curve(b_fit, tenors(i));
    fprintf('%2dy: Base=%.4f%%, Shocked=%.4f%%\n', ...
        tenors(i), base_y, base_y+shock);
end
```

### Bond Pricing
Use when: user asks to price a bond or calculate duration/DV01.

```matlab
% Price a bond given yield curve
face = 100;
coupon_rate = 0.006; % 0.6% coupon
freq = 2;            % semi-annual
maturity = 10;       % years

periods = maturity * freq;
coupon = face * coupon_rate / freq;
cash_flows = [repmat(coupon, 1, periods-1), coupon + face];
times = (1:periods) / freq;

% Get yields at each cash flow date (interpolated from curve)
yields_interp = interp1(maturities, yields, times, 'linear', 'extrap') / 100;

% Discount cash flows
discount_factors = exp(-yields_interp .* times);
price = sum(cash_flows .* discount_factors);
fprintf('Bond Price: %.4f\n', price);

% Duration
duration = sum(times .* cash_flows .* discount_factors) / price;
fprintf('Modified Duration: %.4f years\n', duration);

% DV01 (dollar value of 1bp)
dv01 = price * duration * 0.0001;
fprintf('DV01: %.4f\n', dv01);
```

---

## Output Handling Tips

### Capturing output correctly
Always use `fprintf` or `disp` to print results — MATLAB's automatic variable echo
does NOT get captured by the engine. Bad: `x = 42`. Good: `fprintf('x = %d\n', x)`.

### Multi-step computation
Use `get_variable` to retrieve arrays from the workspace for further processing:
```
Step 1: run_matlab → compute and store result in workspace variable
Step 2: get_variable → pull the variable to inspect or pass to next step
```

### Error recovery
If MATLAB returns an error, read it carefully — common issues:
- Missing toolbox (e.g. Optimization Toolbox for `lsqcurvefit`)
- Wrong matrix dimensions
- Undefined variable (workspace was reset)

---

## Common Toolbox Requirements

| Task | Required Toolbox |
|------|-----------------|
| `lsqcurvefit`, `fmincon` | Optimization Toolbox |
| `arima`, `estimate` | Econometrics Toolbox |
| Simulink models | Simulink |
| `ode45`, `ode23` | Built-in (no toolbox needed) |
| `fft`, `filter` | Built-in (no toolbox needed) |
| `fitlm`, `regress` | Statistics and ML Toolbox |

If a toolbox is missing, suggest an alternative pure-MATLAB implementation.

---

## Example: Full Yield Curve Forecast Workflow

When user asks: *"Forecast Japanese yield curve for a 25bps rate hike"*

1. **run_matlab** → set up maturities and current JGB yields
2. **run_matlab** → fit Nelson-Siegel model, print parameters
3. **run_matlab** → apply 25bps parallel shift, print tenor-by-tenor comparison
4. **run_matlab** → price a benchmark 10y JGB before and after shock
5. **run_matlab** → calculate DV01 and duration impact
6. Interpret: explain what the rate move means for the curve shape and bond prices

---

## Tips for Good Results

- Always `fprintf` your outputs — silent assignments won't show up
- Keep workspace clean between unrelated tasks: `run_matlab("clear all")`
- For iterative models, store intermediate results as workspace variables
- If user provides CSV data, ask for the file path and use `readtable()` to load it
- For large result sets, summarize key statistics rather than dumping all values
