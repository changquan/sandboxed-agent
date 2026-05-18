import json
import os
import httpx
import chainlit as cl
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Create a .env file with OPENAI_API_KEY=sk-...")

client = AsyncOpenAI(api_key=_api_key)

TOOLS = [
    {
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
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A Python-evaluable math expression, e.g. '2 ** 10 + 42'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
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
    },
]


async def run_tool(name: str, args: dict) -> str:
    if name == "get_weather":
        city = args["city"]
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

    elif name == "calculate":
        expr = args["expression"]
        try:
            # Restrict to safe math evaluation
            allowed = set("0123456789+-*/().,** %")
            if not all(c in allowed for c in expr.replace(" ", "")):
                return "Expression contains disallowed characters."
            result = eval(expr, {"__builtins__": {}})  # noqa: S307
            return str(result)
        except Exception as e:
            return f"Calculation error: {e}"

    elif name == "web_search":
        query = args["query"]
        url = f"https://ddg-api.herokuapp.com/search?query={query}&limit=3"
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(url)
                results = resp.json()
            lines = [f"- {r['title']}: {r['link']}" for r in results[:3]]
            return "\n".join(lines) if lines else "No results found."
        except Exception as e:
            return f"Search unavailable: {e}"

    return f"Unknown tool: {name}"


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await cl.Message(
        content=(
            "Hello! I'm your AI agent. I have access to these tools:\n\n"
            "- **get_weather** — current weather for any city\n"
            "- **calculate** — evaluate math expressions\n"
            "- **web_search** — search the web\n\n"
            "Ask me anything!"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})

    msg = cl.Message(content="")
    await msg.send()

    try:
        await _run_agent(history, msg)
    except Exception as e:
        await msg.update()
        await cl.Message(content=f"Error: {e}").send()
        return

    cl.user_session.set("history", history)


async def _run_agent(history: list, msg: cl.Message):
    # Agentic loop — keep calling until no more tool calls
    while True:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant with access to tools. "
                        "Use them whenever they would give a better answer. "
                        "Think step by step."
                    ),
                },
                *history,
            ],
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
        )

        tool_calls_acc: dict[int, dict] = {}
        full_text = ""

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # Accumulate streamed text
            if delta.content:
                full_text += delta.content
                await msg.stream_token(delta.content)

            # Accumulate tool call chunks
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_acc[idx]["id"] += tc.id
                    if tc.function and tc.function.name:
                        tool_calls_acc[idx]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls_acc[idx]["arguments"] += tc.function.arguments

        finish_reason = chunk.choices[0].finish_reason if chunk.choices else "stop"

        if finish_reason == "tool_calls" and tool_calls_acc:
            # Build assistant message with tool_calls field
            tool_calls_list = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_acc.values()
            ]
            history.append({"role": "assistant", "tool_calls": tool_calls_list})

            # Execute each tool and append results
            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])

                async with cl.Step(name=tool_name, type="tool") as step:
                    step.input = json.dumps(tool_args, indent=2)
                    result = await run_tool(tool_name, tool_args)
                    step.output = result

                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )

            # Reset streaming message for the next iteration
            msg = cl.Message(content="")
            await msg.send()

        else:
            # Final text response — done
            history.append({"role": "assistant", "content": full_text})
            await msg.update()
            break
