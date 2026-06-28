# Compliance Broker Statement Checker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two agent tools (`register_compliance_file`, `run_compliance_check`) to the Chainlit AI agent so a compliance officer can upload broker statements and a pre-clearance Excel, and receive a discrepancy report in chat plus a downloadable Excel file.

**Architecture:** A `register_compliance_file` tool parses uploaded files (Excel/PDF in E2B sandbox, images via Claude vision API) into a normalized JSON format and stores them in the E2B sandbox under a session registry. A `run_compliance_check` tool uploads and runs a deterministic Python comparison script (`src/compliance_check.py`) in the sandbox, then downloads the result and generates a three-sheet Excel report attached as a Chainlit file element.

**Tech Stack:** Python, Chainlit, OpenAI Agents SDK (`openai-agents[e2b]`), e2b sandbox, pdfplumber (PDF), pandas (Excel), openpyxl (report), Anthropic API / `claude-sonnet-4-6` (image OCR)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/compliance_check.py` | Deterministic comparison script — runs in E2B sandbox, also importable for tests |
| Create | `src/tools/compliance.py` | `register_compliance_file` + `run_compliance_check` agent tools |
| Create | `tests/__init__.py` | Makes tests a package |
| Create | `tests/test_compliance_check.py` | Unit tests for comparison logic (no E2B needed) |
| Modify | `src/tools/__init__.py` | Export compliance tools |
| Modify | `src/agent.py` | Register compliance tools + update system prompt |
| Modify | `app.py` | Store uploaded file paths in session; pass filenames to agent |
| Modify | `requirements.txt` | Add `pdfplumber`, `anthropic`, `pytest` |

---

## Task 1: Add dependencies and test scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add packages to requirements.txt**

Replace the contents of `requirements.txt` with:

```
chainlit>=2.0.0
openai-agents[e2b]>=0.17.0
httpx>=0.27.0
python-dotenv>=1.0.0
pdfplumber>=0.11.0
anthropic>=0.40.0
openpyxl>=3.1.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

- [ ] **Step 2: Create tests package**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 3: Install new dependencies**

```bash
.venv/Scripts/pip install pdfplumber anthropic openpyxl pytest pytest-asyncio
```

Expected: packages install without error. `pdfplumber` and `anthropic` appear in `pip list`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt tests/__init__.py
git commit -m "chore: add pdfplumber, anthropic, pytest dependencies"
```

---

## Task 2: Write the deterministic comparison script

**Files:**
- Create: `src/compliance_check.py`

- [ ] **Step 1: Write the script**

Create `src/compliance_check.py`:

```python
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
```

- [ ] **Step 2: Verify it runs locally**

```bash
python -c "from src.compliance_check import run; print(run([], []))"
```

Expected output:
```
{'summary': {'total_trades': 0, 'exempt': 0, 'matched': 0, 'discrepancies': 0}, 'discrepancies': [], 'clean_trades': [], 'exempt_trades': []}
```

- [ ] **Step 3: Commit**

```bash
git add src/compliance_check.py
git commit -m "feat: add deterministic compliance comparison script"
```

---

## Task 3: Unit-test the comparison script

**Files:**
- Create: `tests/test_compliance_check.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_compliance_check.py`:

```python
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
    assert result["summary"]["discrepancies"] == 1  # MSFT has no approval

def test_empty_inputs():
    result = run([], [])
    assert result["summary"]["total_trades"] == 0
```

- [ ] **Step 2: Run tests and verify they all pass**

```bash
python -m pytest tests/test_compliance_check.py -v
```

Expected: all tests pass. If any fail, fix `src/compliance_check.py` before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/test_compliance_check.py
git commit -m "test: unit tests for compliance comparison script"
```

---

## Task 4: Write the compliance tool functions

**Files:**
- Create: `src/tools/compliance.py`

This file contains both tools. Excel and PDF parsing scripts run as inline Python strings executed in the E2B sandbox. Image parsing calls the Anthropic API from tool code. The session object from `get_sandbox_session()` is the e2b `AsyncSandbox` (or thin wrapper); adjust `_sbx()` if needed.

- [ ] **Step 1: Write `src/tools/compliance.py`**

