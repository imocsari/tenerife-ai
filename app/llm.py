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

# How many previous turns to carry. Enough for "near Los Cristianos" to still mean football,
# not so many that an hour-old conversation is re-sent (and re-billed) on every question.
# Only the text turns are kept, never the tool calls and their results: those are large,
# already summarised in the answer the model gave, and replaying them teaches it to repeat
# tool calls it has already made.
MAX_HISTORY_TURNS = 8


def _as_turns(history):
    """[{role, content}] -> the last few clean user/assistant turns."""
    turns = [
        {"role": h["role"], "content": h["content"]}
        for h in (history or [])
        if h.get("role") in ("user", "assistant") and (h.get("content") or "").strip()
    ]
    return turns[-MAX_HISTORY_TURNS:]


def _claude_tools(system, question, history=None):
    from anthropic import Anthropic
    from app import tools

    client = Anthropic()
    messages = _as_turns(history) + [{"role": "user", "content": question}]

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


def _ollama_tools(system, question, history=None):
    import ollama
    from app import tools

    messages = [{"role": "system", "content": system}]
    messages += _as_turns(history)
    messages.append({"role": "user", "content": question})

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


def generate_with_tools(system, question, history=None):
    """Answer a question in the context of the conversation so far, calling tools as needed."""
    try:
        provider = TOOL_PROVIDERS[config.LLM_PROVIDER]
    except KeyError:
        raise ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER!r}")
    return provider(system, question, history)
