# Modeling Patterns Reference

## 0. Curve Fitting Model Selection

Nelson-Siegel (NS) is the default — but it's a choice, not the only option.
Pick based on the user's request and how well NS actually fits.

**Use NS (default) when:**
- User doesn't specify a model
- Goal is level/slope/curvature decomposition, scenario shocks, or
  cross-market comparison (consistent factors across curves)
- 4 parameters are enough to describe the curve well (RMSE reasonable,
  lambda in a sane range, e.g. 0.5–15 yrs)

**Switch to Nelson-Siegel-Svensson (NSS) when:**
- User explicitly asks for "Svensson" or "NSS"
- NS RMSE is poor (e.g. >10 bps) or NS lambda is degenerate (very large,
  e.g. >40 yrs, or hugging a bound) — NSS adds a second hump and usually
  fixes this
- Curve has two distinct humps (common in some EM curves or stressed markets)

**Switch to spline / pchip interpolation when:**
- User asks for "smooth curve through the data", "interpolate", or just
  wants a visual fit with no parametric structure
- Goal is interpolation for pricing at arbitrary tenors, not factor
  decomposition or scenario analysis
- Very few data points where a 4-6 parameter parametric model would
  overfit or behave erratically

**General approach:** fit NS first (it's cheap). If RMSE is large or
lambda looks degenerate, mention this to the user and offer to try NSS or
a spline instead — don't silently force a bad NS fit, and don't assume
NSS/spline is needed if NS already fits well.

### Nelson-Siegel-Svensson (NSS)

Adds a second curvature term with its own decay parameter — fixes the
"single distant hump" degeneracy that plain NS sometimes hits.

```matlab
nss_model = @(b, m) b(1) ...
    + b(2) .* (1 - exp(-m/b(5))) ./ (m/b(5)) ...
    + b(3) .* ((1 - exp(-m/b(5))) ./ (m/b(5)) - exp(-m/b(5))) ...
    + b(4) .* ((1 - exp(-m/b(6))) ./ (m/b(6)) - exp(-m/b(6)));

% b = [beta0, beta1, beta2, beta3, lambda1, lambda2]
b0   = [2.0, -1.5, 0.5, 0.5, 2.0, 5.0];
opts = optimset('Display', 'off');
b_fit = lsqcurvefit(nss_model, b0, maturities, yields, ...
    [-10,-10,-10,-10, 0.1, 0.1], [10,10,10,10, 30, 30], opts);

fprintf('Beta0: %.4f  Beta1: %.4f  Beta2: %.4f  Beta3: %.4f\n', ...
    b_fit(1), b_fit(2), b_fit(3), b_fit(4));
fprintf('Lambda1: %.4f yrs  Lambda2: %.4f yrs\n', b_fit(5), b_fit(6));
rmse = sqrt(mean((nss_model(b_fit, maturities) - yields).^2));
fprintf('NSS RMSE: %.2f bps\n', rmse * 100);
```

### Cubic Spline (exact interpolation)

Passes exactly through every data point — good for visualization and
pricing at intermediate tenors, but can oscillate between widely-spaced
points and should NOT be used for extrapolation beyond the data range.

```matlab
t_fine   = linspace(min(maturities), max(maturities), 200);
y_spline = interp1(maturities, yields, t_fine, 'spline');
fprintf('Spline: exact fit through %d points\n', length(maturities));
```

### PCHIP (shape-preserving, no overshoot)

Like spline but avoids the oscillation/overshoot spline can produce —
better default for "just give me a smooth curve" when oscillation would
look wrong (e.g. a few widely-spaced tenors).

```matlab
y_pchip = interp1(maturities, yields, t_fine, 'pchip');
```

---

## 1. SOFR Swap Curve Bootstrap (no toolbox)

Bootstrap a zero curve from deposit rates (short end) + swap rates (long end):

```matlab
% Input: swap_tenors (years), swap_rates (%), deposit up to 1Y
swap_tenors = [1, 2, 3, 5, 7, 10, 30];
swap_rates  = [/* fetched SOFR swap rates */] / 100;

% Bootstrap zero rates sequentially
zero_rates = zeros(size(swap_tenors));

% Short end: deposit rates are approximately zero rates
zero_rates(1) = swap_rates(1);

% Long end: bootstrap from par swap rates
for i = 2:length(swap_tenors)
    t   = swap_tenors(i);
    r_s = swap_rates(i);
    % Sum of discounted coupons for prior periods
    pv_coupons = 0;
    for j = 1:i-1
        dt = swap_tenors(j);
        pv_coupons = pv_coupons + r_s * exp(-zero_rates(j) * dt);
    end
    % Solve for zero rate at this tenor
    zero_rates(i) = -log((1 - pv_coupons) / (1 + r_s * t)) / t;
    fprintf('%2dy zero: %.4f%%\n', t, zero_rates(i)*100);
end
```

---

## 2. PCA on Yield Curve (level / slope / curvature)

Use PCA to decompose historical curve moves into 3 factors:

```matlab
% yields_hist: T x N matrix (T dates, N tenors)
% Requires Statistics & ML Toolbox — or use manual SVD below

% Manual SVD approach (no toolbox needed)
Y = yields_hist - mean(yields_hist, 1);  % demean
[U, S, V] = svd(Y, 'econ');

% First 3 PCs explain ~99% of variance
pct_var = diag(S).^2 / sum(diag(S).^2) * 100;
fprintf('PC1 (level):     %.1f%%\n', pct_var(1));
fprintf('PC2 (slope):     %.1f%%\n', pct_var(2));
fprintf('PC3 (curvature): %.1f%%\n', pct_var(3));

% Loadings (factor sensitivities per tenor)
loadings = V(:, 1:3);
fprintf('\nTenor   PC1     PC2     PC3\n');
for i = 1:length(maturities)
    fprintf('%5.1fy  %6.3f  %6.3f  %6.3f\n', ...
        maturities(i), loadings(i,1), loadings(i,2), loadings(i,3));
end
```

---

## 3. Cross-Market Comparison (USD vs EUR vs JGB)

```matlab
% After fetching and fitting Nelson-Siegel for each market:
% b_usd, b_eur, b_jgb already fitted

tenors_cmp = [1, 2, 5, 10, 30];

fprintf('\n%-6s  %-8s  %-8s  %-8s  %-10s  %-10s\n', ...
    'Tenor','USD(%)','EUR(%)','JGB(%)','USD-EUR','USD-JGB');
fprintf('%s\n', repmat('-',1,60));

for i = 1:length(tenors_cmp)
    t   = tenors_cmp(i);
    usd = ns_model(b_usd, t);
    eur = ns_model(b_eur, t);
    jgb = ns_model(b_jgb, t);
    fprintf('%4dy   %6.3f    %6.3f    %6.3f    %+6.0fbps  %+6.0fbps\n', ...
        t, usd, eur, jgb, (usd-eur)*100, (usd-jgb)*100);
end
```

---

## 4. Rate Hike/Cut Scenario — Central Bank Impact

Model what a central bank decision does to the curve shape:

```matlab
% ECB cuts 25bps — short end anchored, long end moves less
function shifted = cb_shock(b_fit, shock_bps, ns_model, tenors)
    % Non-parallel: front-end moves more than back-end
    % Simple approximation: exponential taper
    taper = exp(-tenors / 5);  % decays over 5yr horizon
    shift = (shock_bps / 100) * taper;
    base  = ns_model(b_fit, tenors);
    shifted = base + shift;
end

tenors_fine = linspace(0.25, 30, 100);
base_curve    = ns_model(b_fit, tenors_fine);
shocked_curve = cb_shock(b_fit, -25, ns_model, tenors_fine);

% Print impact at key tenors
key_t = [1, 2, 5, 10, 30];
fprintf('\nTenor  Base    Shocked  Change\n');
for t = key_t
    b = ns_model(b_fit, t);
    s = cb_shock(b_fit, -25, ns_model, t);
    fprintf('%4dy   %.3f%%  %.3f%%   %+.0fbps\n', t, b, s, (s-b)*100);
end
```

---

## 5. Swaption Basics (no vol surface — analytical approximation)

Without a vol surface (which needs Bloomberg), approximate swaption value
using Black's model with a flat vol assumption:

```matlab
% Black's model for a payer swaption
% Inputs: F (forward swap rate), K (strike), T (option expiry),
%         sigma (vol estimate), tenor (swap tenor), freq, discount_factors

function price = black_swaption(F, K, T, sigma, tenor, freq, zero_rates, maturities)
    d1 = (log(F/K) + 0.5*sigma^2*T) / (sigma*sqrt(T));
    d2 = d1 - sigma*sqrt(T);
    
    % Annuity factor (PV of 1bp per period)
    periods = tenor * freq;
    times   = (1:periods) / freq;
    z_interp = interp1(maturities, zero_rates, times, 'linear','extrap');
    df      = exp(-z_interp .* times);
    annuity = sum(df) / freq;
    
    % Payer swaption = Annuity * (F*N(d1) - K*N(d2))
    N = @(x) 0.5*erfc(-x/sqrt(2));
    price = annuity * (F*N(d1) - K*N(d2)) * 100;  % per 100 notional
    
    fprintf('Swaption: F=%.4f K=%.4f T=%.1fy sigma=%.1f%%\n', F,K,T,sigma*100);
    fprintf('Price: %.4f bp-notional\n', price*100);
end
```

Note: For real swaption trading, you need a proper vol surface from Bloomberg.
This is an approximation useful for sensitivity analysis only.

---

## 6. Toolbox-Free Alternatives

### lsqcurvefit replacement (gradient descent)
```matlab
% If Optimization Toolbox missing, use fminsearch (built-in)
obj = @(b) sum((ns_model(b, maturities) - yields).^2);
b_fit = fminsearch(obj, [2.0, -1.5, 0.5, 2.0]);
```

### fitlm replacement (manual OLS)
```matlab
% OLS: beta = (X'X)^-1 X'y
X    = [ones(n,1), x_vars];
beta = (X'*X) \ (X'*y);
yhat = X * beta;
sse  = sum((y - yhat).^2);
fprintf('R2: %.4f\n', 1 - sse/sum((y-mean(y)).^2));
```

---

## 7. Carry & Roll-Down Analysis

```matlab
% How much yield a bond earns if curve stays unchanged (carry + roll)
horizon = 0.25;  % 3-month horizon
mat_now  = 10;
mat_then = mat_now - horizon;

yield_now  = interp1(maturities, yields, mat_now);
yield_then = interp1(maturities, yields, mat_then);

carry     = yield_now * horizon;            % coupon income
roll_down = (yield_now - yield_then) * mat_then;  % price change from rolling
total_return_bps = (carry + roll_down) * 100;

fprintf('Carry:     %+.2f bps\n', carry*100);
fprintf('Roll-down: %+.2f bps\n', roll_down*100);
fprintf('Total:     %+.2f bps (annualized: %+.2f bps)\n', ...
    total_return_bps, total_return_bps/horizon);
```