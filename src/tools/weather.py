import httpx

WEATHER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city name, e.g. 'London'",
                }
            },
            "required": ["city"],
        },
    },
}


async def get_weather(city: str) -> str:
    url = f"https://wttr.in/{city}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(url)
            data = resp.json()
        current = data["current_condition"][0]
        temp_c = current["temp_C"]
        desc = current["weatherDesc"][0]["value"]
        feels = current["FeelsLikeC"]
        return f"{city}: {desc}, {temp_c}°C (feels like {feels}°C)"
    except Exception as e:
        return f"Could not fetch weather for {city}: {e}"
