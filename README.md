# AI Agent — Chainlit + OpenAI

A conversational AI agent with a **code interpreter** and tool use, built with Chainlit and the OpenAI API. Deployable to Fly.io via GitHub Actions.

## Tools

| Tool | What it does |
|---|---|
| `run_code` | Executes Python or shell in an isolated e2b sandbox — state persists per conversation |
| `get_weather` | Live weather for any city via wttr.in |
| `calculate` | Evaluates safe math expressions |
| `web_search` | Searches the web via DuckDuckGo |

## Project structure

```
├── app.py                    # Chainlit hooks (thin glue layer)
├── src/
│   ├── agent.py              # Streaming agentic loop
│   ├── sandbox.py            # e2b sandbox lifecycle
│   └── tools/
│       ├── __init__.py       # Tool registry + dispatcher
│       ├── code_interpreter.py
│       ├── weather.py
│       ├── calculator.py
│       └── search.py
├── Dockerfile
├── fly.toml
└── .github/workflows/deploy.yml
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

# 4. Run
chainlit run app.py
```

Open http://localhost:8000 in your browser.

**Get your keys:**
- OpenAI: https://platform.openai.com/api-keys
- e2b (code interpreter sandbox): https://e2b.dev/dashboard → API Keys (free: 100h/month)

## Deploy to Fly.io via GitHub

Fly.io builds from the `Dockerfile` and deploys on every push to `master`.

### One-time setup

**1. Install Fly CLI and create the app**

```powershell
iwr https://fly.io/install.ps1 -useb | iex
fly auth login
```

```bash
# Edit fly.toml and set a unique app name, then:
fly apps create <your-app-name>
```

**2. Set secrets on Fly.io**

```bash
fly secrets set OPENAI_API_KEY=sk-... E2B_API_KEY=e2b_...
```

**3. Add `FLY_API_TOKEN` to GitHub**

```bash
fly tokens create deploy -x 999999h
```

Copy the token, then go to:
**GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

Name: `FLY_API_TOKEN`, Value: *(paste token)*

**4. Push to deploy**

```bash
git push origin master
```

GitHub Actions runs `.github/workflows/deploy.yml` → builds the Docker image on Fly's infrastructure → deploys. Check progress at:

```bash
fly logs
fly status
```

Your app will be live at `https://<your-app-name>.fly.dev`.

### Manual deploy (without GitHub Actions)

```bash
fly deploy
```

## How it works

1. User sends a message → Chainlit `on_message` fires
2. `src/agent.py` calls `gpt-4o-mini` with all tool schemas, streaming the response
3. If the model returns `tool_calls`, each tool runs and the result is appended to history
4. The loop repeats until the model gives a plain text reply
5. `run_code` calls forward to an **e2b microVM sandbox** — fully isolated, no host access
6. Each tool call is shown as a collapsible Step in the UI

## Costs

| Service | Free tier | Overage |
|---|---|---|
| Fly.io | ~$0 with auto-stop (machine sleeps when idle) | ~$0.0002/sec active |
| e2b | 100 sandbox-hours/month | $0.16/hour |
| OpenAI | Pay-per-use | gpt-4o-mini is ~$0.15/1M tokens |