```python
import base64
import json
import os
from pathlib import Path

import anthropic
import chainlit as cl

from src.sandbox import get_sandbox_session

_COMPLIANCE_DIR = "/compliance"
_REGISTRY_PATH = f"{_COMPLIANCE_DIR}/registry.json"
_SCRIPT_PATH = f"{_COMPLIANCE_DIR}/compliance_check.py"
_REPORT_PATH = f"{_COMPLIANCE_DIR}/compliance_report.xlsx"

_EXCEL_EXTENSIONS = {".xlsx", ".xls"}
_PDF_EXTENSIONS = {".pdf"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

_EXCEL_PARSE_TEMPLATE = """
import pandas as pd, json, sys
df = pd.read_excel("{path}", engine="openpyxl")
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

COL_MAP_TRADES = {{
    "ticker": ["ticker", "symbol", "stock", "security"],
    "isin": ["isin"],
    "direction": ["direction", "side", "type", "action", "buy_sell"],
    "quantity": ["quantity", "qty", "shares", "units", "volume"],
    "trade_date": ["trade_date", "date", "transaction_date", "settlement_date"],
    "account": ["account", "account_number", "acct"],
}}

COL_MAP_PC = {{
    "ticker": ["ticker", "symbol", "security"],
    "isin": ["isin"],
    "direction": ["direction", "side", "type"],
    "approved_quantity": ["approved_quantity", "approved_qty", "qty_approved", "quantity", "qty"],
    "approval_date": ["approval_date", "approved_date", "date_approved", "request_date"],
    "expiry_date": ["expiry_date", "expiry", "expires", "valid_until", "valid_to"],
    "employee": ["employee", "employee_name", "name", "person"],
}}

schema = COL_MAP_{role}

def find_col(df, aliases):
    for a in aliases:
        if a in df.columns:
            return a
    return None

records = []
for _, row in df.iterrows():
    rec = {{}}
    for field, aliases in schema.items():
        col = find_col(df, aliases)
        val = str(row[col]).strip() if col and col in df.columns else ""
        if val.lower() in ("nan", "none", ""):
            val = ""
        rec[field] = val
    if any(rec.values()):
        records.append(rec)

print(json.dumps(records))
"""

_PDF_PARSE_TEMPLATE = """
import pdfplumber, json, re

records = []
with pdfplumber.open("{path}") as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if not table:
                continue
            headers = [str(h).strip().lower().replace(" ", "_") for h in table[0]]
            for row in table[1:]:
                rec = dict(zip(headers, [str(c).strip() if c else "" for c in row]))
                records.append(rec)
        if not tables:
            text = page.extract_text() or ""
            for line in text.splitlines():
                parts = re.split(r"\\s{{2,}}|\\t", line.strip())
                if len(parts) >= 3:
                    records.append({{"raw": line.strip()}})

print(json.dumps(records))
"""

_IMAGE_PROMPT = """Extract all trades from this broker statement image.
Return a JSON array where each element has these exact keys:
  ticker, isin, direction (buy or sell), quantity (number), trade_date (YYYY-MM-DD), account
If a field is not present, use an empty string.
Return ONLY the JSON array, no explanation."""


def _sbx(session):
    """Get the underlying e2b AsyncSandbox. Adjust if your SDK version differs."""
    for attr in ("sandbox", "_sandbox", "e2b"):
        if hasattr(session, attr):
            candidate = getattr(session, attr)
            if hasattr(candidate, "files") or hasattr(candidate, "filesystem"):
                return candidate
    return session


async def _sbx_write(session, path: str, data: bytes) -> None:
    sbx = _sbx(session)
    if hasattr(sbx, "files"):
        await sbx.files.write(path, data)
    elif hasattr(sbx, "filesystem"):
        await sbx.filesystem.write(path, data)
    else:
        raise RuntimeError(f"Cannot write to sandbox: unknown session type {type(sbx)}")


async def _sbx_read(session, path: str) -> bytes:
    sbx = _sbx(session)
    if hasattr(sbx, "files"):
        return await sbx.files.read(path)
    elif hasattr(sbx, "filesystem"):
        return await sbx.filesystem.read(path)
    else:
        raise RuntimeError(f"Cannot read from sandbox: unknown session type {type(sbx)}")


async def _sbx_run(session, cmd: str) -> tuple[str, str, int]:
    """Returns (stdout, stderr, exit_code)."""
    sbx = _sbx(session)
    if hasattr(sbx, "commands"):
        result = await sbx.commands.run(cmd, timeout=120)
        return result.stdout, result.stderr, result.exit_code
    elif hasattr(sbx, "process"):
        proc = await sbx.process.start(cmd)
        out = await proc.wait()
        return out.stdout, out.stderr, out.exit_code
    else:
        raise RuntimeError(f"Cannot run command in sandbox: unknown session type {type(sbx)}")


async def _ensure_dir(session) -> None:
    await _sbx_run(session, f"mkdir -p {_COMPLIANCE_DIR}")


async def _read_registry(session) -> dict:
    try:
        data = await _sbx_read(session, _REGISTRY_PATH)
        return json.loads(data)
    except Exception:
        return {}


async def _write_registry(session, registry: dict) -> None:
    await _sbx_write(session, _REGISTRY_PATH, json.dumps(registry).encode())


async def _parse_excel_in_sandbox(session, sandbox_path: str, role: str) -> list:
    role_key = "TRADES" if role == "broker_statement" else "PC"
    script = _EXCEL_PARSE_TEMPLATE.format(path=sandbox_path, role=role_key)
    tmp_script = f"{_COMPLIANCE_DIR}/_parse_excel.py"
    await _sbx_write(session, tmp_script, script.encode())
    stdout, stderr, code = await _sbx_run(session, f"pip install openpyxl -q && python3 {tmp_script}")
    if code != 0:
        raise RuntimeError(f"Excel parse failed: {stderr}")
    return json.loads(stdout)


async def _parse_pdf_in_sandbox(session, sandbox_path: str) -> list:
    script = _PDF_PARSE_TEMPLATE.format(path=sandbox_path)
    tmp_script = f"{_COMPLIANCE_DIR}/_parse_pdf.py"
    await _sbx_write(session, tmp_script, script.encode())
    stdout, stderr, code = await _sbx_run(session, f"pip install pdfplumber -q && python3 {tmp_script}")
    if code != 0:
        raise RuntimeError(f"PDF parse failed: {stderr}")
    return json.loads(stdout)


async def _parse_image_with_claude(local_path: str) -> list:
    image_data = Path(local_path).read_bytes()
    b64 = base64.standard_b64encode(image_data).decode()
    ext = Path(local_path).suffix.lower().lstrip(".")
    media_type_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                      "gif": "image/gif", "webp": "image/webp"}
    media_type = media_type_map.get(ext, "image/png")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": _IMAGE_PROMPT},
            ],
        }],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rstrip("`").strip()
    return json.loads(text)


