"""
LLM Client — Unified interface for calling either Anthropic API or local Ollama.

Toggle via LLM_PROVIDER env var:
  "anthropic" → Claude API (default for testing)
  "ollama"    → Local Ollama instance (for production)
"""

import logging

import httpx

from backend.config import LLMConfig

logger = logging.getLogger(__name__)


async def call_llm(
    config: LLMConfig,
    prompt: str,
    *,
    role: str = "reasoning",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Call the configured LLM provider and return the response text.

    Args:
        config: LLM configuration with provider, keys, endpoints.
        prompt: The user prompt to send.
        role: "reasoning" (intent parsing, formatting) or "sql" (SQL generation).
              Only affects model selection in Ollama mode.
        temperature: Override config temperature. Use 0.0 for SQL generation.
        max_tokens: Override config max_tokens.

    Returns:
        The LLM response text content.
    """
    temp = temperature if temperature is not None else config.temperature
    tokens = max_tokens if max_tokens is not None else config.max_tokens

    if config.provider == "anthropic":
        return await _call_anthropic(config, prompt, temp, tokens)
    else:
        return await _call_ollama(config, prompt, role, temp, tokens)


async def _call_anthropic(
    config: LLMConfig,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Claude via the Anthropic Messages API."""
    async with httpx.AsyncClient(timeout=config.request_timeout) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.anthropic_model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


async def _call_ollama(
    config: LLMConfig,
    prompt: str,
    role: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call a local LLM via Ollama-compatible API."""
    if role == "sql":
        endpoint = config.sql_endpoint
        model = config.sql_model
    else:
        endpoint = config.reasoning_endpoint
        model = config.reasoning_model

    async with httpx.AsyncClient(timeout=config.request_timeout) as client:
        response = await client.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
