"""Model gateway: provider-agnostic LLM access with honest degradation.

Design invariants (Directive 62/78, ADR-002 honesty):
- No credentials configured  -> ModelUnavailableError; callers fall back to
  deterministic mode. The system NEVER pretends an LLM was consulted.
- Every call returns cost/latency/token accounting for Cost Intelligence.
- Structured outputs are enforced by decoding against Pydantic contracts with
  one repair retry; failure raises DecodeError (caller decides fallback).
- ScriptedModel is a TEST DOUBLE (like SimulatedDataFetcher) - it must never
  be wired into production composition roots.
"""

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from core.config import Settings

logger = logging.getLogger(__name__)


class ModelUnavailableError(RuntimeError):
    """No usable model backend for this request."""


class GatewayHTTPError(RuntimeError):
    """Provider returned an error after retries."""


class DecodeError(RuntimeError):
    """Model output could not be decoded into the required contract."""


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ModelRequest(BaseModel):
    messages: list[ChatMessage]
    model_hint: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1200
    metadata: dict[str, str] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


def estimate_cost_usd(settings: Settings, prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1_000_000 * settings.cost_usd_per_mtok_input
        + completion_tokens / 1_000_000 * settings.cost_usd_per_mtok_output,
        8,
    )


class BaseModelGateway(ABC):
    """Abstract chat-model boundary."""

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute one chat completion."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider identifier for audit records."""


