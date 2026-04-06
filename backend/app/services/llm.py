import json as _json
import logging
import re
from contextvars import ContextVar
from typing import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Runtime provider override (set per-request, reset after pipeline)
_provider_override: ContextVar[str | None] = ContextVar("llm_provider", default=None)


def set_llm_provider(provider: str | None) -> None:
    _provider_override.set(provider)


def _active_provider() -> str:
    override = _provider_override.get()
    return override or get_settings().llm_provider


def _is_ollama() -> bool:
    return _active_provider() == "ollama"


def _active_model() -> str:
    s = get_settings()
    return s.ollama_model if _is_ollama() else s.qwen_model


def _active_base_url() -> str:
    s = get_settings()
    return s.ollama_base_url if _is_ollama() else s.qwen_base_url


def _active_api_key() -> str:
    s = get_settings()
    return "ollama" if _is_ollama() else s.qwen_api_key


def _build_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )


_clients: dict[str, AsyncOpenAI] = {}


def _get_client_for_provider() -> AsyncOpenAI:
    """Get or create an OpenAI-compatible client for the active provider."""
    provider = _active_provider()
    if provider not in _clients:
        _clients[provider] = AsyncOpenAI(
            base_url=_active_base_url(),
            api_key=_active_api_key(),
        )
    return _clients[provider]


def get_llm_client() -> AsyncOpenAI:
    return _get_client_for_provider()


def reset_llm_client() -> None:
    _clients.clear()


def _ollama_base() -> str:
    """Return the bare Ollama host URL (without /v1)."""
    return get_settings().ollama_base_url.replace("/v1", "")


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from text."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── Ollama native API (most reliable for thinking models) ──────────

async def chat_ollama(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
    think: bool | None = None,
) -> str:
    settings = get_settings()
    model = model or settings.ollama_model

    payload: dict = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if think is not None:
        payload["think"] = think

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{_ollama_base()}/api/chat", json=payload)
        resp.raise_for_status()

    data = resp.json()
    msg = data.get("message", {})
    raw_content = msg.get("content", "")
    raw_thinking = msg.get("thinking", "")

    logger.info(
        "chat_ollama response (think=%s) — content: %d chars, thinking: %d chars",
        think, len(raw_content), len(raw_thinking),
    )

    text = strip_thinking_tags(raw_content)

    if not text and raw_thinking:
        logger.info("chat_ollama: content empty, extracting from thinking field")
        text = strip_thinking_tags(raw_thinking)
        if not text:
            text = raw_thinking

    return text


def _extract_chunk_text(chunk: dict) -> str:
    msg = chunk.get("message", {})
    return msg.get("content", "") or msg.get("thinking", "") or ""


async def stream_ollama(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    model = model or settings.ollama_model

    payload = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    inside_think = False
    seen_content = False

    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("POST", f"{_ollama_base()}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = _json.loads(line)
                except _json.JSONDecodeError:
                    continue

                msg = data.get("message", {})
                content = msg.get("content", "")
                thinking = msg.get("thinking", "")

                if thinking and not content:
                    continue
                if content:
                    seen_content = True

                text = content
                if not text:
                    continue

                while text:
                    if inside_think:
                        end_idx = text.find("</think>")
                        if end_idx != -1:
                            inside_think = False
                            text = text[end_idx + len("</think>"):]
                        else:
                            text = ""
                    else:
                        start_idx = text.find("<think>")
                        if start_idx != -1:
                            before = text[:start_idx]
                            if before:
                                yield before
                            inside_think = True
                            text = text[start_idx + len("<think>"):]
                        else:
                            yield text
                            text = ""

    if not seen_content:
        logger.warning("stream_ollama: no content tokens received — model uses thinking-only mode")


async def stream_ollama_with_thinking(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    model = model or settings.ollama_model

    payload = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("POST", f"{_ollama_base()}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                msg = data.get("message", {})
                content = msg.get("content", "")
                thinking = msg.get("thinking", "")
                if content:
                    yield content
                elif thinking:
                    yield thinking


# ── Provider-agnostic wrappers ─────────────────────────────────────

async def stream_chat(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
    filter_thinking: bool = False,
) -> AsyncGenerator[str, None]:
    if _is_ollama():
        async for chunk in stream_ollama(
            messages, temperature=temperature,
            max_tokens=max_tokens, model=model,
        ):
            yield chunk
        return

    client = get_llm_client()
    model = model or _active_model()

    extra_body = {}
    if filter_thinking:
        extra_body["enable_thinking"] = False

    response = await client.chat.completions.create(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens, stream=True,
        extra_body=extra_body if extra_body else None,
    )

    inside_think = False
    async for chunk in response:
        choice = chunk.choices[0] if chunk.choices else None
        if choice is None:
            continue
        text = choice.delta.content or ""
        if not text:
            continue

        if not filter_thinking:
            yield text
            continue

        # Token-by-token <think> tag filtering for cloud thinking models
        while text:
            if inside_think:
                end_idx = text.find("</think>")
                if end_idx != -1:
                    inside_think = False
                    text = text[end_idx + len("</think>"):]
                else:
                    text = ""
            else:
                start_idx = text.find("<think>")
                if start_idx != -1:
                    before = text[:start_idx]
                    if before:
                        yield before
                    inside_think = True
                    text = text[start_idx + len("<think>"):]
                else:
                    yield text
                    text = ""


async def chat(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
    think: bool | None = None,
) -> str:
    if _is_ollama():
        return await chat_ollama(messages, temperature=temperature,
                                 max_tokens=max_tokens, model=model,
                                 think=think)

    client = get_llm_client()
    model = model or _active_model()

    extra_body = {}
    if think is False:
        extra_body["enable_thinking"] = False

    resp = await client.chat.completions.create(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens, stream=False,
        extra_body=extra_body if extra_body else None,
    )
    msg = resp.choices[0].message
    raw = (msg.content or "").strip()
    return strip_thinking_tags(raw)


async def unload_model() -> None:
    """Tell Ollama to unload the model from VRAM immediately."""
    if not _is_ollama():
        return

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{_ollama_base()}/api/generate",
                json={"model": settings.ollama_model, "keep_alive": 0},
            )
        logger.info("Ollama model unloaded — VRAM released")
    except Exception as e:
        logger.warning("Failed to unload Ollama model: %s", e)


async def check_connectivity() -> bool:
    """Quick connectivity / model availability test."""
    try:
        if _is_ollama():
            text = await chat_ollama(
                [{"role": "user", "content": "Say OK"}],
                max_tokens=16, think=False,
            )
            return bool(text)
        client = get_llm_client()
        resp = await client.chat.completions.create(
            model=_active_model(),
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=16,
        )
        return bool(resp.choices)
    except Exception as e:
        logger.warning("LLM connectivity check failed: %s", e)
        return False
