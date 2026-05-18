import json

import chainlit as cl
from openai import AsyncOpenAI

from src.tools import TOOLS, run_tool

client = AsyncOpenAI()

SYSTEM = (
    "You are a helpful assistant with access to tools including a Python code interpreter. "
    "Use run_code for data analysis, calculations, plotting, or anything that benefits from "
    "running real code. State (variables, imports, files) persists across run_code calls "
    "within the same conversation."
)


async def run_agent(history: list) -> None:
    """Stream one full agentic turn (may involve multiple tool calls), mutating history in place."""
    msg = cl.Message(content="")
    await msg.send()

    while True:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM}, *history],
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
        )

        tool_calls_acc: dict[int, dict] = {}
        full_text = ""
        finish_reason = "stop"

        async for chunk in response:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta.content:
                full_text += delta.content
                await msg.stream_token(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_acc[idx]["id"] += tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if finish_reason == "tool_calls" and tool_calls_acc:
            tool_calls_list = [
                {
                    "id": t["id"],
                    "type": "function",
                    "function": {"name": t["name"], "arguments": t["arguments"]},
                }
                for t in tool_calls_acc.values()
            ]
            history.append({"role": "assistant", "tool_calls": tool_calls_list})

            for tc in tool_calls_list:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                async with cl.Step(name=name, type="tool") as step:
                    step.input = json.dumps(args, indent=2)
                    result = await run_tool(name, args)
                    step.output = result
                history.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result}
                )

            msg = cl.Message(content="")
            await msg.send()
        else:
            history.append({"role": "assistant", "content": full_text})
            await msg.update()
            break