class OpenAICompatibleGateway(BaseModelGateway):
    """Async OpenAI-compatible /chat/completions adapter (httpx).

    Works with OpenAI and any compatible endpoint configured via
    Settings.openai_base_url (DeepSeek, Together, local vLLM, OpenRouter...).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model: str,
        settings: Settings,
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ModelUnavailableError("OpenAI-compatible gateway requires an API key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._settings = settings
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        # FIX 2: one shared client — avoids TLS handshake per request.
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def provider(self) -> str:
        return "openai_compatible"

    def _model_for(self, request: ModelRequest) -> str:
        return request.model_hint or self._default_model

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self._model_for(request),
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                resp = await asyncio.wait_for(
                    self._client.post(url, json=payload, headers=headers),
                    timeout=self._timeout + 5,
                )
                if resp.status_code in (429, 500, 502, 503):
                    raise GatewayHTTPError(f"provider status {resp.status_code}")
                resp.raise_for_status()
                raw = await asyncio.wait_for(resp.aread(), timeout=5)
                body = json.loads(raw)
                usage = body.get("usage", {}) or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                return ModelResponse(
                    content=body["choices"][0]["message"]["content"],
                    model=body.get("model", payload["model"]),
                    provider=self.provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=estimate_cost_usd(self._settings, prompt_tokens, completion_tokens),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (httpx.HTTPError, GatewayHTTPError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning("gateway attempt %d/%d failed: %s", attempt, self._max_attempts, exc)
                if attempt < self._max_attempts:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))  # 0.5s, 1s, ...
        raise GatewayHTTPError(f"all {self._max_attempts} attempts failed: {last_error}")


class AnthropicGateway(BaseModelGateway):
    """Anthropic Messages API adapter (httpx)."""

    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        default_model: str,
        settings: Settings,
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ModelUnavailableError("Anthropic gateway requires an API key")
        self._api_key = api_key
        self._default_model = default_model
        self._settings = settings
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def provider(self) -> str:
        return "anthropic"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        system_text = "\n".join(m.content for m in request.messages if m.role == "system")
        rest = [m for m in request.messages if m.role != "system"]
        payload: dict[str, Any] = {
            "model": request.model_hint or self._default_model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in rest],
        }
        if system_text:
            payload["system"] = system_text
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                resp = await asyncio.wait_for(
                    self._client.post(
                        "https://api.anthropic.com/v1/messages",
                        json=payload,
                        headers=headers,
                    ),
                    timeout=self._timeout + 5,
                )
                if resp.status_code in (429, 500, 502, 503):
                    raise GatewayHTTPError(f"provider status {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
                usage = body.get("usage", {}) or {}
                prompt_tokens = int(usage.get("input_tokens") or 0)
                completion_tokens = int(usage.get("output_tokens") or 0)
                text = "".join(block.get("text", "") for block in body.get("content", []))
                return ModelResponse(
                    content=text,
                    model=body.get("model", payload["model"]),
                    provider=self.provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=estimate_cost_usd(self._settings, prompt_tokens, completion_tokens),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (httpx.HTTPError, GatewayHTTPError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "anthropic attempt %d/%d failed: %s",
                    attempt,
                    self._max_attempts,
                    exc,
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))
        raise GatewayHTTPError(f"all {self._max_attempts} attempts failed: {last_error}")


class ScriptedModel(BaseModelGateway):
    """TEST DOUBLE ONLY. Returns canned outputs keyed by a matcher function.

    Mirrors SimulatedDataFetcher's role for the intelligence layer: exercises
    the full prompt->decode->fallback plumbing deterministically in CI.
    Records every request for assertions.
    """

    def __init__(
        self,
        responder: Callable[[ModelRequest], str],
        provider_name: str = "scripted_test",
    ) -> None:
        self._responder = responder
        self._provider_name = provider_name
        self.requests: list[ModelRequest] = []

    @property
    def provider(self) -> str:
        return self._provider_name

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        content = self._responder(request)
        prompt_tokens = sum(len(m.content.split()) for m in request.messages)
        completion_tokens = len(content.split())
        return ModelResponse(
            content=content,
            model="scripted-1",
            provider=self.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=0.0,
            latency_ms=0,
        )


# --------------------------------------------------------------------- decode

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json_block(content: str) -> str:
    """Extract the outermost JSON object from model text (fences tolerated)."""
    cleaned = _FENCE_RE.sub("", content.strip()).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise DecodeError(f"no JSON object found in model output: {content[:200]!r}")
    return cleaned[start : end + 1]


async def complete_structured(
    gateway: BaseModelGateway,
    contract: type[BaseModel],
    messages: list[ChatMessage],
    settings: Settings,
    model_hint: str | None = None,
    max_retries: int = 2,
) -> tuple[BaseModel, ModelResponse]:
    """Request a completion and decode it into ``contract`` with repair retries.

    On parse/validation failure the raw output is fed back with the validation
    error and the model gets one more chance per retry budget.
    """
    conversation = list(messages)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        response = await gateway.complete(
            ModelRequest(
                messages=conversation,
                model_hint=model_hint,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        )
        try:
            candidate = extract_json_block(response.content)
            parsed = contract.model_validate_json(candidate)
        except (DecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning("structured decode attempt %d failed: %s", attempt + 1, exc)
            conversation = list(conversation) + [
                ChatMessage(role="assistant", content=response.content),
                ChatMessage(
                    role="user",
                    content=(
                        f"Your JSON violated the schema or was unparseable: {exc}. "
                        f"Return ONLY corrected JSON matching the schema exactly."
                    ),
                ),
            ]
            continue
        return parsed, response

    raise DecodeError(f"structured decoding failed after {max_retries + 1} attempts: {last_error}")


# ------------------------------------------------------------------- factory


def build_gateway(settings: Settings) -> BaseModelGateway | None:
    """Build the production gateway from settings; None => deterministic mode.

    Absence of credentials is normal and logged; it is never an error.
    """
    provider = settings.model_provider.lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAICompatibleGateway(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_model=settings.research_model_reasoning,
            settings=settings,
        )
    if provider == "openai_compatible" and settings.openai_api_key:
        return OpenAICompatibleGateway(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_model=settings.research_model_reasoning,
            settings=settings,
        )
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicGateway(
            api_key=settings.anthropic_api_key,
            default_model=settings.research_model_reasoning,
            settings=settings,
        )
    if provider != "none":
        logger.warning(
            "MODEL_PROVIDER=%s but matching credential absent; deterministic mode active",
            provider,
        )
    return None
