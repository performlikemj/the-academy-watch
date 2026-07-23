# Agent Directive: The Academy Watch Refactor

> Implementation guide for transforming Go On Loan → The Academy Watch
> Read ACADEMY_WATCH_REFACTOR_PLAN.md for full context

---

## CRITICAL: Read First

Before ANY work:
1. Read `AGENTS.md` - Operating protocol
2. Read `CONTINUITY.md` - Current project state
3. Read `ledgers/ACADEMY_WATCH_REFACTOR_PLAN.md` - Full refactor plan
4. Understand the tech stack: Flask 3.1 + React 19 + PostgreSQL

---

## Mission

Transform "Go On Loan" (loan-only player tracking with multi-writer platform) into "The Academy Watch" (academy + loan tracking with community-curated takes).

**Key simplifications:**
- Remove Stripe payment complexity
- Remove multi-writer recruitment system
- Add community take aggregation
- Add academy player tracking

---

## Phase-by-Phase Instructions

### Phase 1: Foundation (Start Here)

**Goal:** Simplify codebase, rebrand, don't break existing functionality

#### Task 1.1: Rename LoanedPlayer → TrackedPlayer

**Files to modify:**
```
loan-army-backend/src/models/league.py       # Model definition
loan-army-backend/src/routes/api.py          # All references
loan-army-backend/src/routes/journalist.py   # All references
loan-army-backend/src/agents/*.py            # All references
```

**Steps:**
1. Create Alembic migration:
   ```bash
   cd loan-army-backend
   flask db migrate -m "rename loaned_player to tracked_player"
   ```
2. In migration file, use `op.rename_table('loaned_player', 'tracked_player')`
3. Update model class name: `LoanedPlayer` → `TrackedPlayer`
4. Update all imports and references (use grep to find all)
5. Update foreign key references
6. Run: `flask db upgrade`
7. Test: Ensure existing data accessible

**Acceptance:** Migration runs without error, all existing tests pass

---

#### Task 1.2: Add New Columns to TrackedPlayer

**Add these columns:**
```python
# In TrackedPlayer model
pathway_status = db.Column(db.String(20), default='on_loan')
# Values: 'academy' | 'on_loan' | 'first_team' | 'released'

current_level = db.Column(db.String(20), nullable=True)
# Values: 'U18' | 'U21' | 'U23' | 'Reserve' | 'Senior'

data_depth = db.Column(db.String(20), default='full_stats')
# Values: 'full_stats' | 'events_only' | 'profile_only'
```

**Steps:**
1. Add columns to model in `league.py`
2. Create migration: `flask db migrate -m "add pathway tracking columns"`
3. Set default for existing records: `pathway_status='on_loan'`, `data_depth='full_stats'`
4. Run migration

**Acceptance:** Columns exist, existing loans have correct defaults

---

#### Task 1.3: Remove Stripe Integration (Backend)

**Files to DELETE:**
```
loan-army-backend/src/routes/stripe_journalist.py
loan-army-backend/src/routes/stripe_subscriber.py
loan-army-backend/src/routes/stripe_webhooks.py
loan-army-backend/src/routes/admin_revenue.py
loan-army-backend/src/services/stripe_usage_service.py
```

**Files to MODIFY:**
```
loan-army-backend/src/main.py                # Remove blueprint registrations
loan-army-backend/src/models/league.py       # Mark Stripe models as deprecated
```

**Steps:**
1. Remove Stripe route files
2. In `main.py`, remove:
   ```python
   from src.routes.stripe_journalist import stripe_journalist_bp
   from src.routes.stripe_subscriber import stripe_subscriber_bp
   # ... and their app.register_blueprint() calls
   ```
3. In `league.py`, add deprecation comments to:
   - `StripeConnectedAccount`
   - `StripeSubscriptionPlan`
   - `StripeSubscription`
   - `StripePlatformRevenue`
4. Do NOT delete the models yet (data preservation)
5. Remove Stripe env vars from `env.template`

**Acceptance:** App starts without Stripe, no import errors

---

#### Task 1.4: Remove Stripe Integration (Frontend)

**Files to DELETE:**
```
loan-army-frontend/src/pages/JournalistPricing.jsx
loan-army-frontend/src/pages/JournalistStripeSetup.jsx
loan-army-frontend/src/pages/admin/AdminRevenueDashboard.jsx
loan-army-frontend/src/context/StripeContext.jsx
```

**Files to MODIFY:**
```
loan-army-frontend/src/App.jsx               # Remove Stripe routes
loan-army-frontend/src/lib/api.js            # Remove Stripe API methods
loan-army-frontend/package.json              # Remove @stripe/stripe-js if present
```

