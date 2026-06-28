import pytest
from src.compliance_check import (
    run,
    is_exempt,
    normalize_ticker,
    find_preclearance,
    check_discrepancies,
)

# ---------- Fixtures ----------

AAPL_TRADE = {
    "ticker": "AAPL",
    "isin": "US0378331005",
    "direction": "buy",
    "quantity": 500,
    "trade_date": "2026-06-15",
    "account": "ACC-001",
}

AAPL_PC = {
    "ticker": "AAPL",
    "isin": "US0378331005",
    "direction": "buy",
    "approved_quantity": 1000,
    "approval_date": "2026-06-10",
    "expiry_date": "2026-06-20",
    "employee": "Jane Smith",
}

# ---------- normalize_ticker ----------

def test_normalize_ticker_strips_and_uppercases():
    assert normalize_ticker("  aapl  ") == "AAPL"

def test_normalize_ticker_handles_none():
    assert normalize_ticker(None) == ""

# ---------- is_exempt — builtin list ----------

def test_spy_is_exempt_via_builtin():
    trade = {**AAPL_TRADE, "ticker": "SPY"}
    assert is_exempt(trade, []) is True

def test_aapl_is_not_exempt():
    assert is_exempt(AAPL_TRADE, []) is False

# ---------- is_exempt — custom index_ref ----------

def test_exempt_via_custom_ref_by_ticker():
    ref = [{"ticker": "MYETF", "isin": "", "constituents": 50, "max_weight_pct": 5.0}]
    trade = {**AAPL_TRADE, "ticker": "MYETF"}
    assert is_exempt(trade, ref) is True

def test_not_exempt_if_too_few_constituents():
    ref = [{"ticker": "MYETF", "isin": "", "constituents": 10, "max_weight_pct": 5.0}]
    trade = {**AAPL_TRADE, "ticker": "MYETF"}
    assert is_exempt(trade, ref) is False

def test_not_exempt_if_weight_too_high():
    ref = [{"ticker": "MYETF", "isin": "", "constituents": 50, "max_weight_pct": 25.0}]
    trade = {**AAPL_TRADE, "ticker": "MYETF"}
    assert is_exempt(trade, ref) is False

def test_exempt_via_custom_ref_by_isin():
    ref = [{"ticker": "", "isin": "US9999999999", "constituents": 30, "max_weight_pct": 3.0}]
    trade = {**AAPL_TRADE, "ticker": "", "isin": "US9999999999"}
    assert is_exempt(trade, ref) is True

# ---------- find_preclearance ----------

def test_finds_matching_preclearance():
    assert find_preclearance(AAPL_TRADE, [AAPL_PC]) == AAPL_PC

def test_no_match_wrong_direction():
    sell_pc = {**AAPL_PC, "direction": "sell"}
    assert find_preclearance(AAPL_TRADE, [sell_pc]) is None

def test_no_match_wrong_ticker():
    msft_pc = {**AAPL_PC, "ticker": "MSFT", "isin": "US5949181045"}
    assert find_preclearance(AAPL_TRADE, [msft_pc]) is None

def test_matches_by_isin_when_ticker_absent():
    trade = {**AAPL_TRADE, "ticker": ""}
    assert find_preclearance(trade, [AAPL_PC]) == AAPL_PC

# ---------- check_discrepancies ----------

def test_clean_trade_has_no_reasons():
    assert check_discrepancies(AAPL_TRADE, AAPL_PC) == []

def test_quantity_exceeded():
    trade = {**AAPL_TRADE, "quantity": 1500}
    reasons = check_discrepancies(trade, AAPL_PC)
    assert "quantity_exceeded" in reasons

def test_partial_fill_is_clean():
    trade = {**AAPL_TRADE, "quantity": 100}
    assert check_discrepancies(trade, AAPL_PC) == []

def test_trade_before_approval_window():
    trade = {**AAPL_TRADE, "trade_date": "2026-06-05"}
    reasons = check_discrepancies(trade, AAPL_PC)
    assert "outside_window" in reasons

def test_trade_after_expiry():
    trade = {**AAPL_TRADE, "trade_date": "2026-06-25"}
    reasons = check_discrepancies(trade, AAPL_PC)
    assert "outside_window" in reasons

def test_trade_on_expiry_date_is_clean():
    trade = {**AAPL_TRADE, "trade_date": "2026-06-20"}
    assert check_discrepancies(trade, AAPL_PC) == []

def test_multiple_reasons():
    trade = {**AAPL_TRADE, "quantity": 2000, "trade_date": "2026-06-25"}
    reasons = check_discrepancies(trade, AAPL_PC)
    assert "quantity_exceeded" in reasons
    assert "outside_window" in reasons

# ---------- run — integration ----------

def test_clean_run():
    result = run([AAPL_TRADE], [AAPL_PC])
    assert result["summary"]["total_trades"] == 1
    assert result["summary"]["matched"] == 1
    assert result["summary"]["discrepancies"] == 0
    assert result["summary"]["exempt"] == 0
    assert len(result["clean_trades"]) == 1
    assert len(result["discrepancies"]) == 0

def test_no_approval_discrepancy():
    result = run([AAPL_TRADE], [])
    assert result["summary"]["discrepancies"] == 1
    assert result["discrepancies"][0]["reasons"] == ["no_approval"]

def test_exempt_trade_skipped():
    spy_trade = {**AAPL_TRADE, "ticker": "SPY"}
    result = run([spy_trade], [])
    assert result["summary"]["exempt"] == 1
    assert result["summary"]["discrepancies"] == 0
    assert result["exempt_trades"][0]["exempt_reason"] == "diversified_index"

def test_mixed_results():
    spy_trade = {**AAPL_TRADE, "ticker": "SPY"}
    msft_trade = {
        "ticker": "MSFT", "isin": "US5949181045",
        "direction": "buy", "quantity": 200,
        "trade_date": "2026-06-15", "account": "ACC-001",
    }
    result = run([AAPL_TRADE, spy_trade, msft_trade], [AAPL_PC])
    assert result["summary"]["total_trades"] == 3
    assert result["summary"]["exempt"] == 1
    assert result["summary"]["matched"] == 1
    assert result["summary"]["discrepancies"] == 1

def test_empty_inputs():
    result = run([], [])
    assert result["summary"]["total_trades"] == 0
