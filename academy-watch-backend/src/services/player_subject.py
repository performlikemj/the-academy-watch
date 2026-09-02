"""Canonical resolution for signed player-subject identifiers."""

from __future__ import annotations

from dataclasses import dataclass

from src.models.follow import PlayerShadow
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.services.player_shadow_service import is_external_player_id
from src.services.player_suppression import is_local_player_suppressed, is_player_suppressed


@dataclass(frozen=True)
class PlayerSubject:
    """One resolved logical player across external and local namespaces."""

    signed_id: int
    tracked_player: TrackedPlayer | None = None
    shadow: PlayerShadow | None = None
    local_player: LocalPlayer | None = None
    is_minor: bool = False
    is_suppressed: bool = False

    @property
    def player_api_id(self) -> int:
        """Compatibility name for signed logical-id columns and route payloads."""

        return self.signed_id

    @property
    def local_player_id(self) -> int | None:
        return self.local_player.id if self.local_player is not None else None

    @property
    def is_local(self) -> bool:
        return self.signed_id < 0

    @property
    def is_external(self) -> bool:
        return is_external_player_id(self.signed_id)

    @property
    def is_adult(self) -> bool:
        return not self.is_minor

    @property
    def is_public(self) -> bool:
        return self.is_adult and not self.is_suppressed

    @property
    def is_approved_adult_local(self) -> bool:
        return self.is_local and self.is_public

    @property
    def source(self) -> str:
        if self.is_local:
            return "local"
        if self.tracked_player is not None:
            return "tracked"
        return "shadow"

    @property
    def display_name(self) -> str | None:
        if self.is_local and self.local_player is not None:
            return self.local_player.display_name
        if self.tracked_player is not None:
            return self.tracked_player.player_name
        return self.shadow.player_name if self.shadow is not None else None

    @property
    def position(self) -> str | None:
        if self.is_local and self.local_player is not None:
            return self.local_player.position
        if self.tracked_player is not None:
            return self.tracked_player.position
        return self.shadow.position if self.shadow is not None else None

    @property
    def nationality(self) -> str | None:
        if self.is_local and self.local_player is not None:
            return self.local_player.country
        if self.tracked_player is not None:
            return self.tracked_player.nationality
        return self.shadow.nationality if self.shadow is not None else None

    @property
    def birth_date(self):
        if self.is_local and self.local_player is not None:
            return self.local_player.birth_date
        if self.tracked_player is not None:
            return self.tracked_player.birth_date
        return self.shadow.birth_date if self.shadow is not None else None

    @property
    def birth_year(self) -> int | None:
        if self.local_player is not None:
            return self.local_player.birth_year
        birth_date = self.birth_date
        if birth_date is None:
            return None
        if hasattr(birth_date, "year"):
            return birth_date.year
        try:
            return int(str(birth_date)[:4])
        except (TypeError, ValueError):
            return None


def _preferred_tracked_player(player_api_id: int) -> TrackedPlayer | None:
    base = TrackedPlayer.query.filter(
        TrackedPlayer.player_api_id == player_api_id,
        TrackedPlayer.data_source != "owning-club",
    ).order_by(TrackedPlayer.id)
    active = base.filter(TrackedPlayer.is_active.is_(True)).first()
    return active or base.first()


def resolve_player_subject(signed_id) -> PlayerSubject | None:
    """Resolve a signed id without creating rows or contacting API-Football.

    Negative ids resolve only through the exact approved, unmerged LocalPlayer
    at ``id == -signed_id``. Positive ids retain the existing tracked/shadow
    universe. Minor and suppression state are returned on the subject so each
    caller can produce its surface's neutral denial without probing identities.
    """

    if isinstance(signed_id, bool) or not isinstance(signed_id, int) or signed_id == 0:
        return None

    if signed_id < 0:
        local_player = LocalPlayer.query.filter_by(
            id=-signed_id,
            api_player_id=signed_id,
            status="approved",
            merged_into_local_player_id=None,
        ).first()
        if local_player is None:
            return None
        shadow = PlayerShadow.query.filter_by(player_api_id=signed_id, is_active=True).first()
        return PlayerSubject(
            signed_id=signed_id,
            shadow=shadow,
            local_player=local_player,
            is_minor=bool(local_player_is_minor(local_player)),
            is_suppressed=is_player_suppressed(signed_id),
        )

    tracked_player = _preferred_tracked_player(signed_id)
    shadow = PlayerShadow.query.filter_by(player_api_id=signed_id, is_active=True).first()
    if tracked_player is None and shadow is None:
        return None

    # Keep the established positive-id minor bridge intact after graduation.
    local_player = LocalPlayer.query.filter_by(api_player_id=signed_id).order_by(LocalPlayer.id).first()
    minor = bool(local_player and local_player_is_minor(local_player))
    suppressed = is_player_suppressed(signed_id) or bool(
        local_player is not None and is_local_player_suppressed(local_player.id)
    )
    return PlayerSubject(
        signed_id=signed_id,
        tracked_player=tracked_player,
        shadow=shadow,
        local_player=local_player,
        is_minor=minor,
        is_suppressed=suppressed,
    )


__all__ = ["PlayerSubject", "resolve_player_subject"]