**Steps:**
1. Delete Stripe-related pages
2. In `App.jsx`, remove routes to deleted pages
3. In `api.js`, remove all methods containing "stripe" (search for "stripe")
4. Remove StripeContext provider from App.jsx
5. Update the lockfile without restoring packages, then run
   `./scripts/security/check_frontend_dependencies.sh`
6. Run `pnpm lint` to find any broken imports

**Acceptance:** Frontend builds without Stripe, no import errors

---

#### Task 1.5: Remove Writer Recruitment System

**Backend - Files to modify:**
```
loan-army-backend/src/routes/journalist.py   # Remove coverage request endpoints
loan-army-backend/src/routes/api.py          # Remove admin coverage endpoints
```

**Endpoints to remove from `journalist.py`:**
- `POST /journalists/invite`
- `POST /journalists/<id>/assign-teams`
- `GET /writer/coverage-requests`
- `POST /writer/coverage-requests`
- `DELETE /writer/coverage-requests/<id>`

**Endpoints to remove from `api.py`:**
- `GET /admin/coverage-requests`
- `POST /admin/coverage-requests/<id>/approve`
- `POST /admin/coverage-requests/<id>/deny`

**Frontend - Files to DELETE:**
```
loan-army-frontend/src/pages/admin/AdminCoverageRequests.jsx
loan-army-frontend/src/pages/admin/AdminExternalWriters.jsx
loan-army-frontend/src/components/CoverageRequestModal.jsx
```

**Frontend - Files to MODIFY:**
```
loan-army-frontend/src/App.jsx               # Remove routes
loan-army-frontend/src/lib/api.js            # Remove coverage API methods
loan-army-frontend/src/pages/admin/AdminDashboard.jsx  # Remove coverage stats
```

**Acceptance:** No coverage request UI or endpoints remain

---

#### Task 1.6: Simplify User Roles

**Current roles:** admin, journalist, editor, can_author_commentary
**New roles:** admin, editor (editor = can curate + write commentary)

**In `league.py` UserAccount model:**
- Keep: `is_admin`
- Rename: `is_journalist` → `is_editor` (or add `is_editor`, deprecate `is_journalist`)
- Remove: Complex role hierarchy

**In frontend AuthContext:**
- Update role checks to use simplified model

**Acceptance:** Login works, admin/editor distinction functional

---

#### Task 1.7: Rebrand to "The Academy Watch"

**Files to update:**
```
loan-army-frontend/src/App.jsx               # Title, meta tags
loan-army-frontend/index.html                # <title>, favicon ref
loan-army-frontend/public/                   # Favicon, OG images
loan-army-backend/src/services/email_service.py  # Email templates
loan-army-backend/src/services/reddit_service.py # Reddit post headers
```

**String replacements:**
- "Go On Loan" → "The Academy Watch"
- "GoOnLoan" → "TheAcademyWatch"
- "loan-army" → "academy-watch" (in user-visible places only, NOT file paths yet)

**Acceptance:** No "Go On Loan" visible to end users

---

#### Task 1.8: Run Full Test Suite

```bash
cd loan-army-frontend
pnpm lint
pnpm test:e2e
```

**If tests fail:**
1. Check if tests reference removed features (coverage requests, Stripe)
2. Delete or update obsolete test files
3. Fix legitimate regressions

**Acceptance:** All tests pass (or obsolete tests removed)

---

### Phase 2: Community Takes

> Only start after Phase 1 is complete and tests pass

#### Task 2.1: Create CommunityTake Model

**In `loan-army-backend/src/models/league.py`, add:**

```python
class CommunityTake(db.Model):
    __tablename__ = 'community_take'

    id = db.Column(db.Integer, primary_key=True)

    # Source info
    source_type = db.Column(db.String(20), nullable=False)  # 'reddit' | 'twitter' | 'submission' | 'editor'
    source_url = db.Column(db.String(500), nullable=True)
    source_author = db.Column(db.String(100), nullable=False)
    source_platform = db.Column(db.String(50), nullable=True)  # 'r/reddevils', '@handle'

    # Content
    content = db.Column(db.Text, nullable=False)

    # Associations
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletter.id'), nullable=True)

    # Curation
    status = db.Column(db.String(20), default='pending')  # 'pending' | 'approved' | 'rejected'
    curated_by = db.Column(db.Integer, db.ForeignKey('user_account.id'), nullable=True)
    curated_at = db.Column(db.DateTime, nullable=True)

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    original_posted_at = db.Column(db.DateTime, nullable=True)
    upvotes = db.Column(db.Integer, default=0)

    # Relationships
    player = db.relationship('Player', backref='community_takes')
    team = db.relationship('Team', backref='community_takes')
    newsletter = db.relationship('Newsletter', backref='community_takes')
    curator = db.relationship('UserAccount', foreign_keys=[curated_by])
```

**Steps:**
1. Add model to `league.py`
2. Create migration: `flask db migrate -m "add community_take table"`
3. Run: `flask db upgrade`

