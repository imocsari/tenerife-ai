# app/llm.py
# The ONLY place that talks to a language model.
# To add another provider (e.g. OpenAI), add one function and one line in generate().

from app import config


def _claude(system, message):
    from anthropic import Anthropic
    response = Anthropic().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text


def _ollama(system, message):
    import ollama
    response = ollama.chat(
        model=config.OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
    )
    return response["message"]["content"]


PROVIDERS = {"claude": _claude, "ollama": _ollama}


def generate(system, message):
    try:
        provider = PROVIDERS[config.LLM_PROVIDER]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER!r}")
    return provider(system, message)


# ---------------------------------------------------------------------------
# Tool calling (2026-10-14)
# ---------------------------------------------------------------------------
# The agentic loop: the model asks for a tool, we run it, hand back the result, repeat until
# it answers in words. Written once per provider because the envelopes differ — Claude uses
# tool_use/tool_result content blocks, Ollama uses OpenAI-style tool_calls and a "tool" role —
# while the tool schemas themselves are shared (see app/tools/__init__.py).

MAX_TOOL_ROUNDS = 6   # a wrong-footed model can loop; this bounds the damage and the bill


def _claude_tools(system, question):
    from anthropic import Anthropic
    from app import tools

    client = Anthropic()
    messages = [{"role": "user", "content": question}]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system,
            tools=tools.anthropic_schemas(),
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # Every tool_result for this turn goes back in ONE user message: splitting them
        # teaches the model to stop asking for tools in parallel.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(tools.run(block.name, block.input)),
                })
        messages.append({"role": "user", "content": results})

    return "I kept needing more information and ran out of steps before answering."


def _ollama_tools(system, question):
    import ollama
    from app import tools

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=messages,
            tools=tools.ollama_schemas(),
        )
        message = response.message
        calls = message.tool_calls or []
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            **({"tool_calls": [c.model_dump() for c in calls]} if calls else {}),
        })

        if not calls:
            return message.content or ""

        for call in calls:
            output = tools.run(call.function.name, dict(call.function.arguments or {}))
            messages.append({
                "role": "tool",
                "tool_name": call.function.name,
                "content": str(output),
            })

    return "I kept needing more information and ran out of steps before answering."


TOOL_PROVIDERS = {"claude": _claude_tools, "ollama": _ollama_tools}


def generate_with_tools(system, question):
    """Answer a question, letting the model call tools as it goes."""
    try:
        provider = TOOL_PROVIDERS[config.LLM_PROVIDER]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER!r}")
    return provider(system, question)
