# app/tools/__init__.py
# The tool registry: one neutral description per tool, converted to whichever shape the
# provider wants. Claude and Ollama disagree on the envelope but agree on JSON Schema,
# so the schema is written once here and translated, rather than maintained twice.

from app.tools import (air_quality, buses, currency, fuel, geocode, health, holidays,
                       knowledge, marine, places_nearby, stargazing, weather, wiki)

# name -> {"description", "parameters" (JSON Schema), "run" (callable)}
REGISTRY = {
    **knowledge.TOOLS,
    **geocode.TOOLS,
    **weather.TOOLS,
    **marine.TOOLS,
    **air_quality.TOOLS,
    **holidays.TOOLS,
    **buses.TOOLS,
    **currency.TOOLS,
    **fuel.TOOLS,
    **health.TOOLS,
    **places_nearby.TOOLS,
    **stargazing.TOOLS,
    **wiki.TOOLS,
}


def anthropic_schemas():
    """Claude's shape: {name, description, input_schema}."""
    return [
        {"name": name, "description": t["description"], "input_schema": t["parameters"]}
        for name, t in REGISTRY.items()
    ]


def ollama_schemas():
    """Ollama's shape (OpenAI-style): {type, function: {name, description, parameters}}."""
    return [
        {"type": "function", "function": {
            "name": name, "description": t["description"], "parameters": t["parameters"],
        }}
        for name, t in REGISTRY.items()
    ]


def run(name, arguments):
    """Execute a tool by name. Never raises: a failed tool must come back to the model as
    text it can reason about, not as an exception that kills the whole answer.

    Failures are also logged. Without that they were invisible: the model received the error,
    wrote a polite "try again in a moment", and nothing anywhere recorded why — which is how a
    production weather tool could fail every single time and look like a transient hiccup.
    """
    tool = REGISTRY.get(name)
    if tool is None:
        print(f"[tool] {name}: no such tool", flush=True)
        return f"No such tool: {name}. Available: {', '.join(REGISTRY)}"
    try:
        return tool["run"](**(arguments or {}))
    except TypeError as e:
        print(f"[tool] {name} bad arguments {arguments!r}: {e}", flush=True)
        return f"Wrong arguments for {name}: {e}"
    except Exception as e:
        print(f"[tool] {name} failed: {type(e).__name__}: {e}", flush=True)
        return f"{name} failed: {type(e).__name__}: {e}"
