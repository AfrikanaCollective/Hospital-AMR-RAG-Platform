"""local-adaptation agent — EXTENSION SEAM STUB (ARCH-026; SCOPE-2.4; CDS-FUTURE.md).

######################################################################
#  CDS-FUTURE / DO NOT IMPLEMENT WITHOUT GOVERNANCE GATE              #
#                                                                    #
#  SCOPE-2.4 (guideline adjustment based on local operational        #
#  constraints, beyond alternatives already present in retrieved     #
#  guideline text) is EXCLUDED from this build. See CDS-FUTURE.md    #
#  for what must be true before this can be built (regulatory        #
#  classification, clinical governance sign-off, validation          #
#  strategy, liability model).                                       #
#                                                                    #
#  This file exists ONLY so the capability could be added later      #
#  without a graph redesign. It contains NO adaptation logic and     #
#  MUST NOT gain any. `LOCAL_ADAPTATION_ENABLED` is inert.           #
#                                                                    #
#  The SCOPE-2.5 narrow exception (surface a documented alternative  #
#  ALREADY in retrieved text) is handled in the retrieval +          #
#  synthesis path, NOT here.                                         #
######################################################################
"""

from __future__ import annotations

from app.agents.state import GraphState
from app.config import get_settings
from app.schemas.enums import EscalationTrigger


def run(state: GraphState) -> GraphState:
    """Always returns a capability_not_enabled escalation. Never adapts anything."""
    assert not get_settings().local_adaptation_enabled, (
        "LOCAL_ADAPTATION_ENABLED is inert; enabling it does nothing without a "
        "governance-gated implementation (CDS-FUTURE.md). It must stay false."
    )
    state["escalation"] = {
        "trigger_code": EscalationTrigger.CAPABILITY_NOT_ENABLED,
        "message": (
            "This request would require guideline adjustment for a local operational "
            "constraint, which this system does not perform. Routing to clinician review."
        ),
    }
    return state


def propose_local_adaptation(context: object) -> None:  # noqa: ARG001
    """Reserved interface (ARCH-026). Not implemented; must not be implemented here."""
    raise NotImplementedError(
        "SCOPE-2.4 is excluded (CDS-FUTURE.md). This interface is a placement seam only."
    )
