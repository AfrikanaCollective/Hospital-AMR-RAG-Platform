"""Set planner (ARCH §15.1 step 1, §15.3; PRD-065).

Allocates slots per expected_outcome per the 60/20/20 composition and stratifies
over guideline topics/sections for coverage. Enforces the documented decision:
hard cases (missing_info_expected + no_guideline_expected) must not exceed 50%.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.enums import ExpectedOutcome


@dataclass(frozen=True)
class Composition:
    well_supported: int
    missing_info_expected: int
    no_guideline_expected: int

    @classmethod
    def parse(cls, spec: str) -> "Composition":
        a, b, c = (int(x) for x in spec.split(","))
        if a + b + c != 100:
            raise ValueError("composition percentages must sum to 100")
        comp = cls(a, b, c)
        if comp.hard_fraction > 50:
            raise ValueError(
                f"hard cases (missing_info + no_guideline) = {comp.hard_fraction}% exceeds the "
                "50% cap (PRD-065 / DEVIATIONS.md #9)"
            )
        return comp

    @property
    def hard_fraction(self) -> int:
        return self.missing_info_expected + self.no_guideline_expected


def allocate(total: int, comp: Composition) -> dict[ExpectedOutcome, int]:
    return {
        ExpectedOutcome.WELL_SUPPORTED: round(total * comp.well_supported / 100),
        ExpectedOutcome.MISSING_INFO_EXPECTED: round(total * comp.missing_info_expected / 100),
        ExpectedOutcome.NO_GUIDELINE_EXPECTED: round(total * comp.no_guideline_expected / 100),
    }
