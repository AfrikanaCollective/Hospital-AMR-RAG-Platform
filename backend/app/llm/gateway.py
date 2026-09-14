"""LLMGateway — the single path to the self-hosted LLM gateway (ARCH-005).

Constraint #6:
  - model ids come from config; none is hardcoded here;
  - the answer path must not run on the placeholder model id;
  - an unverified id logs a warning (handled in app.config.validate_model_config);
  - fallback routing tries `MODEL_ID_FALLBACKS` in order on gateway
    error/timeout.

Wire contract: an OpenAI-ish `POST /v1/chat/completions` — matches
`app.llm.stub_server` (the dev/CI stub) and the shape DEVIATIONS.md #42
confirmed against a real operator-supplied self-hosted gateway for the sibling
`/v1/embeddings` endpoint. Request: `{"model", "system", "messages", **params}`.
Response: `{"model", "choices": [{"message": {"content"}}], "usage"?}`.

Transport security (DEVIATIONS.md #54): `httpx.Client` verifies TLS
certificates by default (never disabled here); `Settings.validate_gateway_transport()`
(called at construction) warns if `LLM_GATEWAY_URL` is plaintext against a
non-local host — see that method's docstring for why "private net" doesn't
cover the real gateway the way it covers Postgres/Redis/Qdrant.

`embed`/`rerank` on this class remain unimplemented: `app.ingestion.embed` and
`app.retrieval.rerank` are the actual dispatch points (local/stub/gateway) and
do not route through here — see their own modules. Their `gateway` branches
are separate future work, not blocking this class's `chat()`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from app.config import Settings, get_settings
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatResult:
    text: str
    model_id: str
    used_fallback: bool = False
    usage: dict = field(default_factory=dict)


class LLMGatewayError(RuntimeError):
    pass


class LLMGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Fail closed: the answer path must not start on the placeholder id.
        self.settings.validate_model_config(require_answer_path=True)
        self.settings.validate_gateway_transport()
        self._model_chain: list[str] = [self.settings.model_id, *self.settings.fallback_model_ids]
        self._client = httpx.Client(
            base_url=self.settings.llm_gateway_url,
            timeout=self.settings.llm_timeout_seconds,
        )

    @property
    def model_chain(self) -> list[str]:
        """Primary model id followed by configured fallbacks (ARCH-005)."""
        return list(self._model_chain)

    def _headers(self) -> dict[str, str]:
        if self.settings.llm_gateway_api_key:
            return {"Authorization": f"Bearer {self.settings.llm_gateway_api_key}"}
        return {}

    def _post_chat_completion(
        self, *, model_id: str, system: str, messages: list[dict], params: dict
    ) -> dict:
        resp = self._client.post(
            "/v1/chat/completions",
            json={"model": model_id, "system": system, "messages": messages, **params},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def chat(
        self, *, system: str, messages: list[dict], contains_phi: bool = False, **params: object
    ) -> ChatResult:
        """Send a chat completion. Tries each model id in `model_chain` in order,
        with `settings.llm_max_retries` retries per model on a transient error.

        `contains_phi` is asserted only to make the PHI-egress rule explicit at
        call sites; PHI only ever goes to the configured self-hosted gateway
        (there is no other backend), so this never changes routing — it is a
        guard against a future backend being added carelessly.
        """
        _ = contains_phi  # documented no-op; see docstring
        last_error: Exception | None = None
        for i, model_id in enumerate(self._model_chain):
            for attempt in range(self.settings.llm_max_retries + 1):
                try:
                    data = self._post_chat_completion(
                        model_id=model_id, system=system, messages=messages, params=params
                    )
                    choice = data["choices"][0]["message"]["content"]
                    return ChatResult(
                        text=choice,
                        model_id=data.get("model", model_id),
                        used_fallback=i > 0,
                        usage=data.get("usage", {}),
                    )
                except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                    last_error = exc
                    # Never log message content (PHI redaction, app.logging).
                    logger.warning(
                        "llm_gateway_call_failed",
                        model_id=model_id,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt < self.settings.llm_max_retries:
                        time.sleep(min(0.5 * (2**attempt), 4.0))
        raise LLMGatewayError(
            f"LLM gateway call failed for every model in the fallback chain: {self._model_chain}"
        ) from last_error

    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError(
            "Not routed through LLMGateway — use app.ingestion.embed.embed_texts (ARCH-004)"
        )

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        raise NotImplementedError(
            "Not routed through LLMGateway — use app.retrieval.rerank.rerank (ARCH-012)"
        )
