from dotenv import load_dotenv

load_dotenv()

import chainlit as cl

from src.agent import run_agent
from src.sandbox import create_sandbox, destroy_sandbox


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await create_sandbox()
    await cl.Message(
        content=(
            "Hello! I'm your AI agent. I have access to these tools:\n\n"
            "- **run_code** — execute Python or shell in an isolated sandbox (state persists per conversation)\n"
            "- **get_weather** — current weather for any city\n"
            "- **calculate** — evaluate math expressions\n"
            "- **web_search** — search the web\n\n"
            "Ask me anything!"
        )
    ).send()


@cl.on_chat_end
async def on_chat_end():
    await destroy_sandbox()


@cl.on_message
async def on_message(message: cl.Message):
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    try:
        await run_agent(history)
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()
    cl.user_session.set("history", history)
