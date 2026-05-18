from collections import deque

import chainlit as cl
from agents import Runner, function_tool
from agents.run import RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from openai.types.responses import ResponseTextDeltaEvent

from src.sandbox import get_sandbox_session
from src.tools.weather import get_weather as _get_weather
from src.tools.calculator import calculate as _calculate
from src.tools.search import web_search as _web_search


@function_tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return await _get_weather(city)


@function_tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    return _calculate(expression)


@function_tool
async def web_search(query: str) -> str:
    """Search the web for up-to-date information on a topic."""
    return await _web_search(query)


AGENT = SandboxAgent(
    name="AI Assistant",
    model="gpt-4o-mini",
    instructions=(
        "You are a helpful assistant with shell access to a secure e2b sandbox. "
        "Use exec_command to run Python scripts or shell commands for code execution, data analysis, or calculations. "
        "You also have get_weather, calculate, and web_search tools."
    ),
    tools=[get_weather, calculate, web_search],
    capabilities=[Shell()],
)


async def run_agent(input_list: list) -> list:
    """Stream one agentic turn and return the updated input list."""
    msg = cl.Message(content="")
    await msg.send()

    session = get_sandbox_session()
    run_config = RunConfig(
        sandbox=SandboxRunConfig(session=session) if session else None
    )

    result = Runner.run_streamed(AGENT, input=input_list, run_config=run_config)
    active_steps: deque[cl.Step] = deque()

    async for event in result.stream_events():
        if event.type == "raw_response_event":
            if isinstance(event.data, ResponseTextDeltaEvent):
                await msg.stream_token(event.data.delta)

        elif event.type == "run_item_stream_event":
            if event.name == "tool_called":
                step = cl.Step(name=event.item.raw_item.name, type="tool")
                step.input = event.item.raw_item.arguments
                await step.send()
                active_steps.append(step)

            elif event.name == "tool_output":
                if active_steps:
                    step = active_steps.popleft()
                    step.output = str(event.item.output)
                    await step.update()

    await msg.update()
    return result.to_input_list()
