"""Every number shipped is declared; unverified figures are cut (goal G060).

A generated report with an undeclared number is a claim without a source,
and an unverified figure shipped alongside verified ones borrows their
credibility. This module makes the declaration structural: every number in a
report carries a kind — observed, derived, proposed, cited, or counted — and
anything without one never reaches the rendered output. Cutting is the
default, not a review step: ``render()`` excludes quarantined figures while
reporting what was cut, so the reader sees both the report and its redactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "NumberKind",
    "ReportedNumber",
    "ResearchReport",
]


class NumberKind(StrEnum):
    """What a number is. Five kinds, closed: a sixth would be a number whose
    nature the author could not name, which is exactly what this module refuses."""

    OBSERVED = "observed"
    DERIVED = "derived"
    PROPOSED = "proposed"
    CITED = "cited"
    COUNTED = "counted"


@dataclass(frozen=True)
class ReportedNumber:
    """One declared number: label, value, kind, and the source that stands
    behind it. The source is required — a declared number with nowhere to
    check it is a rumour with a category."""

    label: str
    value: float
    kind: NumberKind
    source: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("a reported number needs a label; an unnamed figure is uncheckable")
        if not self.source.strip():
            raise ValueError(
                f"number {self.label!r} names no source: a declaration without "
                "somewhere to check it is decoration"
            )


@dataclass
class ResearchReport:
    """A report under construction. Declared numbers accumulate; raw figures
    quarantine. ``render()`` ships the former and lists the latter as cut —
    unverified figures are redacted by default, never by review."""

    title: str
    numbers: list[ReportedNumber] = field(default_factory=list)
    _quarantine: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def add(self, number: ReportedNumber) -> None:
        self.numbers.append(number)

    def add_raw(self, label: str, value: float, *, reason: str = "") -> None:
        """Stage an undeclared figure. It will be cut at render, not shipped:
        calling this is how a pipeline admits it has a number it cannot yet
        stand behind."""
        self._quarantine.append({"label": label, "value": value, "reason": reason})

    @property
    def cut(self) -> list[str]:
        """Labels quarantined. Public, so the redactions are themselves part
        of the report rather than a silent absence."""
        return [str(entry["label"]) for entry in self._quarantine]

    def render(self) -> dict[str, Any]:
        """Ship declared numbers; list the cut. The output contains no figure
        the report cannot source, and says which figures that excluded."""
        return {
            "title": self.title,
            "numbers": [
                {
                    "label": number.label,
                    "value": number.value,
                    "kind": number.kind.value,
                    "source": number.source,
                }
                for number in self.numbers
            ],
            "cut": self.cut,
            "counts": {
                "shipped": len(self.numbers),
                "cut": len(self._quarantine),
            },
        }
