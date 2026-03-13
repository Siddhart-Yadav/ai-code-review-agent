"""
Multi-provider LLM wrapper with structured output support.

Supports four providers:
- gemini   : Google GenAI SDK (Vertex AI or API key)
- openai   : OpenAI API (GPT-4o-mini by default)
- anthropic: Anthropic API (Claude Sonnet by default)
- groq     : Groq API (Llama 3.3 70B by default, OpenAI-compatible)

Each provider implements:
- call_llm()            → raw text response
- call_llm_structured() → Pydantic-validated JSON response
"""

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
MAX_RETRIES = 2


# ── Provider: Gemini ────────────────────────────────────────────────────

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    from google import genai

    if settings.GCP_PROJECT_ID:
        _gemini_client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.GCP_REGION,
        )
        logger.info(
            "GenAI client initialized (Vertex AI): project=%s, region=%s",
            settings.GCP_PROJECT_ID,
            settings.GCP_REGION,
        )
    elif settings.GEMINI_API_KEY:
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        logger.info("GenAI client initialized (API key)")
    else:
        raise RuntimeError(
            "Gemini provider selected but neither GCP_PROJECT_ID nor GEMINI_API_KEY is set."
        )
    return _gemini_client


def _call_gemini(system_prompt: str, user_prompt: str, temperature: float) -> str:
    from google.genai import types

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=8192,
        ),
    )
    return response.text


def _call_gemini_structured(
    system_prompt: str, user_prompt: str, response_model: type[T], temperature: float
) -> T:
    from google.genai import types

    client = _get_gemini_client()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error and attempt > 0:
            prompt += (
                f"\n\n[RETRY — your previous response had a validation error: {last_error}. "
                f"Please fix and return valid JSON matching the schema exactly.]"
            )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=8192,
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )

        raw = response.text
        try:
            data = json.loads(raw)
            result = response_model.model_validate(data)
            if attempt > 0:
                logger.info("Structured output succeeded on retry %d", attempt)
            return result
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:500]
            logger.warning(
                "Structured output validation failed (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, last_error[:200],
            )

    raise ValueError(
        f"Gemini failed to produce valid {response_model.__name__} after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


# ── Provider: OpenAI ────────────────────────────────────────────────────

_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OpenAI provider selected but OPENAI_API_KEY is not set.")

    _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("OpenAI client initialized (model=%s)", settings.OPENAI_MODEL)
    return _openai_client


def _call_openai(system_prompt: str, user_prompt: str, temperature: float) -> str:
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


def _call_openai_structured(
    system_prompt: str, user_prompt: str, response_model: type[T], temperature: float
) -> T:
    client = _get_openai_client()
    schema = response_model.model_json_schema()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error and attempt > 0:
            prompt += (
                f"\n\n[RETRY — your previous response had a validation error: {last_error}. "
                f"Please fix and return valid JSON matching the schema exactly.]"
            )

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=8192,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": schema,
                },
            },
        )

        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            result = response_model.model_validate(data)
            if attempt > 0:
                logger.info("Structured output succeeded on retry %d", attempt)
            return result
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:500]
            logger.warning(
                "Structured output validation failed (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, last_error[:200],
            )

    raise ValueError(
        f"OpenAI failed to produce valid {response_model.__name__} after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


# ── Provider: Anthropic ─────────────────────────────────────────────────

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client

    import anthropic

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic provider selected but ANTHROPIC_API_KEY is not set.")

    _anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    logger.info("Anthropic client initialized (model=%s)", settings.ANTHROPIC_MODEL)
    return _anthropic_client


def _call_anthropic(system_prompt: str, user_prompt: str, temperature: float) -> str:
    client = _get_anthropic_client()
    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        temperature=temperature,
        max_tokens=8192,
    )
    return response.content[0].text


