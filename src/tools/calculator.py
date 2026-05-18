CALCULATOR_SCHEMA = {
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
}


def calculate(expression: str) -> str:
    allowed = set("0123456789+-*/().,** %")
    if not all(c in allowed for c in expression.replace(" ", "")):
        return "Expression contains disallowed characters."
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"
