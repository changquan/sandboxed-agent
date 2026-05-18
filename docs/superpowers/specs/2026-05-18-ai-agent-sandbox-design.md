# ai-agent-sandbox — Developer Reference

_Date: 2026-05-18 (last updated: 2026-05-19)_

---

## 1. Overview

**ai-agent-sandbox** is a web-based AI chat application that lets users converse with a tool-using OpenAI agent through a Chainlit UI. The agent runs inside an **e2b cloud sandbox** and can execute real shell/Python commands, look up live weather, evaluate math, and search the web.

| Property | Value |
|---|---|
| Interface | Chainlit web UI (chat) |
| Agent framework | OpenAI Agents SDK (`openai-agents`) |
| LLM | OpenAI `gpt-4o-mini` (streaming) |
| Agent type | `SandboxAgent` with `Shell` capability |
| Code execution | e2b cloud sandbox via `E2BSandboxClient` (per-session, persistent state) |
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
│          src/agent.py  (run_agent)                  │
│  • SandboxAgent + Shell capability                  │
│  • Runner.run_streamed() with RunConfig(sandbox=…)  │
│  • Streams raw_response + run_item events           │
└────┬──────────────────────────┬──────────────────────┘
     │ OpenAI Responses API     │ @function_tool calls
     │ (streaming)              │
     ▼                   ┌──────▼──────────────────────┐
 OpenAI API              │        src/tools/           │
 (gpt-4o-mini)           │  weather.py  calculator.py  │
                         │  search.py                  │
                         └─────────────────────────────┘

  exec_command (Shell capability) ──► src/sandbox.py
                                          │
                                    E2BSandboxClient
                                          │
                                   e2b cloud sandbox
                                   (per session, stateful)
```

**Key architectural decisions:**

- `app.py` owns only Chainlit lifecycle hooks — no business logic.
- `agent.py` uses the OpenAI Agents SDK's `SandboxAgent` + `Runner.run_streamed()`. Tool dispatch and the multi-turn loop are handled by the SDK; `run_agent` just processes streaming events.
- `SandboxAgent` is configured with `capabilities=[Shell()]` only. The `Filesystem` capability is excluded because it adds `SandboxApplyPatchTool` (type `"custom"`), which `gpt-4o-mini` rejects. The `Shell` capability adds `ExecCommandTool` (type `"function"`), which works with all standard OpenAI models.
- The e2b sandbox session is created once per chat session and lives in `cl.user_session`. All `exec_command` calls in a session share the same sandbox — files, environment, and installed packages persist across turns.
- No global state — concurrent sessions are fully isolated via `cl.user_session`.
- Conversation history is stored as the Agents SDK's `input_list` format (list of response items) and passed back to `Runner.run_streamed()` each turn via `result.to_input_list()`.

---

## 3. Module Breakdown

| File | Responsibility |
|---|---|
| `app.py` | Chainlit entry point. Registers `on_chat_start`, `on_chat_end`, `on_message` hooks. Creates/destroys e2b sandbox session and delegates all agent logic to `run_agent`. |
| `src/agent.py` | Defines `SandboxAgent` with `Shell` capability and `@function_tool` wrappers. `run_agent()` calls `Runner.run_streamed()` with `RunConfig(sandbox=SandboxRunConfig(session=...))`, then processes streaming events to update the Chainlit UI. |
| `src/sandbox.py` | e2b session lifecycle. `create_sandbox()` uses `E2BSandboxClient` to create an `E2BSandboxType.E2B` session (600s timeout, pause on exit). `get_sandbox_session()` returns the active session for the current chat. Gracefully degrades if creation fails. |
| `src/tools/weather.py` | `get_weather(city)` — fetches from `wttr.in` JSON API via `httpx`. |
| `src/tools/calculator.py` | `calculate(expression)` — evaluates Python math expressions with a character allowlist. No `__builtins__` to prevent arbitrary execution. |
| `src/tools/search.py` | `web_search(query)` — POSTs to Tavily Search API, returns top results as title + URL + snippet. |
| `src/tools/__init__.py` | Re-exports the three `@function_tool`-wrapped tool functions. |

---

## 4. Data Flow

**Per-message lifecycle:**

```
User sends message
  │
  ▼
