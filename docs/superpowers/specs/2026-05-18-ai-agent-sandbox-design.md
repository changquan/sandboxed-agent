# ai-agent-sandbox — Developer Reference

_Date: 2026-05-18_

---

## 1. Overview

**ai-agent-sandbox** is a web-based AI chat application that lets users converse with a tool-using OpenAI agent through a Chainlit UI. The agent can execute real Python/shell code in an isolated cloud sandbox, look up live weather, evaluate math, and search the web.

| Property | Value |
|---|---|
| Interface | Chainlit web UI (chat) |
| LLM | OpenAI `gpt-4o-mini` (streaming) |
| Code execution | e2b cloud sandbox (per-session, persistent state) |
| Conversation memory | In-process per session (`cl.user_session`) |
| Entry point | `app.py` |
| Runtime | Python 3.11, async (`asyncio`) |

The system is intentionally a sandbox / learning project — no database, no auth, no multi-user persistence. One session = one sandbox instance.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser (User)                    │
└──────────────────────┬──────────────────────────────┘
                       │  WebSocket (Chainlit)
┌──────────────────────▼──────────────────────────────┐
│                    app.py                           │
│   on_chat_start │ on_chat_end │ on_message          │
└──────────────────────┬──────────────────────────────┘
                       │  calls
┌──────────────────────▼──────────────────────────────┐
│               src/agent.py  (run_agent)             │
│  • Maintains conversation history (list of dicts)   │
│  • Streams from OpenAI API                          │
│  • Handles tool_calls loop until finish=stop        │
└────┬──────────────────────────┬──────────────────────┘
     │ OpenAI API (streaming)   │ dispatches to
     │                   ┌──────▼────────────────────┐
     │                   │   src/tools/__init__.py   │
     │                   │      run_tool(name, args) │
     │                   └──┬──────┬──────┬──────┬───┘
     │                      │      │      │      │
     │               weather│  calc│search│  code│
     │                   .py│   .py│   .py│ _interp.py
     │                      │      │      │      │
     │                      │      │      │  ┌───▼──────────────┐
     │                      │      │      │  │  src/sandbox.py  │
     │                      │      │      │  │  e2b AsyncSandbox│
     │                      │      │      │  │  (per session)   │
     │                      │      │      │  └──────────────────┘
     ▼
 OpenAI API
 (gpt-4o-mini)
```

**Key architectural decisions:**

- `app.py` owns only Chainlit lifecycle hooks — no business logic.
- `agent.py` is the single agentic loop; all tool dispatch goes through `run_tool`.
- Each tool module exports a schema dict + async/sync function — uniform interface.
- The e2b sandbox is created once per chat session and lives in `cl.user_session`; state (variables, files) persists across all `run_code` calls in that session.
- No global state — concurrent sessions are fully isolated via `cl.user_session`.

---

## 3. Module Breakdown

| File | Responsibility |
|---|---|
| `app.py` | Chainlit entry point. Registers `on_chat_start`, `on_chat_end`, `on_message` hooks. Initializes/destroys sandbox and delegates all agent logic. |
| `src/agent.py` | Agentic loop. Streams OpenAI completions, accumulates streaming tool call chunks, dispatches tool calls, appends results to history, loops until `finish_reason == "stop"`. |
| `src/sandbox.py` | e2b sandbox lifecycle. `create_sandbox()` / `destroy_sandbox()` called at session start/end. `get_sandbox()` returns the active sandbox for the current session or `None`. Gracefully degrades when `E2B_API_KEY` is absent. |
| `src/tools/__init__.py` | Tool registry. Exports `TOOLS` (list of all OpenAI function schemas) and `run_tool(name, args)` dispatcher. |
| `src/tools/weather.py` | `get_weather(city)` — fetches from `wttr.in` JSON API via `httpx`. |
| `src/tools/calculator.py` | `calculate(expression)` — evaluates Python math expressions with a character allowlist. No `__builtins__` to prevent arbitrary execution. |
| `src/tools/search.py` | `web_search(query)` — queries a DuckDuckGo proxy API, returns top 3 results as title + link. |
| `src/tools/code_interpreter.py` | `run_code(code, language)` — runs Python or shell in the e2b sandbox. Returns combined stdout, stderr, result text, and error info. |

---

## 4. Data Flow

**Per-message lifecycle:**

```
User sends message
  │
  ▼
