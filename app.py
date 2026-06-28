from dotenv import load_dotenv

load_dotenv()

import chainlit as cl

from src.agent import run_agent
from src.sandbox import create_sandbox, destroy_sandbox


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("input_list", [])
    cl.user_session.set("uploaded_files", {})
    await create_sandbox()
    await cl.Message(
        content=(
            "Hello! I'm your AI agent. I have access to these tools:\n\n"
            "- **shell** — execute Python or shell commands in a secure e2b sandbox (state persists per conversation)\n"
            "- **get_weather** — current weather for any city\n"
            "- **calculate** — evaluate math expressions\n"
            "- **web_search** — search the web\n"
            "- **compliance check** — upload a broker statement (Excel, PDF, or image) and a pre-clearance Excel "
            "to check for trading discrepancies\n\n"
            "Ask me anything!"
        )
    ).send()


@cl.on_chat_end
async def on_chat_end():
    await destroy_sandbox()


@cl.on_message
async def on_message(message: cl.Message):
    input_list: list = cl.user_session.get("input_list")
    uploaded_files: dict = cl.user_session.get("uploaded_files", {})

    new_files = {}
    for element in message.elements:
        if hasattr(element, "path") and element.path:
            new_files[element.name] = element.path

    if new_files:
        uploaded_files.update(new_files)
        cl.user_session.set("uploaded_files", uploaded_files)

    content = message.content or ""
    if new_files:
        names = ", ".join(new_files.keys())
        content = f"{content}\n\n[Uploaded files this message: {names}]".strip()

    input_list = input_list + [{"role": "user", "content": content}]
    try:
        input_list = await run_agent(input_list)
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()
    cl.user_session.set("input_list", input_list)
