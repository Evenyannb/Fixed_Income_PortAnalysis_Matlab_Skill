# Fixed Income Morning Assistant
### An AI Skill for Portfolio Managers

A conversational skill that gives a fixed income portfolio manager a
structured morning workflow — fetch live yield curves, monitor positions,
run rate shock scenarios, and price bonds — all through natural language.

The skill defines **what the assistant does and how it thinks**. The
underlying infrastructure (how data is fetched, how models run) is
implementation-specific — this repo includes a Python + MATLAB reference
implementation, but the skill itself can be adapted to any platform or
toolchain.

---

## The Idea

A fixed income PM spends significant time every morning on repetitive
analytical work:

- Checking what moved overnight across markets
- Estimating how curve moves hit their book
- Running quick "what if the central bank does X" scenarios
- Writing up a summary for the team

This skill automates that workflow through conversation. The PM interacts
in plain language — the assistant handles data fetching, curve fitting,
bond pricing, and delivers a structured brief.

**What the PM types:**
> "Morning check"

**What the assistant does:**
Loads the book → fetches live curves for each market → compares to
yesterday → prices positions with proper day count and accrued → aggregates
DV01 → delivers a plain-language morning brief.

No parameters. No code. No friction.

---

## Example Prompts

| Scenario | Prompt |
|----------|--------|
| Full morning workflow | `Morning check` |
| Overnight curve moves | `What moved on JGB since yesterday?` |
| Parallel rate shock | `What happens to my book if the Fed cuts 50bps?` |
| Realistic CB shock | `Apply a 25bps BoJ hike — short end weighted` |
| Relative value | `Is the 10Y UST cheap or rich vs the curve?` |
| Bond pricing with accrued | `Price my JGB 10Y position including accrued` |
| Cross-market comparison | `Compare US Treasury vs JGB right now` |
| Add a position | `Add a short 30Y JGB, ¥500B notional, 2.1% coupon` |
| Remove a position | `Remove the 2Y UST short from my book` |
| Non-curated market | `Fetch the Australian government bond curve` |
| Alternative model | `Fit the JGB curve using Svensson instead` |
| Interpolation only | `Give me a smooth curve through the UST data` |
| Plot | `Plot the JGB curve and save it` |

---

## Skill Design

The skill is defined in three documents:

### `CLAUDE.md` — The Core Skill
The primary instruction file. Defines:
- **The PM's perspective** — what they care about, what they don't
- **Morning check workflow** — the full step-by-step sequence
- **Common requests** — rate shocks, RV, position management
- **Communication rules** — lead with market implications, not methodology
- **Pricing guidance** — when to use approximate vs full day-count pricing
- **Tool usage map** — which tools to call for each PM request

This file is designed for Claude Desktop projects but the logic is
platform-agnostic — it can be adapted as a system prompt for any LLM.

### `references/data-sources.md` — Data Source Registry
A tiered registry of official data sources:

- **Tier 1 (curated):** US Treasury, JGB (MoF Japan), EUR AAA (ECB),
  ECB policy rate — all free, no API key, machine-readable
- **Tier 2 (known leads):** UK Gilts (BoE), Australia (RBA), Canada
  (Bank of Canada Valet API), South Korea (BoK), Switzerland (SNB) —
  starting points with notes on format and reliability
- **Tier 3 (unknown):** Decision tree for finding any other official
  source via web search

The registry is designed to grow — when a new market is successfully
fetched, the working endpoint gets added to Tier 2 for next time.