async def _generate_report(session, result: dict) -> bytes:
    result_json_path = f"{_COMPLIANCE_DIR}/_result.json"
    await _sbx_write(session, result_json_path, json.dumps(result).encode())
    report_script = f"""
import json, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

with open("{result_json_path}") as f:
    result = json.load(f)

wb = openpyxl.Workbook()

def header_row(ws, cols):
    for i, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=i, value=col)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")

# Sheet 1: Discrepancies
ws1 = wb.active
ws1.title = "Discrepancies"
cols1 = ["Ticker", "Direction", "Traded Qty", "Approved Qty",
         "Trade Date", "Approval Date", "Expiry Date", "Reason(s)"]
header_row(ws1, cols1)
for item in result["discrepancies"]:
    t = item["trade"]
    pc = item["preclearance"] or {{}}
    ws1.append([
        t.get("ticker", ""), t.get("direction", ""), t.get("quantity", ""),
        pc.get("approved_quantity", "N/A"), t.get("trade_date", ""),
        pc.get("approval_date", "N/A"), pc.get("expiry_date", "N/A"),
        ", ".join(item["reasons"]),
    ])

# Sheet 2: Clean Trades
ws2 = wb.create_sheet("Clean Trades")
cols2 = ["Ticker", "Direction", "Traded Qty", "Approved Qty", "Trade Date", "Approval Date", "Expiry Date"]
header_row(ws2, cols2)
for item in result["clean_trades"]:
    t = item["trade"]
    pc = item["preclearance"]
    ws2.append([
        t.get("ticker", ""), t.get("direction", ""), t.get("quantity", ""),
        pc.get("approved_quantity", ""), t.get("trade_date", ""),
        pc.get("approval_date", ""), pc.get("expiry_date", ""),
    ])

# Sheet 3: Exempt Trades
ws3 = wb.create_sheet("Exempt Trades")
cols3 = ["Ticker", "ISIN", "Direction", "Quantity", "Trade Date", "Exempt Reason"]
header_row(ws3, cols3)
for t in result["exempt_trades"]:
    ws3.append([
        t.get("ticker", ""), t.get("isin", ""), t.get("direction", ""),
        t.get("quantity", ""), t.get("trade_date", ""), t.get("exempt_reason", ""),
    ])

wb.save("{_REPORT_PATH}")
print("ok")
"""
    tmp = f"{_COMPLIANCE_DIR}/_gen_report.py"
    await _sbx_write(session, tmp, report_script.encode())
    stdout, stderr, code = await _sbx_run(session, f"python3 {tmp}")
    if code != 0:
        raise RuntimeError(f"Report generation failed: {stderr}")
    return await _sbx_read(session, _REPORT_PATH)


