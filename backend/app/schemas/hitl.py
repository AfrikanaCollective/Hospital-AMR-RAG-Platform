"""HITL decision models (PRD-032; ARCH §13.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.enums import HitlAcceptAction


class SpanAction(BaseModel):
    span_index: int
    action: str  # kept | removed | edited
    edited_text: str | None = None


class HitlDecisionRequest(BaseModel):
    action: HitlAcceptAction
    # partial_accept:
    edited_answer: str | None = None
    span_actions: list[SpanAction] = Field(default_factory=list)
    accepted_context_ids: list[str] = Field(default_factory=list)
    # required for reject / partial_accept / out_of_scope
    reason_code: str | None = None

    @model_validator(mode="after")
    def _require_reason(self) -> HitlDecisionRequest:
        reason_required = (
            HitlAcceptAction.REJECT,
            HitlAcceptAction.PARTIAL_ACCEPT,
            HitlAcceptAction.OUT_OF_SCOPE,
        )
        if self.action in reason_required and not self.reason_code:
            raise ValueError(f"{self.action} requires reason_code")
        if self.action == HitlAcceptAction.PARTIAL_ACCEPT and not (
            self.edited_answer or self.span_actions
        ):
            raise ValueError("partial_accept requires edited_answer or span_actions")
        return self