**Acceptance:** Table created, can insert/query records

---

#### Task 2.2: Create QuickTakeSubmission Model

```python
class QuickTakeSubmission(db.Model):
    __tablename__ = 'quick_take_submission'

    id = db.Column(db.Integer, primary_key=True)

    # Submitter
    submitter_name = db.Column(db.String(100), nullable=True)
    submitter_email = db.Column(db.String(255), nullable=True)

    # Content
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)  # Max ~280 chars enforced in API

    # Moderation
    status = db.Column(db.String(20), default='pending')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user_account.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    # Link to approved take
    community_take_id = db.Column(db.Integer, db.ForeignKey('community_take.id'), nullable=True)

    # Spam prevention
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_hash = db.Column(db.String(64), nullable=True)

    # Relationships
    player = db.relationship('Player', backref='quick_take_submissions')
    reviewer = db.relationship('UserAccount', foreign_keys=[reviewed_by])
    community_take = db.relationship('CommunityTake', backref='submission')
```

**Acceptance:** Table created, can insert/query records

---

#### Task 2.3: Build Submission API

**Create new file: `loan-army-backend/src/routes/community.py`**

```python
from flask import Blueprint, request, jsonify
from src.models.league import db, CommunityTake, QuickTakeSubmission, Player
import hashlib

community_bp = Blueprint('community', __name__, url_prefix='/api')

@community_bp.route('/community-takes/submit', methods=['POST'])
def submit_take():
    """Public endpoint for community take submissions"""
    data = request.get_json()

    # Validate
    if not data.get('player_id') or not data.get('content'):
        return jsonify({'error': 'player_id and content required'}), 400

    if len(data['content']) > 500:
        return jsonify({'error': 'Content must be under 500 characters'}), 400

    # Check player exists
    player = Player.query.get(data['player_id'])
    if not player:
        return jsonify({'error': 'Player not found'}), 404

    # Create submission
    submission = QuickTakeSubmission(
        player_id=data['player_id'],
        content=data['content'].strip(),
        submitter_name=data.get('name', 'Anonymous'),
        submitter_email=data.get('email'),
        ip_hash=hashlib.sha256(request.remote_addr.encode()).hexdigest()[:16] if request.remote_addr else None
    )

    db.session.add(submission)
    db.session.commit()

    return jsonify({'message': 'Take submitted for review', 'id': submission.id}), 201


@community_bp.route('/community-takes', methods=['GET'])
def list_approved_takes():
    """Public endpoint to list approved community takes"""
    player_id = request.args.get('player_id', type=int)
    team_id = request.args.get('team_id', type=int)
    limit = request.args.get('limit', 20, type=int)

    query = CommunityTake.query.filter_by(status='approved')

    if player_id:
        query = query.filter_by(player_id=player_id)
    if team_id:
        query = query.filter_by(team_id=team_id)

    takes = query.order_by(CommunityTake.created_at.desc()).limit(limit).all()

    return jsonify([{
        'id': t.id,
        'content': t.content,
        'source_author': t.source_author,
        'source_platform': t.source_platform,
        'source_type': t.source_type,
        'player_id': t.player_id,
        'created_at': t.created_at.isoformat()
    } for t in takes])
```

**Register in `main.py`:**
```python
from src.routes.community import community_bp
app.register_blueprint(community_bp)
```

**Acceptance:** Can POST submission, GET approved takes

---

#### Task 2.4: Build Curation API

**Add admin endpoints to `community.py`:**