on_message(message)
  │  appends {"role": "user", "content": ...} to input_list
  ▼
run_agent(input_list)
  │
  │  Runner.run_streamed(AGENT, input=input_list,
  │                      run_config=RunConfig(sandbox=SandboxRunConfig(session=…)))
  ▼
Stream events
  ├─ raw_response_event (ResponseTextDeltaEvent)
  │    → stream token to Chainlit message
  └─ run_item_stream_event
       ├─ "tool_called"  → open cl.Step, record name + args
       └─ "tool_output"  → close cl.Step with result
  │
  ▼
result.to_input_list()  →  returned as new input_list
  │
  ▼
cl.user_session.set("input_list", input_list)
```

**exec_command flow (Shell tool):**

```
Agent decides to call exec_command(cmd="python3 script.py")
  │
  ▼
Shell capability routes call to ExecCommandTool._invoke()
  │
  ▼
session.exec(cmd, shell=True)  →  runs inside e2b sandbox
  │
  ▼
Returns stdout + stderr + exit code as string to agent
```

**input_list format** (OpenAI Agents SDK response items, passed between turns):

```python
[
  {"role": "user",      "content": "user text"},
  # assistant response items (text, tool calls) added by SDK
  # tool output items added by SDK after each tool execution
]
```

---

## 5. Tool Inventory

| Tool | Source | Transport | Input | Output |
|---|---|---|---|---|
| `exec_command` | Shell capability (SandboxAgent) | e2b sandbox `session.exec()` | `cmd: str` | stdout + stderr + exit code |
| `get_weather` | `@function_tool` | HTTP GET `wttr.in` | `city: str` | `"City: desc, temp°C (feels like X°C)"` |
| `calculate` | `@function_tool` | In-process `eval` | `expression: str` | Result string or error message |
| `web_search` | `@function_tool` | HTTP POST Tavily API | `query: str` | Top results as title + URL + snippet |

**Notes:**

- `exec_command` runs in the e2b sandbox. The agent can run `python3 -c "..."`, `pip install ...`, write files, and chain commands across turns — the sandbox stays alive for the session.
- `calculate` uses a character allowlist (`0-9 + - * / ( ) . , ** %`) and strips `__builtins__` — it cannot execute arbitrary code.
- `web_search` uses the Tavily Search API. If `TAVILY_API_KEY` is not set, the tool returns a graceful error string. Free tier: 1,000 searches/month.
- All `@function_tool` tools return plain strings; error conditions are returned as human-readable strings rather than raised exceptions.

---

## 6. Configuration

**Environment variables** (defined in `.env`, loaded via `python-dotenv`):

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Authenticates requests to the OpenAI API |
| `E2B_API_KEY` | Yes | Authenticates the `E2BSandboxClient`. If absent, sandbox creation fails and a warning is shown; other tools still work. |
| `TAVILY_API_KEY` | No | Enables the `web_search` tool via Tavily API. If absent, search returns a graceful error. Get a key at tavily.com (free tier: 1,000 searches/month) |

**Dependencies** (`requirements.txt`):

| Package | Version | Role |
|---|---|---|
| `chainlit` | `>=2.0.0` | Web UI + WebSocket server + session management |
| `openai-agents[e2b]` | `>=0.17.0` | OpenAI Agents SDK + e2b extension (`E2BSandboxClient`, `SandboxAgent`) |
| `httpx` | `>=0.27.0` | Async HTTP client for weather and search tools |
| `python-dotenv` | `>=1.0.0` | Loads `.env` at startup |

**Running the app:**

```powershell
chainlit run app.py
```

**Sandbox timeout:** The e2b sandbox is created with a 600-second server-side timeout and `pause_on_exit=True`. If the browser tab closes without triggering `on_chat_end`, the sandbox pauses rather than immediately billing; it resumes if the session reconnects, or expires after the timeout.

