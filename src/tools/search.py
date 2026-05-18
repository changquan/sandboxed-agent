import os

import httpx

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for up-to-date information on a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                }
            },
            "required": ["query"],
        },
    },
}


async def web_search(query: str) -> str:
    if not TAVILY_API_KEY:
        return "Web search unavailable: TAVILY_API_KEY is not set."
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 3},
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return "No results found."
        lines = [
            f"- {r['title']}: {r['url']}\n  {r.get('content', '')[:200]}"
            for r in results
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"
