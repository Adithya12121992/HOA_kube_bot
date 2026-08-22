"""Best-effort 2-line document summary, generated via whichever LLM the
active environment bundle points at (see src/config/settings.py):
  - local: LM Studio (OpenAI-compatible local server)
  - cloud: Anthropic, falling back to OpenAI on failure

Every call is wrapped so failure (missing key, connection refused, timeout,
non-2xx response) returns None rather than raising: per PLAN.md Step 2.4's
design, a missing summary must never block marking a document "ready" for
search.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from src.config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CLOUD_LLM_FALLBACK_ORDER,
    ENVIRONMENT,
    LM_STUDIO_API_KEY,
    LM_STUDIO_BASE_URL,
    LM_STUDIO_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)

# Local reasoning models (e.g. Qwen3) spend most of max_tokens on internal
# "reasoning_content" before writing the real answer to "content" - verified
# against a real LM Studio instance running qwen/qwen3-14b: with
# max_tokens=150, 199 completion tokens were used (179 on reasoning), and
# "content" came back as an empty string because generation hit the token
# limit before writing any real answer. 3 minutes / higher token budget
# accounts for that; cloud providers (non-reasoning by default) don't need
# nearly this much but the same budget doesn't hurt them.
LOCAL_TIMEOUT_SECONDS = 240  # floor requested: 3 min; padded higher for slower local hardware/larger models
CLOUD_TIMEOUT_SECONDS = 30
LOCAL_MAX_TOKENS = 800
CLOUD_MAX_TOKENS = 150
MAX_SOURCE_CHARS = 2000  # first ~2000 chars of the doc's text is enough context for a 2-line summary

_PROMPT_TEMPLATE = (
    "Summarize this {doc_type} document in exactly 2 lines. "
    "Be concise and specific about what it covers.\n\n{text}"
)


def summarize_document(doc_type: str, full_text: str) -> Optional[str]:
    """Generate a 2-line summary, or None if no LLM is reachable/configured."""
    text_sample = full_text[:MAX_SOURCE_CHARS]
    prompt = _PROMPT_TEMPLATE.format(doc_type=doc_type or "HOA", text=text_sample)

    if ENVIRONMENT == "local":
        return _try_lm_studio(prompt)

    for provider in CLOUD_LLM_FALLBACK_ORDER:
        result = _try_cloud_provider(provider, prompt)
        if result:
            return result
    return None


def _try_lm_studio(prompt: str) -> Optional[str]:
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
                "max_tokens": LOCAL_MAX_TOKENS,
                "temperature": 0.3,
            },
            timeout=LOCAL_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"LM Studio summarization failed, skipping summary: {e}")
        return None


def _try_cloud_provider(provider: str, prompt: str) -> Optional[str]:
    if provider == "anthropic":
        return _try_anthropic(prompt)
    if provider == "openai":
        return _try_openai(prompt)
    logger.warning(f"Unknown cloud LLM provider in CLOUD_LLM_FALLBACK_ORDER: {provider!r}")
    return None


def _try_anthropic(prompt: str) -> Optional[str]:
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
                "max_tokens": CLOUD_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=CLOUD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"Anthropic summarization failed, trying next provider: {e}")
        return None


def _try_openai(prompt: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": CLOUD_MAX_TOKENS,
                "temperature": 0.3,
            },
            timeout=CLOUD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        logger.warning(f"OpenAI summarization failed, skipping summary: {e}")
        return None
