# Floodlight offline review

DEBUG + iOS Simulator only. Launch with `-floodlightPreview <screen>`.
All API requests resolve locally or fail closed; mutations and unknown paths
are rejected, authentication uses an ephemeral token store, and review scout
responses bypass the persistent cache. App startup does not warm the live API.
The unobtrusive overlay labels every image as an offline generic fixture.

Screens: chooser, home, club-home, my-club, scout, scout-empty, scout-error,
loading, player, player-error, season, showcase, compare, watchlist,
watchlist-empty, watchlist-error, lists, lists-empty, list-detail, introduction,
introductions, introductions-empty, incoming, thread, gol, gol-answer,
player-onboarding, create-profile, worldwide, club-onboarding, profiles,
profile-editor, invitations, feedback, development, auth, account,
account-signed-out, verification, blocked, legal, report, removal, add-game.

The views and navigation are the existing production views. Fixture data uses
Sample Player/Member/Academy/Club labels and no personal photos. The JSON schema
examples derive from native decoding tests; the experience fixture supplies
synthetic private feedback and season data. Legal pages and club console retain
their existing Safari handoff; `legal` reviews their native links.

Review images: `~/codex-runs/aw-redesign/shots/ios/INDEX.md`. Baselines use the
same harness over the pinned origin/main iOS sources, without Floodlight assets,
fonts or view restyles. See `sim/capture-floodlight.py` to reproduce the capture.
