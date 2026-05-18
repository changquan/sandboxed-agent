from src.sandbox import get_sandbox

CODE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_code",
        "description": (
            "Execute code in a secure isolated sandbox. Use for data analysis, "
            "calculations, file generation, or any task needing actual code. "
            "State (variables, imports, files) persists across calls in the same conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to execute.",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "shell"],
                    "description": "'python' (default) runs Python 3.11. 'shell' runs bash commands.",
                },
            },
            "required": ["code"],
        },
    },
}


async def run_code(code: str, language: str = "python") -> str:
    sbx = get_sandbox()
    if sbx is None:
        return "Code interpreter sandbox is not available for this session."
    lang = "bash" if language in ("shell", "bash", "sh") else "python"
    try:
        execution = await sbx.run_code(code, language=lang)
    except Exception as e:
        return f"Sandbox error: {e}"

    parts = []
    if execution.logs.stdout:
        parts.append("stdout:\n" + "\n".join(execution.logs.stdout))
    if execution.logs.stderr:
        parts.append("stderr:\n" + "\n".join(execution.logs.stderr))
    if execution.text:
        parts.append("result:\n" + execution.text)
    if execution.error:
        parts.append(
            f"error ({execution.error.name}): {execution.error.value}\n"
            f"{execution.error.traceback}"
        )
    return "\n\n".join(parts) or "(no output)"
