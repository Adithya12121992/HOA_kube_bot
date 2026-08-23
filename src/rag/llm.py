"""Generic environment-aware text generation, shared by summarize.py and
the chat query engine.

Routes to whichever LLM the active environment bundle points at (see
src/config/settings.py):
  - local: LM Studio (OpenAI-compatible local server)
  - cloud: providers in CLOUD_LLM_FALLBACK_ORDER, in order

Every call is wrapped so failure (missing key, connection refused, timeout,
non-2xx response, empty content) returns None rather than raising — callers
decide what "no LLM available" means for their feature (e.g. summarize.py
treats it as "skip the summary"; the chat query engine treats it as
"return an error to the user").
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from src.config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CLOUD_LLM_FALLBACK_ORDER,
    LM_STUDIO_API_KEY,
    LM_STUDIO_BASE_URL,
    LM_STUDIO_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    get_environment,
)

logger = logging.getLogger(__name__)

# Local reasoning models (e.g. Qwen3) spend most of max_tokens on internal
# "reasoning_content" before writing the real answer to "content" — verified
# against a real LM Studio instance running qwen/qwen3-14b: with a low
# max_tokens budget, generation hit the limit before writing any real
# content at all, returning an empty string. The timeout floor (3 min) and
# generous token budget below account for that; cloud providers (not
# reasoning models by default) don't need nearly this much but the same
# budget doesn't hurt them.
LOCAL_TIMEOUT_SECONDS = 240
CLOUD_TIMEOUT_SECONDS = 30


def generate(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> Optional[str]:
    """Generate text from whichever LLM the active environment points at.

    Returns None if no LLM is reachable/configured — never raises.
    """
    if get_environment() == "local":
        return _try_lm_studio(prompt, max_tokens, temperature)

    for provider in CLOUD_LLM_FALLBACK_ORDER:
        result = _try_cloud_provider(provider, prompt, max_tokens, temperature)
        if result:
            return result
    return None


def _try_lm_studio(prompt: str, max_tokens: int, temperature: float) -> Optional[str]:
    headers = {}
    if LM_STUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_API_KEY}"
    try:
        resp = requests.post(
            f"{LM_STUDIO_BASE_URL}/chat/completions",
            headers=headers,
            json={
                "model": LM_STUDIO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=LOCAL_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"LM Studio generation failed: {e}")
        return None


def _try_cloud_provider(provider: str, prompt: str, max_tokens: int, temperature: float) -> Optional[str]:
    if provider == "anthropic":
        return _try_anthropic(prompt, max_tokens)
    if provider == "openai":
        return _try_openai(prompt, max_tokens, temperature)
    logger.warning(f"Unknown cloud LLM provider in CLOUD_LLM_FALLBACK_ORDER: {provider!r}")
    return None


def _try_anthropic(prompt: str, max_tokens: int) -> Optional[str]:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=CLOUD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"Anthropic generation failed, trying next provider: {e}")
        return None


def _try_openai(prompt: str, max_tokens: int, temperature: float) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=CLOUD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"OpenAI generation failed: {e}")
        return None
