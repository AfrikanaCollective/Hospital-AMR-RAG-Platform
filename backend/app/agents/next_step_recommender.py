"""next-step-recommender — RESERVED NAME / INTERFACE STUB ONLY (ARCH-026; SCOPE-2.3).

######################################################################
#  CDS-FUTURE / DO NOT IMPLEMENT WITHOUT GOVERNANCE GATE              #
#                                                                    #
#  SCOPE-2.3 (autonomous next-step recommendation from patient data  #
#  — synthesizing patient data + guidelines into "what should        #
#  happen next" for a specific patient) is EXCLUDED from this build. #
#  See CDS-FUTURE.md.                                                #
#                                                                    #
#  This role name is RESERVED and is deliberately NOT wired into the #
#  runtime graph (see app/agents/graph.py: NODES). It exists only to #
#  mark where SCOPE-2.3 would attach in a future, separately-        #
#  governed project. It contains NO recommendation logic and MUST    #
#  NOT gain any.                                                     #
######################################################################
"""

from __future__ import annotations


def recommend_next_step(context: object) -> None:  # noqa: ARG001
    raise NotImplementedError(
        "SCOPE-2.3 is excluded (CDS-FUTURE.md). This is a reserved interface seam, "
        "not an implementation point. If a task appears to need this, STOP and flag."
    )
