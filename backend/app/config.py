"""Application configuration (ARCH-005, ARCH-020, §20; PRD-101, PRD-103, PRD-108).

All settings come from the environment / .env. No model name or secret is
hardcoded. `Settings.validate_model_config()` implements constraint #6: the
answer path must refuse to start on the placeholder model id, and an
unverified id must produce a prominent warning.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PLACEHOLDER_MODEL_ID = "<set-me>"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ── app ──
    app_env: str = "dev"
    log_level: str = "INFO"
    api_base_path: str = "/api"
    request_id_header: str = "x-request-id"

    # ── LLM gateway (ARCH-005 / PRD-101 / PRD-102) ──
    llm_gateway_url: str = "http://llm-gateway:8080"
    model_id: str = PLACEHOLDER_MODEL_ID
    model_id_fallbacks: str = ""  # comma-separated
    model_id_verified: bool = False
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2

    # ── embeddings / reranker (ARCH-004 / ARCH-012 / PRD-103) ──
    embedding_backend: str = "stub"  # local | gateway | stub
    embedding_model_id: str = "BAAI/bge-large-en-v1.5"  # UNVERIFIED placeholder
    embedding_model_verified: bool = False
    embedding_query_prefix: str = ""
    embedding_doc_prefix: str = ""
    reranker_backend: str = "stub"
    reranker_model_id: str = "BAAI/bge-reranker-v2-m3"  # UNVERIFIED placeholder
    reranker_model_verified: bool = False

    # ── retrieval (ARCH-003 / §7) ──
    candidate_k: int = 40
    fused_k: int = 24
    top_k: int = 8
    rrf_k: int = 60
    retrieval_min_score: float = 0.30
    support_score_floor: float = 0.20
    min_supporting_chunks: int = 2
    grounding_entailment_mode: str = "hybrid"  # lexical | model | hybrid

    # ── vector store (ARCH-002 / ARCH-023) ──
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_guideline_collection: str = "guideline_chunks_v1"
    patient_record_vectors_enabled: bool = False

    # ── guideline corpus + ingestion (ARCH-038 / ARCH §5.1 / DEVIATIONS #26, #28) ──
    sample_guidelines_dir: str = "data/sample_guidelines"
    guidelines_allow_synthetic: bool = False  # opt-in CI-only synthetic fixture set
    ingest_min_parse_quality: float = 0.60  # below -> document badged + held for admin review

    # ── patient records (ARCH-039 / DEVIATIONS #30, #33, #34) ──
    patient_records_dir: str = "data/patient_records"
    record_domain: str = "neonatal"  # neonatal | adult_inpatient — MUST match the ingested corpus domain
    deidentified_attestation_required: bool = True  # de-identified datasets need a complete DATASET.md attestation

    # ── database / async (ARCH-007 / ARCH-008) ──
    database_url: str = "postgresql+psycopg://hrag_app:hrag_app_pw@postgres:5432/hospital_rag"
    redis_url: str = "redis://:redis_pw@redis:6379/0"
    celery_broker_url: str = "redis://:redis_pw@redis:6379/1"
    celery_result_backend: str = "redis://:redis_pw@redis:6379/2"

    # ── auth / rbac (ARCH-011 / ARCH-034) ──
    auth_provider: str = "devjwt"  # devjwt | oidc
    devjwt_signing_key: str = "dev-only-change-me"
    devjwt_issuer: str = "hospital-rag-dev"
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_audience: str = ""

    # ── crypto / secrets (ARCH-032 / ARCH-033) ──
    secrets_backend: str = "file"  # env | file | vault
    crypto_kek_file: str = "./secrets/dev_kek.bin"
    vault_addr: str = ""
    vault_token: str = ""

    # ── HITL / rubric (ARCH-018 / ARCH-020 / ARCH-021) ──
    escalation_sla_minutes: int = 60
    irr_min_raters: int = 3
    irr_metric: str = "krippendorff_alpha_ordinal"
    review_webhook_url: str = ""

    # ── auto question generation (ARCH-022 / PRD-065) ──
    qgen_composition: str = "60,20,20"  # well_supported,missing_info_expected,no_guideline_expected
    qgen_dedup_threshold: float = 0.92
    qgen_max_retries: int = 3

    # ── eval gating (§16) ──
    eval_min_precision_at_8: float = 0.70
    eval_min_recall_at_24: float = 0.80
    eval_min_citation_support_rate: float = 0.95
    eval_require_zero_scope_violations: bool = True
    eval_require_full_disclaimer: bool = True

    # ── retention (PRD-Q3) ──
    retention_audit_days: int = 3650
    retention_context_days: int = 1825
    retention_conv_days: int = 730
    checkpoint_ttl_days: int = 30

    # ── extension seam (ARCH-026 / CDS-FUTURE.md) ── inert; do not implement.
    local_adaptation_enabled: bool = Field(default=False)

    # ── derived ──
    @property
    def fallback_model_ids(self) -> list[str]:
        return [m.strip() for m in self.model_id_fallbacks.split(",") if m.strip()]

    @property
    def qgen_composition_tuple(self) -> tuple[int, int, int]:
        parts = [int(x) for x in self.qgen_composition.split(",")]
        if len(parts) != 3 or sum(parts) != 100:
            raise ValueError("QGEN_COMPOSITION must be three integers summing to 100")
        return parts[0], parts[1], parts[2]

    def is_model_placeholder(self) -> bool:
        return self.model_id.strip() in ("", PLACEHOLDER_MODEL_ID)

    def validate_model_config(self, *, require_answer_path: bool) -> None:
        """Constraint #6. Call at startup and before serving the answer path.

        - placeholder model id  -> hard error if the answer path is required
        - unverified model id    -> prominent warning, not an error
        """
        if self.is_model_placeholder():
            msg = (
                "MODEL_ID is the placeholder (%r). Set MODEL_ID to a model id "
                "verified against the self-hosted gateway's current docs. "
                "The build does not guess model names (constraint #6)."
            ) % PLACEHOLDER_MODEL_ID
            if require_answer_path:
                raise RuntimeError(msg)
            logger.warning(msg)
        elif not self.model_id_verified:
            logger.warning(
                "MODEL_ID=%r is set but MODEL_ID_VERIFIED=false. Confirm this id "
                "against current gateway documentation, then set MODEL_ID_VERIFIED=true.",
                self.model_id,
            )
        for label, mid, verified in (
            ("EMBEDDING_MODEL_ID", self.embedding_model_id, self.embedding_model_verified),
            ("RERANKER_MODEL_ID", self.reranker_model_id, self.reranker_model_verified),
        ):
            if not verified:
                logger.warning(
                    "%s=%r is an UNVERIFIED placeholder default. Confirm or override it "
                    "and set the corresponding *_VERIFIED=true (DEVIATIONS.md #10).",
                    label,
                    mid,
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
