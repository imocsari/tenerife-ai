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
