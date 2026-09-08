# A2 review fix round 1

- Base: `3cd3c2989853c8cc7e9f7190e7a8e7f85e125678`; one follow-up commit, push, no PR/merge.
- Scope: iOS app and this proof directory only. Master CONTINUITY.md intentionally unchanged per user path constraint.
- State: all six findings addressed; production app source unchanged; fresh GREEN and reproducible RED retained. Final committed-byte validation and push are performed after this ledger is committed; the handback records the resulting SHA.
- B2 plan: source-tree equivalence, deterministic config digest; proof on an immutable source snapshot, final commit includes identical app tree plus evidence.
- Gates: units 206/206, GREEN 43/43, archived strict GREEN/RED, required GREEN stories at source snapshot, story-map check and binding regression pass. Final HEAD gates are reproducible with verify-committed.sh.

- Unit gate: 206 tests, 0 failures; TEST SUCCEEDED.
- B2: source/config certificate regression PASS, including a fresh clone without the original source commit; changed source, dirty source, missing digest and tampering rejected. Shared harness unchanged; upstream candidate documented in app sim/README.md and PACK_SOURCE.
- M1: both cited original PNGs visibly show Home title and selected Home tab. Strengthened runner on unchanged production app passes 16/16. No persistent UX bug reproduced; treated as assertion/capture hardening (i), but the alleged timing failure itself was not reproduced. App routing code unchanged.
- M2: actual My club tap plus destination Club verification assertion added.
- m1: named player-club-home-content-absent assertion added to scout journey and inventory.
- GREEN source snapshot: unpushed `88f013a`; final one follow-up commit will include identical app tree plus fresh evidence. Only this session's unpushed commit is amended; published history stays intact.
- RED setup deviations: first host preflight rejected dynamically constructed choice IDs; explicit equivalent IDs added. XcodeGen was absent from PATH; used the existing downloaded binary, regenerated the RED scheme after an empty execution was correctly rejected. Neither failed setup is used as behavioral RED evidence.

- GREEN full: 43/43 steps, 6 proven, 0 unproven/failing, all 43 original screenshots retained. Archived strict exit 0; both required stories exit 0 at source snapshot.
- B1: removed incomplete green-10f05d5 and replaced it with green-88f013a; RED replaced with all 20 original referenced screenshots and exact overlay provenance.

- M3: RED rebuilt from clean 292d5912 plus instrumentation.patch. Apply check/apply exit 0; build and test execution exit 0; full host exit 0 with 20 steps / 17 successful / 3 intended behavioral failures. Required stories fail at home-absent-before-change and scout-desk-selected; the third baseline failure is scout-search-player-detail at scroll-to-search.
- Both archived bundles pass strict with matching current journey hashes/inventory. All 63 screenshots retain original bytes; no downscaling.
- Per-item references: B1 green-88f013a/report.json and red-292d5912/report.json; B2 sim/ios-proof-binding.mjs and sim/run.sh; M1 JourneyRunnerUITests.swift plus M1-determination.md; M2 club-my-club journey and inventory; M3 red-292d5912/instrumentation.patch, apply-result.txt, applied-source-sha256.json and build-result.json; m1 scout-opens-app journey and inventory.
- Deliberate deviations: M1's screenshot description is contradicted by direct PNG inspection; neither timing failure nor persistent UX glitch was reproduced. Applied stronger assertion/capture checks, without changing app routing. The harness shared assembler was not edited; the local extension is documented for upstream. Only this session's unpushed follow-up commit is amended to add evidence, leaving exactly one commit above 3cd3c29.
- Cleanup: detached RED worktree removed after verifying patch/applied-source equality; no booted simulators remain. Session-owned temporary build/report artifacts are removed after final push verification.
