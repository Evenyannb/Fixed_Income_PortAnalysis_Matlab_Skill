import asyncio
import io
import sys
import json
import csv
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests
import matlab.engine
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Start MATLAB engine ──────────────────────────────────────────────────────
sys.stderr.write("Starting MATLAB engine...\n"); sys.stderr.flush()
eng = matlab.engine.start_matlab()
sys.stderr.write("MATLAB engine ready!\n"); sys.stderr.flush()

app = Server("matlab-mcp")
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path.home() / "matlab-mcp"
SNAPSHOT_DIR   = BASE_DIR / "snapshots"
OUTPUT_DIR     = BASE_DIR / "output"
POSITIONS_FILE = BASE_DIR / "positions.csv"

for d in [SNAPSHOT_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ── Market data helpers ──────────────────────────────────────────────────────

def fetch_us_treasury():
    """Fetch US Treasury curve with 3-source fallback chain:
    1. Treasury CSV (most stable endpoint)
    2. Treasury XML (original, flaky but sometimes works)
    3. Snapshot fallback (last saved data with staleness warning)
    """
    result = _fetch_treasury_csv()
    if result and 'error' not in result:
        sys.stderr.write(f"Treasury CSV succeeded: {result['date']}\n")
        return result

    sys.stderr.write("Treasury CSV failed, trying XML...\n")
    result = _fetch_treasury_xml()
    if result and 'error' not in result:
        sys.stderr.write(f"Treasury XML succeeded: {result['date']}\n")
        return result

    sys.stderr.write("Treasury XML failed, trying last snapshot...\n")
    result = _fetch_treasury_snapshot_fallback()
    if result and 'error' not in result:
        return result

    return {'error': (
        'All US Treasury sources failed (CSV, XML, snapshot). '
        'Treasury.gov may be temporarily unavailable. '
        'Try again in a few minutes or use a saved snapshot.'
    )}


def _fetch_treasury_csv():
    """Try Treasury CSV endpoint — more stable than XML."""
    year = datetime.now().year
    url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
           f"interest-rates/daily-treasury-rates.csv/{year}/all"
           f"?type=daily_treasury_yield_curve"
           f"&field_tdr_date_value={year}&download=true")
    col_map = {
        '1 Mo': 0.083, '2 Mo': 0.167, '3 Mo': 0.25, '4 Mo': 0.333,
        '6 Mo': 0.5,   '1 Yr': 1,     '2 Yr': 2,    '3 Yr': 3,
        '5 Yr': 5,     '7 Yr': 7,     '10 Yr': 10,  '20 Yr': 20,
        '30 Yr': 30,
    }
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        lines = r.text.splitlines()
        if len(lines) < 2:
            return None
        reader = list(csv.DictReader(lines))
        # Find latest row with actual data
        for row in reversed(reader):
            date_str = row.get('Date', '').strip()
            if not date_str:
                continue
            maturities, yields = [], []
            for col, mat in sorted(col_map.items(), key=lambda x: x[1]):
                val = row.get(col, '').strip()
                if val and val != 'N/A':
                    try:
                        maturities.append(mat)
                        yields.append(float(val))
                    except ValueError:
                        pass
            if len(maturities) >= 6:  # need at least 6 tenors
                # Normalize date format
                try:
                    dt = datetime.strptime(date_str, '%m/%d/%Y')
                    date_str = dt.strftime('%Y-%m-%d')
                except Exception:
                    pass
                return {'market': 'US_TREASURY', 'date': date_str,
                        'maturities': maturities, 'yields': yields,
                        'unit': 'percent',
                        'source': 'US Treasury CSV (treasury.gov)'}
    except Exception as e:
        sys.stderr.write(f"Treasury CSV error: {e}\n")
    return None


