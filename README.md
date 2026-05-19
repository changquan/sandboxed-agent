# AI Agent — Chainlit + OpenAI Agents SDK

A conversational AI agent with sandboxed code execution and tool use, built with Chainlit and the OpenAI Agents SDK.

## Tools

| Tool | What it does |
|---|---|
| `exec_command` | Runs shell commands (including Python) in an isolated e2b sandbox — state persists per conversation |
| `get_weather` | Live weather for any city via wttr.in |
| `calculate` | Evaluates safe math expressions |
| `web_search` | Searches the web via Tavily API |

## Project structure

```
├── app.py                    # Chainlit hooks (thin glue layer)
├── src/
│   ├── agent.py              # SandboxAgent + streaming event loop
│   ├── sandbox.py            # e2b session lifecycle (E2BSandboxClient)
│   └── tools/
│       ├── __init__.py
│       ├── weather.py
│       ├── calculator.py
│       └── search.py
```

## Local setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your keys:
#   OPENAI_API_KEY=sk-...
#   E2B_API_KEY=e2b_...
#   TAVILY_API_KEY=tvly-...

# 4. Run
chainlit run app.py
```

Open http://localhost:8000 in your browser.

**Get your keys:**
- OpenAI: https://platform.openai.com/api-keys
- e2b (code sandbox): https://e2b.dev/dashboard → API Keys (free: 100h/month)
- Tavily (web search): https://tavily.com → free tier: 1,000 searches/month

## How it works

1. User sends a message → Chainlit `on_message` fires
2. `src/agent.py` runs `Runner.run_streamed()` from the OpenAI Agents SDK, streaming events
3. The agent (`SandboxAgent`) decides which tools to call; each call appears as a collapsible Step in the UI
4. Shell commands run inside a live **e2b microVM** via `exec_command` — the sandbox is created once per chat session and keeps state (files, installed packages, running processes) across turns
5. The loop continues until the agent produces a final text reply

## Costs

| Service | Free tier | Overage |
|---|---|---|
| e2b | 100 sandbox-hours/month | $0.16/hour |
| OpenAI | Pay-per-use | gpt-4o-mini is ~$0.15/1M tokens |
| Tavily | 1,000 searches/month | pay-per-use above |
