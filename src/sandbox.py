import chainlit as cl
from agents.extensions.sandbox import E2BSandboxClient, E2BSandboxClientOptions, E2BSandboxType

_client = E2BSandboxClient()


async def create_sandbox() -> None:
    try:
        session = await _client.create(
            options=E2BSandboxClientOptions(
                sandbox_type=E2BSandboxType.E2B,
                timeout=600,
                pause_on_exit=True,
            )
        )
        cl.user_session.set("sandbox_session", session)
    except Exception as e:
        cl.user_session.set("sandbox_session", None)
        await cl.Message(
            content=f"⚠️ Code sandbox unavailable: {e}\nOther tools still work."
        ).send()


async def destroy_sandbox() -> None:
    session = cl.user_session.get("sandbox_session")
    if session is not None:
        try:
            await session.shutdown()
        except Exception:
            pass


def get_sandbox_session():
    return cl.user_session.get("sandbox_session")
