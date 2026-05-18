from src.tools.weather import get_weather, WEATHER_SCHEMA
from src.tools.calculator import calculate, CALCULATOR_SCHEMA
from src.tools.search import web_search, SEARCH_SCHEMA
from src.tools.code_interpreter import run_code, CODE_SCHEMA

TOOLS = [WEATHER_SCHEMA, CALCULATOR_SCHEMA, SEARCH_SCHEMA, CODE_SCHEMA]


async def run_tool(name: str, args: dict) -> str:
    if name == "get_weather":
        return await get_weather(**args)
    elif name == "calculate":
        return calculate(**args)
    elif name == "web_search":
        return await web_search(**args)
    elif name == "run_code":
        return await run_code(**args)
    return f"Unknown tool: {name}"
