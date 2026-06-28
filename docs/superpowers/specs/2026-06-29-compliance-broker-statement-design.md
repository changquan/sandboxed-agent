# Compliance Broker Statement Checker — Design Spec

**Date:** 2026-06-29
**Branch:** compliance-broker-statement-skill
**Status:** Approved

---

## Overview

A new capability for the Chainlit AI agent that allows a compliance officer to upload broker statements (Excel, PDF, or image) and a pre-clearance declarations file (Excel), then receive a plain-English discrepancy report in chat plus a downloadable Excel report file.

---

## Architecture

### New files

```
src/
  tools/
    compliance.py          # Two new agent tools: register_compliance_file, run_compliance_check
  compliance_check.py      # Deterministic comparison script (runs inside E2B sandbox)
```

### Modified files

```
src/
  tools/__init__.py        # Export new compliance tools
  agent.py                 # Register compliance tools with SandboxAgent
requirements.txt           # Add pdfplumber
```

### Tools

**`register_compliance_file(file_path, role)`**
- `role`: `"broker_statement"` or `"preclearance"`
- Uploads the file from Chainlit's temp path into the E2B sandbox
- Detects file type and runs the appropriate parser (see Parsing section)
- Saves normalized JSON output to the sandbox
- Writes/updates a session registry file (`compliance_registry.json`) tracking which roles are loaded
- Returns a plain confirmation string so the agent can acknowledge receipt

**`run_compliance_check()`**
- Reads `compliance_registry.json` to verify both `broker_statement` and `preclearance` are registered
- Uploads `src/compliance_check.py` to the sandbox (overwrites on each call to keep it current)
- Executes the script via `exec_command`
- Reads the JSON output from the sandbox
- Generates a two-sheet Excel report (`compliance_report.xlsx`) in the sandbox
- Downloads the report and attaches it as a Chainlit file element for download
- Returns structured JSON for the agent to narrate in plain English

---

## File Parsing

The agent handles three input formats for broker statements, and one (Excel) for pre-clearance.

| Format | Where it runs | Library/Method | Notes |
|---|---|---|---|
| `.xlsx` / `.xls` | E2B sandbox via `exec_command` | `pandas` | Header row auto-detected; used for both broker statements and pre-clearance |
| `.pdf` | E2B sandbox via `exec_command` | `pdfplumber` | Table extraction first; falls back to line-by-line text parsing |
| `.png` / `.jpg` / `.jpeg` / `.gif` | Tool code (outside sandbox) | Claude vision API (`claude-sonnet-4-6`) | Image bytes read locally, sent to Anthropic API with a structured extraction prompt; normalized JSON result is then uploaded to sandbox |

### Normalized broker statement record
```json
{
  "ticker": "AAPL",
  "isin": "US0378331005",
  "direction": "buy",
  "quantity": 500,
  "trade_date": "2026-06-15",
  "account": "ACC-001"
}
```

### Normalized pre-clearance record
```json
{
  "ticker": "AAPL",
  "isin": "US0378331005",
  "direction": "buy",
  "approved_quantity": 1000,
  "approval_date": "2026-06-10",
  "expiry_date": "2026-06-20",
  "employee": "Jane Smith"
}
```

Field name mapping from real source files (FIS Compliance Manager or custom Excel) to this normalized schema is handled at parse time. Ticker or ISIN can be used for matching — whichever is present.

---

## Deterministic Comparison Script (`src/compliance_check.py`)

This script is fixed — it never changes at runtime. The LLM is not involved in the comparison logic.

### Steps

1. **Load** normalized broker trades JSON and pre-clearance declarations JSON from sandbox paths passed as CLI args
2. **Normalize** — uppercase all tickers/ISINs, strip whitespace, parse all dates to `datetime.date`
3. **Match** — for each trade, find the best pre-clearance candidate where:
   - `ticker` matches (or `isin` matches if ticker absent)
   - `direction` matches exactly (`buy`/`sell`)
4. **Check** each matched pair for discrepancies:

| Discrepancy Type | Rule |
|---|---|
| No approval found | Trade has no matching pre-clearance entry |
| Outside approval window | `trade_date < approval_date` OR `trade_date > expiry_date` |
| Quantity exceeded | `traded_quantity > approved_quantity` |

5. **Output** structured JSON to stdout:
```json
{
  "summary": {
    "total_trades": 12,
    "matched": 10,
    "discrepancies": 3
  },
  "discrepancies": [
    {
      "trade": { "ticker": "MSFT", "direction": "buy", "quantity": 200, "trade_date": "2026-06-18" },
      "preclearance": { "ticker": "MSFT", "approved_quantity": 100, "expiry_date": "2026-06-17" },
      "reasons": ["quantity_exceeded", "outside_window"]
    }
  ],
  "clean_trades": [ ... ]
}
```

### Matching rules (partial match)
- Ticker + direction must match exactly — no tolerance
- Traded quantity ≤ approved quantity is **clean** (partial fills are allowed)
- Traded quantity > approved quantity is a **discrepancy**
- Trade date must fall within `[approval_date, expiry_date]` inclusive

---

## Output

### In-chat summary (agent narrates)
- Total trades reviewed
- Number of clean trades
- Number of discrepancies
- Plain-English description of each discrepancy (e.g., "MSFT buy of 200 shares on 2026-06-18 exceeded approved quantity of 100 and fell outside the approval window which expired 2026-06-17")

### Downloadable report (`compliance_report.xlsx`)
Two sheets:
- **Discrepancies** — one row per discrepancy with columns: Ticker, Direction, Traded Qty, Approved Qty, Trade Date, Approval Date, Expiry Date, Reason(s)
- **Clean Trades** — one row per matched clean trade for reference

---

## Multi-turn Upload Flow

The agent handles both upload patterns gracefully:

- **Both files in one message:** Agent calls `register_compliance_file` twice then `run_compliance_check`
- **Files in separate messages:** Agent calls `register_compliance_file` for the first file, acknowledges receipt, waits; calls `register_compliance_file` for the second file, then `run_compliance_check`

The E2B sandbox session persists across turns so registered files survive between messages.

---

## Dependencies

```
pdfplumber      # PDF table extraction (new)
pandas          # Already used / Excel parsing
openpyxl        # Already used / Excel writing
anthropic       # Already used / Claude vision for image parsing
```

---

## Out of Scope

- Multi-employee / multi-account batch checking
- Direct integration with FIS Compliance Manager API
- Historical trend analysis
- Automated escalation or alerts
