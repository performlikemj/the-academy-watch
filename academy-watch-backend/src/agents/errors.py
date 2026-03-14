"""Common exceptions shared across newsletter agents."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass(eq=False)
class NoActiveLoaneesError(RuntimeError):
    """Raised when attempting to generate a newsletter for a team with zero active loanees."""

    team_id: int
    week_start: date | None = None
    week_end: date | None = None

    def __post_init__(self) -> None:
        message = f"Team {self.team_id} has no active loanees"
        if self.week_start and self.week_end:
            message += f" for week {self.week_start}–{self.week_end}"
        super().__init__(message)
