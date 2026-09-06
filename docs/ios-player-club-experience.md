# Player and club experience

The iOS Home tab gives players, coaches/clubs, and scouts/supporters a starting point that matches their task. The choice is a local navigation preference; it never changes account roles or permissions. Existing Scout Desk, Watchlist, Lists, and Account remain available.

Players can return to **Home → My profiles** or **Account → My profiles** throughout claim review. Approved profile owners can edit their bio, positions, preferred foot, and height; submit a photo or YouTube highlight; and use the system share sheet for an eligible public adult profile. Pending and inactive claims explain their next step and link to the existing web verification/support flow.

Player search checks the tracked and worldwide directories together before offering profile creation. Self-claims require adult age evidence before submission. Age details appear before optional profile fields, and validation dismisses the keyboard and scrolls missing name/age details into view. Exact dates use the entered calendar day against the backend's UTC-day boundary; a year alone must establish adulthood conservatively. Guardian/agent relationships remain distinct and do not become self-claims.

## Club workflow

- Coaches use **Home → My club** for verification and the web club workspace. Web sign-in uses the same email; iOS credentials are never placed in a URL.
- Approved adult players review invitations in **Home → Club invitations**, with explicit accept/decline and leave confirmations.
- **My profiles → [profile] → Coach feedback** lists private feedback, opens the current permitted revision, and lets the player explicitly acknowledge reading it.
- Invitation and feedback APIs retain their existing `PILOT_CLUB_RELATIONSHIPS_ENABLED` gate. Disabled/unavailable states are shown honestly. No production flags are changed by this work.
- Full roster, match/video management, feedback authoring, advanced profile details, and reel ordering remain in the web console.

## API change

`PATCH /api/players/<positive-id>/showcase/profile` and `PATCH /api/local-players/<local-id>/showcase/profile` accept a nonempty subset of `bio`, `positions`, `preferred_foot`, and `height_cm`. Explicit null clears nullable fields. The existing approved-owner gate, validation, moderation, and trust-tier approval rules apply. All other fields—including web-managed contract/agent details and staged private attestations—are preserved. Existing PUT behavior is unchanged. Deploy this additive backend change before distributing the new binary; no migration is required.

Native owner media calls use `local-players/<positive-local-id>` for local identities. Invitation/feedback APIs retain signed player IDs and cursor pagination. Protected rows clear on lost access; private feedback is never passed to a share sheet.

## Photos and release metadata

The system Photos picker grants access to the selected image only. The app creates a metadata-free JPEG, downsampled to 1,600 pixels and capped at 5 MiB, then uses the existing private upload → completion → moderation pipeline. Uploads use a separate ephemeral session, no account token/cookies, no redirects, and HTTPS Azure Blob destinations. Upload completion is tied to the account that started it. Failed uploads attempt to remove only their own newly created slot; an incomplete slot can also be deleted in the photo list.

The privacy manifest adds Photos or Videos (linked to the account, app functionality, no tracking) and the app-only UserDefaults access reason. Before the next App Store submission, update the corresponding App Store Connect photo disclosure. This branch does not alter store metadata or submit a release. PhotosPicker and manifest declarations follow [Apple's Photos picker documentation](https://developer.apple.com/documentation/photosui/photospicker) and [privacy-manifest data types](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacycollecteddatatypes/nsprivacycollecteddatatype).

`project.yml` now explicitly preserves `CFBundleShortVersionString = $(MARKETING_VERSION)` through XcodeGen. Choose the release version/build through the usual release workflow.

## Verification

Run from `academy-watch-ios`:

```sh
xcodegen generate
xcodebuild -project AcademyWatch.xcodeproj -scheme AcademyWatch -destination 'platform=iOS Simulator,name=iPhone 17' test
xcodebuild -project AcademyWatch.xcodeproj -scheme AcademyWatchExperience -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:AcademyWatchUITests/PlayerClubExperienceUITests test
```

`AcademyWatchExperience` is an offline scheme with explicit `-experienceFixture` data and labeled screenshots. All API requests are intercepted; unknown paths fail locally. It uses an ephemeral token store and sends no login email, media upload, or production mutation. The existing `AcademyWatchUISmoke` scheme remains a separate live test that sends login email; it was not run for this change.

The initial pilot still needs a real App Store-installed device walkthrough after deployment and a later-week return from participants. This implementation does not introduce a full youth-consent workflow, automatic acceptance from shared links, push notifications, or native match/video authoring.
