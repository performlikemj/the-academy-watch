"""B2 identity rekeys run inside the caller's identity-merge transaction, even while dark."""

from collections import Counter

import sqlalchemy as sa
from src.models.league import db
from src.models.opportunities import OpportunityApplication


def repoint_applications(source_claims, target_claims, target_signed_id):
    if not sa.inspect(db.session.connection()).has_table("opportunity_applications"):
        return
    target_by_user = {claim.user_account_id: claim for claim in target_claims}
    claim_ids = [c.id for c in [*source_claims, *target_claims]]
    apps = (
        OpportunityApplication.query.filter(
            sa.or_(
                OpportunityApplication.claim_id.in_(claim_ids),
                OpportunityApplication.signed_player_id == target_signed_id,
            )
        )
        .order_by(OpportunityApplication.id)
        .with_for_update()
        .all()
    )
    # Keep both independent application histories intact; admin resolves the collision by waiting
    # for erasure/retention. Nothing is deleted or partially rekeyed by a failed merge.
    if any(count > 1 for count in Counter(app.opportunity_id for app in apps).values()):
        return "Cannot merge: both identities have retained applications to the same opportunity. Resolve retention or erasure first."
    source_by_id = {c.id: c for c in source_claims}
    for app in apps:
        source_claim = source_by_id.get(app.claim_id)
        if source_claim and source_claim.user_account_id in target_by_user:
            app.claim_id = target_by_user[source_claim.user_account_id].id
        app.signed_player_id = target_signed_id
    db.session.flush()