def _fetch_treasury_xml():
    """Original XML endpoint — try last 14 days across month boundaries."""
    tenor_map = {
        'BC_1MONTH': 0.083, 'BC_2MONTH': 0.167, 'BC_3MONTH': 0.25,
        'BC_6MONTH': 0.5,   'BC_1YEAR': 1,      'BC_2YEAR': 2,
        'BC_3YEAR': 3,      'BC_5YEAR': 5,      'BC_7YEAR': 7,
        'BC_10YEAR': 10,    'BC_20YEAR': 20,    'BC_30YEAR': 30,
    }
    seen_months = set()
    for days_back in range(1, 14):
        d = datetime.now() - timedelta(days=days_back)
        ym = d.strftime('%Y%m')
        if ym in seen_months:
            continue
        seen_months.add(ym)
        url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
               f"interest-rates/pages/xml?data=daily_treasury_yield_curve"
               f"&field_tdr_date_value={ym}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            ns_m = 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'
            ns_d = 'http://schemas.microsoft.com/ado/2007/08/dataservices'
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            if not entries:
                continue
            props = entries[-1].find(f'.//{{{ns_m}}}properties')
            date_el = props.find(f'{{{ns_d}}}NEW_DATE')
            date_str = (date_el.text[:10] if date_el is not None
                        else d.strftime('%Y-%m-%d'))
            maturities, yields = [], []
            for tag, mat in sorted(tenor_map.items(), key=lambda x: x[1]):
                el = props.find(f'{{{ns_d}}}{tag}')
                if el is not None and el.text:
                    maturities.append(mat)
                    yields.append(float(el.text))
            if len(maturities) >= 6:
                return {'market': 'US_TREASURY', 'date': date_str,
                        'maturities': maturities, 'yields': yields,
                        'unit': 'percent',
                        'source': 'US Treasury XML (treasury.gov)'}
        except Exception as e:
            sys.stderr.write(f"Treasury XML error ({ym}): {e}\n")
    return None


def _fetch_treasury_snapshot_fallback():
    """Last resort: use the most recent saved US_TREASURY snapshot."""
    snapshots = sorted(SNAPSHOT_DIR.glob("US_TREASURY_*.json"))
    if not snapshots:
        return None
    latest = snapshots[-1]
    try:
        with open(latest) as f:
            data = json.load(f)
        data['source'] = (f"CACHED snapshot ({latest.name}) — "
                          f"live fetch failed, using last saved data. "
                          f"Date may be stale.")
        data['stale'] = True
        return data
    except Exception:
        return None


def fetch_jgb():
    url = ("https://www.mof.go.jp/english/jgbs/reference/interest_rate/"
           "historical/jgbcme_all.csv")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        lines = r.text.splitlines()
        header_idx = 0
        for i, line in enumerate(lines):
            if '1Y' in line and '2Y' in line:
                header_idx = i
                break
        reader = list(csv.reader(lines[header_idx:]))
        headers = reader[0]
        tenor_map = {'1Y':1,'2Y':2,'3Y':3,'4Y':4,'5Y':5,'6Y':6,'7Y':7,
                     '8Y':8,'9Y':9,'10Y':10,'15Y':15,'20Y':20,'25Y':25,
                     '30Y':30,'40Y':40}
        for row in reversed(reader[1:]):
            if len(row) < 5 or not row[0].strip():
                continue
            maturities, yields = [], []
            for j, h in enumerate(headers[1:], 1):
                h = h.strip()
                if h in tenor_map and j < len(row) and row[j].strip():
                    try:
                        maturities.append(tenor_map[h])
                        yields.append(float(row[j].strip()))
                    except ValueError:
                        pass
            if maturities:
                return {'market': 'JGB', 'date': row[0].strip(),
                        'maturities': maturities, 'yields': yields,
                        'unit': 'percent', 'source': 'MoF Japan (mof.go.jp)'}
    except Exception as e:
        sys.stderr.write(f"JGB fetch failed: {e}\n")
    return {'error': 'Could not fetch JGB data'}


def fetch_eur_swap():
    tenors = [1, 2, 3, 5, 7, 10, 15, 20, 30]
    maturities, yields, dates = [], [], []
    for t in tenors:
        url = (f"https://data-api.ecb.europa.eu/service/data/"
               f"YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{t}Y"
               f"?format=csvdata&lastNObservations=1")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            reader = list(csv.DictReader(r.text.splitlines()))
            if reader:
                row = reader[-1]
                val = row.get('OBS_VALUE', '').strip()
                date = row.get('TIME_PERIOD', '').strip()
                if val and float(val) > 0:
                    maturities.append(t)
                    yields.append(round(float(val), 6))
                    dates.append(date)
        except Exception as e:
            sys.stderr.write(f"ECB {t}Y fetch failed: {e}\n")
    if maturities:
        return {'market': 'EUR_SWAP', 'date': dates[-1],
                'maturities': maturities, 'yields': yields,
                'unit': 'percent', 'source': 'ECB AAA Yield Curve (ecb.europa.eu)'}
    return {'error': 'Could not fetch EUR yield curve'}


