"""
Deterministic compliance comparison script.

Run in E2B sandbox:
    python3 compliance_check.py trades.json preclearances.json [index_ref.json]

Also importable for unit tests — all logic lives in module-level functions.
"""
import json
import sys
from datetime import date

BUILTIN_EXEMPT_TICKERS = {
    "SPY", "IVV", "VTI", "QQQ", "EFA", "AGG", "BND",
    "VEA", "VWO", "IEFA", "IJH", "IJR", "IWM", "GLD",
    "SHY", "TLT", "LQD", "HYG", "ACWI", "VT",
}


def normalize_ticker(value: str) -> str:
    return (value or "").strip().upper()


def parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def is_exempt(trade: dict, index_ref: list) -> bool:
    ticker = normalize_ticker(trade.get("ticker", ""))
    isin = normalize_ticker(trade.get("isin", ""))

    for entry in index_ref:
        ref_ticker = normalize_ticker(entry.get("ticker", ""))
        ref_isin = normalize_ticker(entry.get("isin", ""))
        ticker_match = (ticker and ticker == ref_ticker) or (isin and isin == ref_isin)
        if ticker_match:
            if entry.get("constituents", 0) > 20 and entry.get("max_weight_pct", 100) < 20:
                return True

    return ticker in BUILTIN_EXEMPT_TICKERS


def find_preclearance(trade: dict, preclearances: list) -> dict | None:
    ticker = normalize_ticker(trade.get("ticker", ""))
    isin = normalize_ticker(trade.get("isin", ""))
    direction = (trade.get("direction") or "").strip().lower()

    for pc in preclearances:
        pc_ticker = normalize_ticker(pc.get("ticker", ""))
        pc_isin = normalize_ticker(pc.get("isin", ""))
        pc_direction = (pc.get("direction") or "").strip().lower()

        ticker_match = (ticker and ticker == pc_ticker) or (isin and isin == pc_isin)
        if ticker_match and direction == pc_direction:
            return pc
    return None


def check_discrepancies(trade: dict, pc: dict) -> list[str]:
    reasons = []
    qty = float(trade.get("quantity", 0))
    approved_qty = float(pc.get("approved_quantity", 0))
    trade_date = parse_date(trade.get("trade_date"))
    approval_date = parse_date(pc.get("approval_date"))
    expiry_date = parse_date(pc.get("expiry_date"))

    if qty > approved_qty:
        reasons.append("quantity_exceeded")
    if trade_date < approval_date or trade_date > expiry_date:
        reasons.append("outside_window")
    return reasons


def run(trades: list, preclearances: list, index_ref: list | None = None) -> dict:
    if index_ref is None:
        index_ref = []

    exempt_trades = []
    discrepancies = []
    clean_trades = []

    for trade in trades:
        if is_exempt(trade, index_ref):
            exempt_trades.append({**trade, "exempt_reason": "diversified_index"})
            continue

        pc = find_preclearance(trade, preclearances)

        if pc is None:
            discrepancies.append({
                "trade": trade,
                "preclearance": None,
                "reasons": ["no_approval"],
            })
            continue

        reasons = check_discrepancies(trade, pc)
        if reasons:
            discrepancies.append({"trade": trade, "preclearance": pc, "reasons": reasons})
        else:
            clean_trades.append({"trade": trade, "preclearance": pc})

    return {
        "summary": {
            "total_trades": len(trades),
            "exempt": len(exempt_trades),
            "matched": len(clean_trades),
            "discrepancies": len(discrepancies),
        },
        "discrepancies": discrepancies,
        "clean_trades": clean_trades,
        "exempt_trades": exempt_trades,
    }


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(json.dumps({"error": "Usage: compliance_check.py trades.json preclearances.json [index_ref.json]"}))
        sys.exit(1)

    with open(argv[0]) as f:
        _trades = json.load(f)
    with open(argv[1]) as f:
        _preclearances = json.load(f)
    _index_ref = []
    if len(argv) > 2:
        with open(argv[2]) as f:
            _index_ref = json.load(f)

    print(json.dumps(run(_trades, _preclearances, _index_ref)))