def _call_anthropic_structured(
    system_prompt: str, user_prompt: str, response_model: type[T], temperature: float
) -> T:
    client = _get_anthropic_client()
    schema = response_model.model_json_schema()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error and attempt > 0:
            prompt += (
                f"\n\n[RETRY — your previous response had a validation error: {last_error}. "
                f"Please fix and return valid JSON matching the schema exactly.]"
            )

        # Use Anthropic's tool_use for structured output
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=8192,
            tools=[
                {
                    "name": response_model.__name__,
                    "description": f"Return the analysis as a structured {response_model.__name__} object.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": response_model.__name__},
        )

        # Extract tool_use block
        tool_input = None
        for block in response.content:
            if block.type == "tool_use":
                tool_input = block.input
                break

        if tool_input is None:
            last_error = "No tool_use block in response"
            logger.warning("Anthropic returned no tool_use block (attempt %d)", attempt + 1)
            continue

        try:
            result = response_model.model_validate(tool_input)
            if attempt > 0:
                logger.info("Structured output succeeded on retry %d", attempt)
            return result
        except ValidationError as e:
            last_error = str(e)[:500]
            logger.warning(
                "Structured output validation failed (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, last_error[:200],
            )

    raise ValueError(
        f"Anthropic failed to produce valid {response_model.__name__} after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


# ── Provider: Groq (OpenAI-compatible, free tier with Llama 3.3 70B) ──

_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client

    from openai import OpenAI

    if not settings.GROQ_API_KEY:
        raise RuntimeError("Groq provider selected but GROQ_API_KEY is not set.")

    _groq_client = OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    logger.info("Groq client initialized (model=%s)", settings.GROQ_MODEL)
    return _groq_client


def _call_groq(system_prompt: str, user_prompt: str, temperature: float) -> str:
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


def _call_groq_structured(
    system_prompt: str, user_prompt: str, response_model: type[T], temperature: float
) -> T:
    client = _get_groq_client()
    schema = response_model.model_json_schema()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error and attempt > 0:
            prompt += (
                f"\n\n[RETRY — your previous response had a validation error: {last_error}. "
                f"Please fix and return valid JSON matching the schema exactly.]"
            )

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            result = response_model.model_validate(data)
            if attempt > 0:
                logger.info("Structured output succeeded on retry %d", attempt)
            return result
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:500]
            logger.warning(
                "Structured output validation failed (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, last_error[:200],
            )

    raise ValueError(
        f"Groq failed to produce valid {response_model.__name__} after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


# ── Provider: OpenRouter (free Llama 3.3 70B, OpenAI-compatible) ──────

_openrouter_client = None


def _get_openrouter_client():
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client

    from openai import OpenAI

    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError("OpenRouter provider selected but OPENROUTER_API_KEY is not set.")

    _openrouter_client = OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    logger.info("OpenRouter client initialized (model=%s)", settings.OPENROUTER_MODEL)
    return _openrouter_client


def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float) -> str:
    client = _get_openrouter_client()
    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


def _call_openrouter_structured(
    system_prompt: str, user_prompt: str, response_model: type[T], temperature: float
) -> T:
    client = _get_openrouter_client()
    schema = response_model.model_json_schema()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error and attempt > 0:
            prompt += (
                f"\n\n[RETRY — your previous response had a validation error: {last_error}. "
                f"Please fix and return valid JSON matching the schema exactly.]"
            )

        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            result = response_model.model_validate(data)
            if attempt > 0:
                logger.info("Structured output succeeded on retry %d", attempt)
            return result
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:500]
            logger.warning(
                "Structured output validation failed (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, last_error[:200],
            )

    raise ValueError(
        f"OpenRouter failed to produce valid {response_model.__name__} after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


# ── Unified API ─────────────────────────────────────────────────────────

_PROVIDERS = {
    "gemini": (_call_gemini, _call_gemini_structured),
    "openai": (_call_openai, _call_openai_structured),
    "anthropic": (_call_anthropic, _call_anthropic_structured),
    "groq": (_call_groq, _call_groq_structured),
    "openrouter": (_call_openrouter, _call_openrouter_structured),
}


def _get_provider():
    provider = settings.LLM_PROVIDER.lower()
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Choose from: {', '.join(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider]


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """Call the configured LLM provider and return raw text response."""
    call_fn, _ = _get_provider()
    return call_fn(system_prompt, user_prompt, temperature)


def call_llm_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
    temperature: float = 0.1,
) -> T:
    """
    Call the configured LLM provider with structured output enforcement.

    Each provider uses its native structured output mechanism:
    - Gemini: response_schema
    - OpenAI: json_schema response_format
    - Anthropic: tool_use with forced tool choice
    """
    _, call_structured_fn = _get_provider()
    return call_structured_fn(system_prompt, user_prompt, response_model, temperature)