def fetch_ecb_rate():
    url = ("https://data-api.ecb.europa.eu/service/data/"
           "FM/B.U2.EUR.4F.KR.DFR.LEV?format=csvdata&lastNObservations=1")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        reader = list(csv.DictReader(r.text.splitlines()))
        if reader:
            row = reader[-1]
            return {'market': 'ECB_RATE', 'date': row.get('TIME_PERIOD', ''),
                    'deposit_facility_rate': float(row.get('OBS_VALUE', 0)),
                    'unit': 'percent', 'source': 'ECB Data Portal'}
    except Exception as e:
        sys.stderr.write(f"ECB rate fetch failed: {e}\n")
    return {'error': 'Could not fetch ECB rate'}


CURATED_MARKETS = {
    'US_TREASURY': fetch_us_treasury,
    'JGB': fetch_jgb,
    'EUR_SWAP': fetch_eur_swap,
    'ECB_RATE': fetch_ecb_rate,
}

def fetch_market_data_fn(market: str):
    market = market.upper()
    fn = CURATED_MARKETS.get(market)
    if fn:
        return fn()
    return {'error': (f"'{market}' not curated. Curated: {list(CURATED_MARKETS.keys())}. "
                      f"For other markets use fetch_url.")}


def fetch_url_fn(url: str, max_chars: int = 8000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        content_type = r.headers.get('Content-Type', '')
        if 'spreadsheet' in content_type or url.endswith(('.xls', '.xlsx')):
            return {'url': url, 'content_type': content_type,
                    'error': 'Excel file — find the CSV alternative on the same page.'}
        content = r.text
        return {'url': url, 'status': r.status_code, 'content_type': content_type,
                'truncated': len(content) > max_chars,
                'content': content[:max_chars], 'total_length': len(content)}
    except Exception as e:
        return {'url': url, 'error': str(e)}


# ── Snapshot helpers ─────────────────────────────────────────────────────────

def save_snapshot(data: dict) -> str:
    """Save fetched curve data as a dated JSON snapshot. Returns filepath."""
    market = data.get('market', 'UNKNOWN')
    date   = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    fname  = SNAPSHOT_DIR / f"{market}_{date}.json"
    with open(fname, 'w') as f:
        json.dump(data, f, indent=2)
    return str(fname)


def load_snapshot(market: str, date: str) -> dict:
    """Load a previously saved snapshot by market and date."""
    fname = SNAPSHOT_DIR / f"{market.upper()}_{date}.json"
    if not fname.exists():
        return {'error': f"No snapshot found: {fname.name}. "
                         f"Available: {list_snapshots_fn(market)}"}
    with open(fname) as f:
        return json.load(f)


def list_snapshots_fn(market: str = None) -> list:
    """List available snapshot files, optionally filtered by market."""
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    if market:
        files = [f for f in files if f.name.startswith(market.upper())]
    return [f.name for f in files]


def diff_snapshots(market: str, date1: str, date2: str) -> dict:
    """Compute yield changes between two snapshots at matching tenors."""
    s1 = load_snapshot(market, date1)
    s2 = load_snapshot(market, date2)
    if 'error' in s1:
        return s1
    if 'error' in s2:
        return s2
    m1 = {m: y for m, y in zip(s1['maturities'], s1['yields'])}
    m2 = {m: y for m, y in zip(s2['maturities'], s2['yields'])}
    common = sorted(set(m1) & set(m2))
    changes = []
    for m in common:
        chg_bps = (m2[m] - m1[m]) * 100
        changes.append({'maturity': m, 'from': m1[m], 'to': m2[m],
                         'change_bps': round(chg_bps, 2)})
    return {'market': market, 'from_date': date1, 'to_date': date2,
            'changes': changes,
            'summary': {
                'max_move': max(changes, key=lambda x: abs(x['change_bps'])),
                'parallel_shift_approx': round(
                    sum(c['change_bps'] for c in changes) / len(changes), 2)
            }}


# ── Positions helpers ────────────────────────────────────────────────────────

POSITIONS_HEADER = ['bond_id','market','maturity_yr','coupon_pct',
                    'face_notional','side','description']

def load_positions() -> list:
    """Load positions from CSV. Returns list of dicts."""
    if not POSITIONS_FILE.exists():
        return []
    with open(POSITIONS_FILE) as f:
        return list(csv.DictReader(f))


def save_positions(positions: list) -> str:
    """Save positions list back to CSV."""
    with open(POSITIONS_FILE, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=POSITIONS_HEADER)
        w.writeheader()
        w.writerows(positions)
    return str(POSITIONS_FILE)


def add_position(bond_id, market, maturity_yr, coupon_pct,
                 face_notional, side, description='') -> dict:
    """Add or update a position in the positions file."""
    positions = load_positions()
    # Remove existing entry with same bond_id
    positions = [p for p in positions if p['bond_id'] != bond_id]
    positions.append({
        'bond_id': bond_id,
        'market': market.upper(),
        'maturity_yr': float(maturity_yr),
        'coupon_pct': float(coupon_pct),
        'face_notional': float(face_notional),
        'side': side.lower(),
        'description': description
    })
    save_positions(positions)
    return {'status': 'saved', 'bond_id': bond_id,
            'file': str(POSITIONS_FILE), 'total_positions': len(positions)}


def remove_position(bond_id: str) -> dict:
    """Remove a position by bond_id."""
    positions = load_positions()
    before = len(positions)
    positions = [p for p in positions if p['bond_id'] != bond_id]
    save_positions(positions)
    removed = before - len(positions)
    return {'status': 'removed' if removed else 'not_found',
            'bond_id': bond_id, 'remaining': len(positions)}


# ── MCP Tool definitions ─────────────────────────────────────────────────────

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="run_matlab",
            description=(
                "Execute MATLAB code on the local engine and return output. "
                "CRITICAL: Always use fprintf() to print results — silent assignments "
                "produce NO output. Workspace persists across calls in same conversation. "
                "For plots: figure('Visible','off'), saveas(gcf, path), close(gcf). "
                "Plot path: /Users/yanliang/matlab-mcp/output/<name>.png"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"}
                },
                "required": ["code"]
            }
        ),
        types.Tool(
            name="get_variable",
            description="Read a named variable from the MATLAB workspace.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"]
            }
        ),
        types.Tool(
            name="fetch_market_data",
            description=(
                "Fetch live yield/rate data for curated markets: "
                "US_TREASURY, JGB, EUR_SWAP, ECB_RATE. "
                "After fetching, ALWAYS call save_snapshot to persist the data. "
                "For non-curated markets, use fetch_url instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "enum": ["US_TREASURY", "JGB", "EUR_SWAP", "ECB_RATE"]
                    }
                },
                "required": ["market"]
            }
        ),
        types.Tool(
            name="fetch_url",
            description=(
                "Fetch raw CSV/XML/JSON from any URL. Use for non-curated markets "
                "(Australia, UK, Canada etc.) after finding the official source via web search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer"}
                },
                "required": ["url"]
            }
        ),
        types.Tool(
            name="save_snapshot",
            description=(
                "Save a fetched curve dataset as a dated JSON snapshot. "
                "Always call this after fetch_market_data or fetch_url so "
                "historical comparisons are possible. "
                "Pass the full data dict returned by the fetch tool."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "The full data dict from fetch_market_data"
                    }
                },
                "required": ["data"]
            }
        ),
        types.Tool(
            name="load_snapshot",
            description="Load a previously saved curve snapshot by market and date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string",
                               "description": "e.g. US_TREASURY, JGB, EUR_SWAP"},
                    "date": {"type": "string",
                             "description": "YYYY-MM-DD format"}
                },
                "required": ["market", "date"]
            }
        ),
        types.Tool(
            name="list_snapshots",
            description="List available saved snapshots, optionally filtered by market.",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string",
                               "description": "Optional filter, e.g. JGB"}
                }
            }
        ),
        types.Tool(
            name="diff_snapshots",
            description=(
                "Compare two curve snapshots and show yield changes in bps at each tenor. "
                "Use for 'what moved since last week/yesterday' questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string"},
                    "date1": {"type": "string", "description": "Earlier date YYYY-MM-DD"},
                    "date2": {"type": "string", "description": "Later date YYYY-MM-DD"}
                },
                "required": ["market", "date1", "date2"]
            }
        ),
        types.Tool(
            name="manage_positions",
            description=(
                "Read, add, update or remove bond positions in the portfolio. "
                "action='list' → returns all positions. "
                "action='add' → add/update a position (requires bond_id, market, "
                "maturity_yr, coupon_pct, face_notional, side). "
                "action='remove' → remove by bond_id. "
                "Positions are saved to ~/matlab-mcp/positions.csv."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "enum": ["list", "add", "remove"]},
                    "bond_id": {"type": "string"},
                    "market": {"type": "string"},
                    "maturity_yr": {"type": "number",
                                    "description": "Years to maturity from today"},
                    "coupon_pct": {"type": "number",
                                   "description": "Annual coupon rate in percent"},
                    "face_notional": {"type": "number",
                                      "description": "Face value in local currency"},
                    "side": {"type": "string", "enum": ["long", "short"]},
                    "description": {"type": "string"}
                },
                "required": ["action"]
            }
        ),
    ]


