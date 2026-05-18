# AI Agent — Chainlit + OpenAI

A tool-using conversational agent built with **Chainlit** and the **OpenAI Chat Completions API**.

## Tools

| Tool | What it does |
|---|---|
| `get_weather` | Fetches live weather for any city via wttr.in |
| `calculate` | Evaluates safe math expressions |
| `web_search` | Searches the web via DuckDuckGo |

## Setup

```bash
# 1. Copy and fill in your API key
cp .env.example .env

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
chainlit run app.py
```

Then open http://localhost:8000 in your browser.

## How it works

1. User sends a message.
2. The app calls `gpt-4o-mini` with the available tool schemas.
3. If the model returns `tool_calls`, each tool is executed and the result is fed back.
4. The loop continues until the model returns a final text response (no more tool calls).
5. Each tool invocation is shown as a collapsible **Step** in the UI.
