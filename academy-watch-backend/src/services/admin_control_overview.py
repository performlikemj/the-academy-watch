"""Exact per-queue workload counts. Totals count queue items, not unique cases."""

import sqlalchemy as sa
from src.models.admin_control import SafeguardingCase, now
from src.models.funding import ClubProgramClaim, ClubProgramProfileRevision, ClubProgramUpdate
from src.models.league import (
    CommunityTake,
    ManualPlayerSubmission,
    PlayerFlag,
    PlayerLink,
    QuickTakeSubmission,
    TeamTrackingRequest,
    db,
)
from src.models.showcase import (
    ClubOfficialClaim,
    LocalClub,
    LocalPlayer,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
)
from src.models.trust import ContentReport, ScoutVerification


def queue_counts(enabled):
    specs = [
        ("manual", "Manual players", "/admin/inbox?tab=manual", ManualPlayerSubmission, "pending", None),
        ("takes", "Community takes", "/admin/inbox?tab=takes", CommunityTake, "pending", None),
        ("submissions", "Quick takes", "/admin/inbox?tab=submissions", QuickTakeSubmission, "pending", None),
        ("flags", "Player flags", "/admin/inbox?tab=flags", PlayerFlag, "pending", None),
        ("tracking", "Tracking requests", "/admin/inbox?tab=tracking", TeamTrackingRequest, "pending", None),
        ("links", "Player links", "/admin/inbox?tab=links", PlayerLink, "pending", None),
        ("club_claims", "Club claims", "/admin/funding?tab=claims", ClubProgramClaim, "pending", "programs"),
        (
            "club_profiles",
            "Club profile revisions",
            "/admin/funding?tab=content",
            ClubProgramProfileRevision,
            "pending",
            "programs",
        ),
        ("club_updates", "Club updates", "/admin/funding?tab=content", ClubProgramUpdate, "pending", "programs"),
        (
            "scout_verifications",
            "Scout verifications",
            "/admin/trust?tab=verifications",
            ScoutVerification,
            "pending",
            "people",
        ),
        (
            "profile_claims",
            "Player profile claims",
            "/admin/showcase?tab=claims",
            PlayerProfileClaim,
            "pending",
            "people",
        ),
        (
            "showcase_profiles",
            "Player showcase edits",
            "/admin/showcase?tab=profiles",
            PlayerShowcaseProfile,
            "pending",
            "people",
        ),
        ("local_players", "Community players", "/admin/showcase?tab=local-players", LocalPlayer, "pending", "people"),
        ("local_clubs", "Community clubs", "/admin/local-clubs?tab=clubs", LocalClub, "pending", "people"),
        (
            "affiliations",
            "Club affiliations",
            "/admin/local-clubs?tab=affiliations",
            PlayerClubAffiliation,
            "pending",
            "people",
        ),
        (
            "official_claims",
            "Club official claims",
            "/admin/local-clubs?tab=officials",
            ClubOfficialClaim,
            "pending",
            "people",
        ),
        (
            "showcase_media",
            "Showcase photos",
            "/admin/showcase?tab=media",
            PlayerShowcaseMedia,
            "pending",
            "people",
        ),
        ("reports", "Open reports", "/admin/trust?tab=reports", ContentReport, "open", "safety"),
        ("safeguarding", "Safeguarding cases", "/admin/safety", SafeguardingCase, None, "safety"),
    ]
    specs = [spec for spec in specs if spec[5] is None or enabled(spec[5])]
    queries = []
    for key, _, _, model, status, _ in specs:
        predicate = model.status != "closed" if status is None else model.status == status
        if key == "local_players":
            predicate = sa.and_(predicate, LocalPlayer.provenance != "club")
        elif key == "showcase_media":
            predicate = sa.and_(predicate, PlayerShowcaseMedia.kind == "photo")
        queries.append(
            sa.select(sa.literal(key).label("key"), sa.func.count().label("count")).select_from(model).where(predicate)
        )
    counts = dict(db.session.execute(sa.union_all(*queries)).all())
    overdue = (
        SafeguardingCase.query.filter(
            SafeguardingCase.status != "closed",
            SafeguardingCase.first_action_at.is_(None),
            SafeguardingCase.first_action_due_at < now(),
        ).count()
        if enabled("safety")
        else None
    )
    return {
        "queues": [{"key": key, "label": label, "href": href, "count": counts[key]} for key, label, href, *_ in specs],
        "total": sum(counts.values()),
        "overdue_safeguarding": overdue,
    }
