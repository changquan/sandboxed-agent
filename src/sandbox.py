import os

import chainlit as cl
from e2b_code_interpreter import AsyncSandbox

SANDBOX_TIMEOUT = 600  # 10 minutes; auto-expires server-side if on_chat_end is missed
_E2B_API_KEY = os.environ.get("E2B_API_KEY")


async def create_sandbox() -> None:
    """Create a persistent e2b sandbox for this session, stored in cl.user_session."""
    if not _E2B_API_KEY:
        cl.user_session.set("sandbox", None)
        await cl.Message(
            content="⚠️ E2B_API_KEY is not set. Code interpreter is disabled."
        ).send()
        return
    try:
        sbx = await AsyncSandbox.create(api_key=_E2B_API_KEY, timeout=SANDBOX_TIMEOUT)
        cl.user_session.set("sandbox", sbx)
    except Exception as e:
        cl.user_session.set("sandbox", None)
        await cl.Message(
            content=f"⚠️ Code interpreter unavailable: {e}\nOther tools still work."
        ).send()


async def destroy_sandbox() -> None:
    """Kill the e2b sandbox at end of session."""
    sbx = cl.user_session.get("sandbox")
    if sbx is not None:
        try:
            await sbx.kill()
        except Exception:
            pass


def get_sandbox():
    """Return the active sandbox for the current session, or None."""
    return cl.user_session.get("sandbox")