async def register_compliance_file(filename: str, role: str) -> str:
    """
    Register an uploaded file for compliance checking.

    Args:
        filename: Name of the uploaded file (must match a file the user uploaded this turn).
        role: One of 'broker_statement', 'preclearance', or 'index_reference'.
    """
    valid_roles = {"broker_statement", "preclearance", "index_reference"}
    if role not in valid_roles:
        return f"Invalid role '{role}'. Must be one of: {', '.join(sorted(valid_roles))}"

    uploaded: dict = cl.user_session.get("uploaded_files", {})
    if filename not in uploaded:
        available = list(uploaded.keys()) or ["(none)"]
        return f"File '{filename}' not found in this session. Available: {', '.join(available)}"

    local_path = uploaded[filename]
    ext = Path(filename).suffix.lower()
    session = get_sandbox_session()
    if session is None:
        return "Sandbox not available. Please start a new chat."

    await _ensure_dir(session)

    sandbox_path = f"{_COMPLIANCE_DIR}/{role}{ext}"
    data = Path(local_path).read_bytes()
    await _sbx_write(session, sandbox_path, data)

    if ext in _EXCEL_EXTENSIONS:
        records = await _parse_excel_in_sandbox(session, sandbox_path, role)
    elif ext in _PDF_EXTENSIONS:
        records = await _parse_pdf_in_sandbox(session, sandbox_path)
    elif ext in _IMAGE_EXTENSIONS:
        records = await _parse_image_with_claude(local_path)
    elif ext == ".json" and role == "index_reference":
        records = json.loads(data)
    else:
        return f"Unsupported file type '{ext}' for role '{role}'."

    json_path = f"{_COMPLIANCE_DIR}/{role}.json"
    await _sbx_write(session, json_path, json.dumps(records).encode())

    registry = await _read_registry(session)
    registry[role] = {"filename": filename, "records": len(records), "json_path": json_path}
    await _write_registry(session, registry)

    return (
        f"Registered '{filename}' as {role.replace('_', ' ')}. "
        f"Extracted {len(records)} record(s). "
        f"Registry now has: {', '.join(registry.keys())}."
    )


async def run_compliance_check() -> str:
    """
    Run the compliance check comparing registered broker statement against pre-clearance declarations.
    Both 'broker_statement' and 'preclearance' must be registered first via register_compliance_file.
    Returns a structured JSON summary for narration plus attaches a downloadable Excel report.
    """
    session = get_sandbox_session()
    if session is None:
        return json.dumps({"error": "Sandbox not available."})

    registry = await _read_registry(session)
    missing = [r for r in ("broker_statement", "preclearance") if r not in registry]
    if missing:
        return json.dumps({"error": f"Missing required files: {', '.join(missing)}. Please upload them first."})

    script_source = (Path(__file__).parent.parent / "compliance_check.py").read_bytes()
    await _sbx_write(session, _SCRIPT_PATH, script_source)

    trades_path = registry["broker_statement"]["json_path"]
    pc_path = registry["preclearance"]["json_path"]
    index_arg = ""
    if "index_reference" in registry:
        index_arg = registry["index_reference"]["json_path"]

    cmd = f"python3 {_SCRIPT_PATH} {trades_path} {pc_path}"
    if index_arg:
        cmd += f" {index_arg}"

    stdout, stderr, code = await _sbx_run(session, cmd)
    if code != 0:
        return json.dumps({"error": f"Comparison script failed: {stderr}"})

    result = json.loads(stdout)

    report_bytes = await _generate_report(session, result)

    report_local = Path("/tmp/compliance_report.xlsx")
    report_local.write_bytes(report_bytes)
    file_element = cl.File(
        name="compliance_report.xlsx",
        path=str(report_local),
        display="inline",
    )
    await cl.Message(content="Compliance report ready:", elements=[file_element]).send()

    return json.dumps(result)