on_message(message)
  │  appends {"role": "user", "content": ...} to history
  ▼
run_agent(history)  ◄────────────────────────────┐
  │                                               │
  │  POST /chat/completions (stream=True)         │
  │  messages = [system_prompt] + history         │
  ▼                                               │
Stream chunks                                     │
  ├─ delta.content  → stream tokens to UI         │
  └─ delta.tool_calls → accumulate into dict      │
  │                                               │
  ▼                                               │
finish_reason == "tool_calls"?                    │
  ├─ NO  → append assistant message, break        │
  └─ YES → append assistant + tool_calls to history
           │                                      │
           ▼                                      │
        run_tool(name, args) for each call        │
           │  result string returned              │
           ▼                                      │
        append {"role": "tool", ...} to history   │
        open new cl.Message, loop ──────────────►─┘
```

**History format** (OpenAI messages list, mutated in place across the loop):

```python
[
  {"role": "system",    "content": "..."},          # prepended each request, not stored
  {"role": "user",      "content": "user text"},
  {"role": "assistant", "tool_calls": [...]},        # when tools were called
  {"role": "tool",      "tool_call_id": "...", "content": "tool result"},
  {"role": "assistant", "content": "final reply"},
]
```

History is stored in `cl.user_session` and persists for the duration of the session only — it is lost when the browser tab closes.

---

## 5. Tool Inventory

| Tool | Function | Transport | Input | Output |
|---|---|---|---|---|
| `get_weather` | Current weather for a city | HTTP GET `wttr.in` | `city: str` | `"City: desc, temp°C (feels like X°C)"` |
| `calculate` | Evaluate a math expression | In-process `eval` | `expression: str` | Result string or error message |
| `web_search` | Search the web | HTTP GET DuckDuckGo proxy | `query: str` | Up to 3 results as `"- title: url"` lines |
| `run_code` | Execute Python or shell | e2b cloud sandbox (async) | `code: str`, `language: "python"\|"shell"` | Combined stdout + stderr + result + error |

**Notes:**

- `calculate` uses a character allowlist (`0-9 + - * / ( ) . , ** %`) and strips `__builtins__` — it cannot execute arbitrary code.
- `run_code` sandbox state (variables, imports, installed packages, written files) persists across all calls within the same session; a new session gets a fresh sandbox.
- `web_search` depends on a third-party DuckDuckGo proxy (`ddg-api.herokuapp.com`) — availability is not guaranteed.
- All tools return plain strings back to the agent; error conditions are returned as human-readable strings rather than raised exceptions.

---

## 6. Configuration

**Environment variables** (defined in `.env`, loaded via `python-dotenv`):

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Authenticates requests to the OpenAI API |
| `E2B_API_KEY` | No | Enables the e2b code interpreter sandbox. If absent, `run_code` is disabled and a warning is shown at session start |

**Dependencies** (`requirements.txt`):

| Package | Version | Role |
|---|---|---|
| `chainlit` | `>=2.0.0` | Web UI + WebSocket server + session management |
| `openai` | `>=1.30.0,<2.0.0` | OpenAI async client (pinned below v2 — breaking streaming API changes in v2) |
| `httpx` | `>=0.27.0` | Async HTTP client for weather and search tools |
| `python-dotenv` | `>=1.0.0` | Loads `.env` at startup |
| `e2b-code-interpreter` | `>=1.0.0` | e2b async sandbox for code execution |

**Running the app:**

```powershell
.venv\Scripts\chainlit.exe run app.py
# or
.\run.ps1
```

**Sandbox timeout:** The e2b sandbox is configured with a 600-second (10-minute) server-side timeout. If the browser tab closes without triggering `on_chat_end`, the sandbox auto-expires.
