"""Tiny HTTP server that imitates the self-hosted LLM gateway for dev/CI.

Run by the `llm-gateway` docker-compose service under the `dev`/`full` profiles.
Real deployments drop this service and point LLM_GATEWAY_URL at the actual
self-hosted gateway.

Phase 2 gives this a minimal OpenAI-ish `/v1/chat/completions`,
`/v1/embeddings`, and `/v1/rerank` surface backed by app.llm.stub. For Phase 1
it just serves a health endpoint so the container starts.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.llm.stub import stub_chat, stub_embed, stub_rerank

app = FastAPI(title="LLM gateway (dev stub)")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "stub"}


@app.post("/v1/chat/completions")
async def chat(body: dict) -> dict:
    r = stub_chat(system=body.get("system", ""), messages=body.get("messages", []))
    return {"model": r.model_id, "choices": [{"message": {"role": "assistant", "content": r.text}}]}


@app.post("/v1/embeddings")
async def embeddings(body: dict) -> dict:
    vecs = stub_embed(body.get("input", []))
    return {"data": [{"embedding": v, "index": i} for i, v in enumerate(vecs)]}


@app.post("/v1/rerank")
async def rerank(body: dict) -> dict:
    scores = stub_rerank(body.get("query", ""), body.get("documents", []))
    return {"results": [{"index": i, "relevance_score": s} for i, s in enumerate(scores)]}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