```

- [ ] **Step 2: Verify the file imports without error**

```bash
python -c "import src.tools.compliance; print('OK')"
```

Expected: `OK` (the `anthropic` import and `cl` session calls won't fire at import time)

- [ ] **Step 3: Commit**

```bash
git add src/tools/compliance.py
git commit -m "feat: add register_compliance_file and run_compliance_check tools"
```

---

## Task 5: Wire up the compliance tools

**Files:**
- Modify: `src/tools/__init__.py`
- Modify: `src/agent.py`

- [ ] **Step 1: Export compliance tools from `src/tools/__init__.py`**

Replace `src/tools/__init__.py`:

```python
from src.tools.weather import get_weather
from src.tools.calculator import calculate
from src.tools.search import web_search
from src.tools.compliance import register_compliance_file, run_compliance_check

__all__ = ["get_weather", "calculate", "web_search", "register_compliance_file", "run_compliance_check"]
```

- [ ] **Step 2: Register compliance tools and update the agent's system prompt in `src/agent.py`**

Replace `src/agent.py`:

```python
from collections import deque

import chainlit as cl
from agents import Runner, function_tool
from agents.run import RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from openai.types.responses import ResponseTextDeltaEvent

from src.sandbox import get_sandbox_session
from src.tools.weather import get_weather as _get_weather
from src.tools.calculator import calculate as _calculate
from src.tools.search import web_search as _web_search
from src.tools.compliance import (
    register_compliance_file as _register_compliance_file,
    run_compliance_check as _run_compliance_check,
)


@function_tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return await _get_weather(city)


@function_tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    return _calculate(expression)


@function_tool
async def web_search(query: str) -> str:
    """Search the web for up-to-date information on a topic."""
    return await _web_search(query)


@function_tool
async def register_compliance_file(filename: str, role: str) -> str:
    """
    Register an uploaded file for compliance checking.
    Call this once per uploaded file before running the compliance check.
    filename: the exact name of the uploaded file.
    role: 'broker_statement', 'preclearance', or 'index_reference'.
    """
    return await _register_compliance_file(filename, role)


@function_tool
async def run_compliance_check() -> str:
    """
    Run the compliance check once both broker_statement and preclearance files are registered.
    Returns a JSON summary of discrepancies, clean trades, and exempt trades.
    Also attaches a downloadable Excel report.
    """
    return await _run_compliance_check()


AGENT = SandboxAgent(
    name="AI Assistant",
    model="gpt-4o-mini",
    instructions=(
        "You are a helpful assistant with shell access to a secure e2b sandbox. "
        "Use exec_command to run Python scripts or shell commands for code execution, data analysis, or calculations. "
        "You also have get_weather, calculate, and web_search tools.\n\n"
        "COMPLIANCE CHECKING:\n"
        "When the user uploads broker statements or pre-clearance files for compliance review:\n"
        "1. Call register_compliance_file(filename, role) for each uploaded file. "
        "   Role must be 'broker_statement', 'preclearance', or 'index_reference'.\n"
        "2. Once both 'broker_statement' and 'preclearance' are registered, call run_compliance_check().\n"
        "3. Parse the returned JSON and narrate a clear plain-English summary:\n"
        "   - State total trades reviewed, how many are clean, how many are exempt (index funds), "
        "     and how many have discrepancies.\n"
        "   - For each discrepancy, explain it in plain English: what was traded, what was approved, "
        "     and exactly what rule was violated.\n"
        "4. If a file arrives in one message and the other arrives later, acknowledge receipt and wait.\n"
        "5. Diversified index ETFs (e.g. SPY, QQQ, VTI) are automatically exempt — no pre-clearance needed."
    ),
    tools=[get_weather, calculate, web_search, register_compliance_file, run_compliance_check],
    capabilities=[Shell()],
)