### `references/modeling-patterns.md` — Analytical Patterns
MATLAB implementations (adaptable to any numerical language) for:
- Nelson-Siegel curve fitting (default)
- Nelson-Siegel-Svensson (6-parameter, handles two-hump curves)
- Cubic spline / PCHIP interpolation
- Rate shock scenarios (parallel and front-end weighted)
- Bond pricing with day count conventions and accrued interest
- SOFR swap curve bootstrap
- PCA on yield curve history
- Carry and roll-down analysis
- Swaption approximation (Black's model, flat vol)

---

## Workflow in Detail

### Morning Check

```
1. manage_positions(list)
   → loads the book: markets, maturities, notionals, sides

2. fetch_market_data(market) × N  +  save_snapshot(data) × N
   → live curves from official sources, persisted to disk

3. diff_snapshots(market, yesterday, today) × N
   → yield changes in bps per tenor, biggest movers flagged

4. run_matlab (curve fitting + bond pricing)
   → NS fit per market, dirty price + DV01 per position

5. Aggregate book DV01 by market and total
   → overnight P&L estimate per position = move_bps × DV01

6. Deliver morning brief
   → plain language: what moved, book impact, positions to watch
```

### Rate Shock

```
1. fetch_market_data → today's curve (or use workspace if already fetched)
2. Apply shock:
   - Parallel: add X bps across all tenors
   - Front-end weighted: taper from X bps at short end toward 0 at long end
3. Reprice affected positions at shocked curve
4. Report: position-level P&L, book total, which positions benefit vs hurt
```

### Curve Fitting — Model Selection

| Situation | Model |
|-----------|-------|
| Default, no model specified | Nelson-Siegel |
| NS RMSE > 10bps or lambda degenerate | Nelson-Siegel-Svensson |
| User wants exact interpolation | Cubic spline or PCHIP |
| User explicitly names a model | Use that model |

### Bond Pricing — Day Count by Market

| Market | Convention | Coupon Freq |
|--------|-----------|-------------|
| US Treasury | Actual/Actual (ICMA) | Semi-annual |
| JGB | Actual/365 | Semi-annual |
| UK Gilt | Actual/Actual (ICMA) | Semi-annual |
| EUR Govvie | Actual/Actual (ICMA) | Annual |
| EUR Corp | 30/360 | Annual |

Morning DV01 aggregation uses approximate pricing (fast).
Full pricing with accrued is used when the PM asks about price levels or P&L.

---

## Data Sources

All data comes from official government and central bank sources.
No paid APIs. No web scraping of news or aggregator sites.

| Market | Source | URL | Tenors |
|--------|--------|-----|--------|
| US Treasury | US Treasury | treasury.gov | 1M–30Y |
| JGB | Ministry of Finance Japan | mof.go.jp | 1Y–40Y |
| EUR AAA yield curve | ECB Data Portal | data-api.ecb.europa.eu | 1Y–30Y |
| ECB policy rate | ECB Data Portal | data-api.ecb.europa.eu | Single rate |

For any other market, the skill finds the official source via web search,
fetches raw data directly, and continues with the same workflow.
See `references/data-sources.md` for known leads on UK, Australia,
Canada, South Korea, Switzerland, and China.

### Important — Government Bonds vs Swap Rates vs LIBOR

This skill fetches **sovereign government bond yields** — not swap rates,
not LIBOR, not SOFR. These are meaningfully different:

| Rate | What it is | Status |
|------|-----------|--------|
| US Treasury yield | US govt borrowing rate — risk-free, sovereign | ✅ What this skill fetches |
| JGB yield | Japanese govt borrowing rate — risk-free, sovereign | ✅ What this skill fetches |
| ECB AAA curve | AAA euro govt bond yields — sovereign | ✅ What this skill fetches |
| SOFR | USD secured overnight interbank rate — replaced LIBOR | ⚠️ Not fetched — no free full curve source |
| €STR | EUR overnight interbank rate — replaced EURIBOR | ⚠️ Not fetched — no free full curve source |
| LIBOR | Was unsecured interbank rate | ❌ Defunct since June 2023 — do not use |

**Practical implication:**

- If the PM runs a **government bond book** (Treasuries, JGBs, Gilts,
  Bunds) — this skill uses the right curves directly.
- If the PM trades **USD/EUR interest rate swaps** — the government bond
  curve is a directional proxy, but understates rates by the swap spread
  (typically 10–30 bps). A SOFR or €STR swap curve is needed for
  precise swap pricing, but has no free machine-readable public source.
- **LIBOR is dead.** Any reference to LIBOR in positions or analysis
  should be flagged as a legacy instrument requiring transition to SOFR/€STR.

See `references/data-sources.md` for details on what each curve is,
how they relate, and options for obtaining swap curve data.

---

## Reference Implementation (Python + MATLAB)

This repo includes a working implementation using:
- **Python 3.11** — MCP server (`matlab_server.py`)
- **MATLAB R2026a** — curve fitting, bond pricing, plots via `matlab.engine`
- **Claude Desktop** — conversation layer with MCP integration

This is one way to implement the skill. The same workflow could be built
with a different modeling engine (R, Julia, numpy/scipy), a different
server language (Node.js, Go), or a different LLM platform.

### Tools Implemented

| Tool | Purpose |
|------|---------|
| `fetch_market_data` | Curated live data (US Treasury, JGB, EUR, ECB) |
| `fetch_url` | Raw fetch from any official URL for non-curated markets |
| `save_snapshot` | Persist curve data as dated JSON |
| `load_snapshot` | Load a saved curve by market + date |
| `list_snapshots` | List available history |
| `diff_snapshots` | Yield changes between two dates in bps |
| `manage_positions` | Read/add/remove bond positions from CSV |
| `run_matlab` | Execute MATLAB code, return stdout |
| `get_variable` | Read from MATLAB workspace |

### Setup (Python + MATLAB on macOS)

**Prerequisites:**
- macOS with MATLAB R2026a and a valid license
- Python 3.11 (MATLAB engine requires 3.11, not 3.13)
- Claude Desktop

**Install:**
```bash
# MATLAB Python engine
sudo python3.11 /Applications/MATLAB_R2026a.app/extern/engines/python/setup.py install

# Dependencies
python3.11 -m pip install mcp requests
```

**Project folder:**
```bash
mkdir -p ~/matlab-mcp/snapshots ~/matlab-mcp/output ~/matlab-mcp/references

# Copy from repo
cp matlab_server.py ~/matlab-mcp/
cp references/* ~/matlab-mcp/references/
cp positions.csv ~/matlab-mcp/   # edit with your actual positions
```

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "matlab": {
      "command": "/opt/homebrew/bin/python3.11",
      "args": ["/Users/YOUR_USERNAME/matlab-mcp/matlab_server.py"]
    }
  }
}
```

**Claude project:**
1. Create a new project in Claude Desktop
2. Paste `CLAUDE.md` contents into the project Instructions
3. Add `references/data-sources.md` and `references/modeling-patterns.md`
   to the project context

**Positions file** (`~/matlab-mcp/positions.csv`):
```csv
bond_id,market,maturity_yr,coupon_pct,face_notional,side,description
UST_10Y_2036,US_TREASURY,10.0,4.25,200000000,long,10Y UST long
JGB_10Y_2036,JGB,10.0,0.8,1000000000,long,10Y JGB benchmark
```

---

## Adapting to Other Platforms

The skill (CLAUDE.md + references/) is platform-agnostic. To adapt:

**Different LLM (GPT-4, Gemini, Codex, etc.):**
Use `CLAUDE.md` as a system prompt. The workflow logic, communication
rules, and data sourcing decision tree are not Claude-specific.

**Different modeling engine (Python/numpy, R, Julia):**
Replace the MATLAB code in `modeling-patterns.md` with equivalent
implementations. The NS formula, bond pricing logic, and shock patterns
are standard — not MATLAB-specific.

**Different server language (Node.js, Go, etc.):**
Implement the same tool interface (`fetch_market_data`, `save_snapshot`,
`manage_positions`, etc.) in your preferred language. The tool names and
schemas in `matlab_server.py` serve as the reference spec.

**No MCP (direct API integration):**
The tools can be implemented as function calls in the OpenAI/Anthropic
API tool-use format. The skill logic in `CLAUDE.md` maps directly to
tool descriptions.

---

## Limitations

- Pricing is indicative — no callable/puttable features, no floating legs,
  no repo/financing cost
- Data is end-of-day — official sources update once per business day
- SOFR full swap curve requires CME Term SOFR API (not free)
- Swaption vol surface requires Bloomberg/Refinitiv (no free public source)
- Single-user — tied to local MATLAB license, not a multi-user system
- Snapshot history starts from first use — no pre-loaded historical data

---

## Repository Structure

```
├── README.md                  ← this file
├── CLAUDE.md                  ← skill instructions (core of the project)
├── matlab_server.py           ← reference MCP server (Python + MATLAB)
├── positions.csv              ← sample positions file
└── references/
    ├── data-sources.md        ← tiered data source registry
    └── modeling-patterns.md   ← analytical patterns and MATLAB code
```

---

## Acknowledgements

Data sources: US Department of the Treasury, Ministry of Finance Japan,
European Central Bank.

Runtime (reference implementation): MathWorks MATLAB, Anthropic Claude,
Model Context Protocol.