# ── MCP Tool handler ─────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict):

    if name == "run_matlab":
        try:
            out = io.StringIO()
            err = io.StringIO()
            eng.eval(arguments["code"], nargout=0, stdout=out, stderr=err)
            output = out.getvalue() or "Code executed successfully (no output)"
            if err.getvalue():
                output += f"\n[warnings]: {err.getvalue()}"
            return [types.TextContent(type="text", text=output)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"MATLAB error: {str(e)}")]

    elif name == "get_variable":
        try:
            val = eng.workspace[arguments["name"]]
            return [types.TextContent(type="text", text=str(val))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "fetch_market_data":
        try:
            data = fetch_market_data_fn(arguments.get("market", "US_TREASURY"))
            return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Fetch error: {str(e)}")]

    elif name == "fetch_url":
        try:
            data = fetch_url_fn(arguments["url"], arguments.get("max_chars", 8000))
            return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Fetch error: {str(e)}")]

    elif name == "save_snapshot":
        try:
            path = save_snapshot(arguments["data"])
            return [types.TextContent(type="text",
                                      text=json.dumps({'saved': path}, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Snapshot error: {str(e)}")]

    elif name == "load_snapshot":
        try:
            data = load_snapshot(arguments["market"], arguments["date"])
            return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Load error: {str(e)}")]

    elif name == "list_snapshots":
        try:
            files = list_snapshots_fn(arguments.get("market"))
            return [types.TextContent(type="text",
                                      text=json.dumps({'snapshots': files}, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"List error: {str(e)}")]

    elif name == "diff_snapshots":
        try:
            result = diff_snapshots(arguments["market"],
                                    arguments["date1"], arguments["date2"])
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Diff error: {str(e)}")]

    elif name == "manage_positions":
        try:
            action = arguments.get("action", "list")
            if action == "list":
                positions = load_positions()
                return [types.TextContent(type="text",
                                          text=json.dumps({'positions': positions,
                                                           'count': len(positions)},
                                                          indent=2))]
            elif action == "add":
                result = add_position(
                    bond_id       = arguments["bond_id"],
                    market        = arguments["market"],
                    maturity_yr   = arguments["maturity_yr"],
                    coupon_pct    = arguments["coupon_pct"],
                    face_notional = arguments["face_notional"],
                    side          = arguments["side"],
                    description   = arguments.get("description", "")
                )
                return [types.TextContent(type="text",
                                          text=json.dumps(result, indent=2))]
            elif action == "remove":
                result = remove_position(arguments["bond_id"])
                return [types.TextContent(type="text",
                                          text=json.dumps(result, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text",
                                      text=f"Positions error: {str(e)}")]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())