async def run_agent(input_list: list) -> list:
    """Stream one agentic turn and return the updated input list."""
    msg = cl.Message(content="")
    await msg.send()

    session = get_sandbox_session()
    run_config = RunConfig(
        sandbox=SandboxRunConfig(session=session) if session else None
    )

    result = Runner.run_streamed(AGENT, input=input_list, run_config=run_config)
    active_steps: deque[cl.Step] = deque()

    async for event in result.stream_events():
        if event.type == "raw_response_event":
            if isinstance(event.data, ResponseTextDeltaEvent):
                await msg.stream_token(event.data.delta)

        elif event.type == "run_item_stream_event":
            if event.name == "tool_called":
                step = cl.Step(name=event.item.raw_item.name, type="tool")
                step.input = event.item.raw_item.arguments
                await step.send()
                active_steps.append(step)

            elif event.name == "tool_output":
                if active_steps:
                    step = active_steps.popleft()
                    step.output = str(event.item.output)
                    await step.update()

    await msg.update()
    return result.to_input_list()
```

- [ ] **Step 3: Verify imports are clean**

```bash
python -c "from src.agent import AGENT; print('tools:', [t.name for t in AGENT.tools])"
```

Expected output includes: `register_compliance_file`, `run_compliance_check`

- [ ] **Step 4: Commit**

```bash
git add src/tools/__init__.py src/agent.py
git commit -m "feat: register compliance tools with SandboxAgent"
```

---

## Task 6: Handle file uploads in app.py

**Files:**
- Modify: `app.py`

Chainlit file uploads arrive as `message.elements` — a list of `cl.File` objects with `.name` and `.path` attributes. We store them in the session so `register_compliance_file` can look them up by name.

- [ ] **Step 1: Update `app.py`**

Replace `app.py`:

```python
from dotenv import load_dotenv

load_dotenv()

import chainlit as cl

from src.agent import run_agent
from src.sandbox import create_sandbox, destroy_sandbox


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("input_list", [])
    cl.user_session.set("uploaded_files", {})
    await create_sandbox()
    await cl.Message(
        content=(
            "Hello! I'm your AI agent. I have access to these tools:\n\n"
            "- **shell** — execute Python or shell commands in a secure e2b sandbox (state persists per conversation)\n"
            "- **get_weather** — current weather for any city\n"
            "- **calculate** — evaluate math expressions\n"
            "- **web_search** — search the web\n"
            "- **compliance check** — upload a broker statement (Excel, PDF, or image) and a pre-clearance Excel "
            "to check for trading discrepancies\n\n"
            "Ask me anything!"
        )
    ).send()


@cl.on_chat_end
async def on_chat_end():
    await destroy_sandbox()


@cl.on_message
async def on_message(message: cl.Message):
    input_list: list = cl.user_session.get("input_list")
    uploaded_files: dict = cl.user_session.get("uploaded_files", {})

    new_files = {}
    for element in message.elements:
        if hasattr(element, "path") and element.path:
            new_files[element.name] = element.path

    if new_files:
        uploaded_files.update(new_files)
        cl.user_session.set("uploaded_files", uploaded_files)

    content = message.content or ""
    if new_files:
        names = ", ".join(new_files.keys())
        content = f"{content}\n\n[Uploaded files this message: {names}]".strip()

    input_list = input_list + [{"role": "user", "content": content}]
    try:
        input_list = await run_agent(input_list)
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()
    cl.user_session.set("input_list", input_list)
```

- [ ] **Step 2: Verify the app starts without errors**

```bash
chainlit run app.py --headless &
sleep 3
kill %1
```

Expected: no import errors or tracebacks during startup.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: store uploaded files in session for compliance tools"
```

---

## Task 7: Run the full test suite

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass. Fix any failures before pushing.

- [ ] **Step 2: Push branch**

```bash
git push -u origin compliance-broker-statement-skill
```