```python
from src.routes.api import require_admin  # Import existing decorator

@community_bp.route('/admin/community-takes/queue', methods=['GET'])
@require_admin
def curation_queue():
    """Admin: View pending submissions and scraped takes"""
    status = request.args.get('status', 'pending')

    submissions = QuickTakeSubmission.query.filter_by(status=status)\
        .order_by(QuickTakeSubmission.created_at.desc()).limit(50).all()

    takes = CommunityTake.query.filter_by(status=status)\
        .order_by(CommunityTake.created_at.desc()).limit(50).all()

    return jsonify({
        'submissions': [{
            'id': s.id,
            'type': 'submission',
            'content': s.content,
            'submitter_name': s.submitter_name,
            'player_id': s.player_id,
            'player_name': s.player.name if s.player else None,
            'created_at': s.created_at.isoformat()
        } for s in submissions],
        'takes': [{
            'id': t.id,
            'type': 'scraped',
            'content': t.content,
            'source_author': t.source_author,
            'source_platform': t.source_platform,
            'source_url': t.source_url,
            'player_id': t.player_id,
            'player_name': t.player.name if t.player else None,
            'upvotes': t.upvotes,
            'created_at': t.created_at.isoformat()
        } for t in takes]
    })


@community_bp.route('/admin/submissions/<int:id>/approve', methods=['POST'])
@require_admin
def approve_submission(id):
    """Admin: Approve a quick take submission"""
    submission = QuickTakeSubmission.query.get_or_404(id)

    if submission.status != 'pending':
        return jsonify({'error': 'Already reviewed'}), 400

    # Create CommunityTake from submission
    take = CommunityTake(
        source_type='submission',
        source_author=submission.submitter_name or 'Anonymous',
        content=submission.content,
        player_id=submission.player_id,
        status='approved',
        curated_by=g.current_user.id if hasattr(g, 'current_user') else None,
        curated_at=datetime.utcnow()
    )

    submission.status = 'approved'
    submission.reviewed_at = datetime.utcnow()

    db.session.add(take)
    submission.community_take = take
    db.session.commit()

    return jsonify({'message': 'Approved', 'take_id': take.id})


@community_bp.route('/admin/submissions/<int:id>/reject', methods=['POST'])
@require_admin
def reject_submission(id):
    """Admin: Reject a quick take submission"""
    submission = QuickTakeSubmission.query.get_or_404(id)
    data = request.get_json() or {}

    submission.status = 'rejected'
    submission.reviewed_at = datetime.utcnow()
    submission.rejection_reason = data.get('reason')

    db.session.commit()

    return jsonify({'message': 'Rejected'})


@community_bp.route('/admin/takes/<int:id>/approve', methods=['POST'])
@require_admin
def approve_take(id):
    """Admin: Approve a scraped community take"""
    take = CommunityTake.query.get_or_404(id)

    take.status = 'approved'
    take.curated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'message': 'Approved'})


@community_bp.route('/admin/takes/<int:id>/reject', methods=['POST'])
@require_admin
def reject_take(id):
    """Admin: Reject a scraped community take"""
    take = CommunityTake.query.get_or_404(id)

    take.status = 'rejected'
    take.curated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'message': 'Rejected'})
```

**Acceptance:** Admin can view queue, approve/reject items

---

#### Task 2.5-2.8: Frontend Implementation

**Create `loan-army-frontend/src/pages/admin/CurationDashboard.jsx`:**

Basic structure:
- Fetch `/admin/community-takes/queue`
- Display submissions and scraped takes in cards
- Approve/Reject buttons
- Filter by status (pending/approved/rejected)

**Create `loan-army-frontend/src/components/QuickTakeForm.jsx`:**

Basic structure:
- Player selector (dropdown or search)
- Textarea for take (max 500 chars, show counter)
- Optional name/email fields
- Submit button
- Success/error feedback

**Integrate into newsletter:**
- In newsletter template, add "Community Takes" section
- Fetch approved takes for each player
- Display with attribution

**Add submission link to newsletter footer:**
- Link to `/submit-take?player={player_id}` or embed form

---

### Phase 3: Reddit Integration

> Detailed in ACADEMY_WATCH_REFACTOR_PLAN.md
> Key: Use PRAW library, map subreddits to teams, scrape comments mentioning players

---

### Phase 4: Academy Tracking

> Detailed in ACADEMY_WATCH_REFACTOR_PLAN.md
> Key: Create AcademyLeague model, sync youth fixtures, track from lineups/events

---

## Quality Checklist

Before marking ANY task complete:

- [ ] Code compiles without errors
- [ ] `pnpm lint` passes (frontend)
- [ ] `pnpm test:e2e` passes (or obsolete tests removed)
- [ ] Backend starts without errors
- [ ] No console errors in browser
- [ ] Ledger updated with task status

---

## Common Patterns

### Adding a new API endpoint
1. Add route in appropriate `routes/*.py` file
2. Add API method in `loan-army-frontend/src/lib/api.js`
3. Test with curl or Postman before frontend integration

### Adding a new database model
1. Add class in `models/league.py` or `models/weekly.py`
2. Create migration: `flask db migrate -m "description"`
3. Review migration file for correctness
4. Run: `flask db upgrade`
5. Test: Insert and query a record

### Adding a new admin page
1. Create page in `src/pages/admin/`
2. Add route in `App.jsx`
3. Add navigation link in `AdminLayout.jsx` sidebar

---

## Emergency Rollback

If something breaks badly:

```bash
# Database rollback
cd loan-army-backend
flask db downgrade

# Git rollback
git stash
git checkout main
```

---

## Contact / Escalation

If blocked on:
- **Architecture decisions** → Update ledger with question, mark task `blocked`
- **API-Football data issues** → Check documentation, log findings in ledger
- **Test failures you can't resolve** → Document in ledger, continue with other tasks

---

## Success = Phase 1 Complete

The minimum viable refactor is **Phase 1 done**:
- Stripe removed
- Writer recruitment removed
- Rebranded
- Tests passing

Phases 2-4 can be done incrementally after launch.
