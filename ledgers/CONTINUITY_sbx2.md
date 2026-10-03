# Process isolation for the analysis tool

- Goal: second OS boundary after the existing analysis allowlist.
- Constraints: local only; no migration/frontend change; release after #1135; assistant stays under maintenance.
- Base: d9489aee / feat/gol-analysis-isolation.
- Now: SBX2F1 review union implemented; reviewed delivery was 0cfbfc3d / ready PR1139, four cached gates and six CI jobs PASS.
- Next: final-head cached gates, push, bounded Linux CI and SBX2F1 hand-back.
- Contract: CONTRACT | SBX2 | One fresh exec child per analysis, env={}, close_fds, three pipes, private temp cwd. Versioned column JSON (base64 fixed numeric buffers and tagged plain object values; no pickle) capped128MiB input/2MiB output; existing restricted executor and formatter run synchronously only after OS policy installs. Linux requires Landlock ABI>=3 + no_new_privs + libseccomp syscall allowlist denying network/process creation/other-process access; macOS requires Seatbelt filesystem/network/process policy. CPU10s, wall deadline parent SIGKILL+wait, address-space cap Linux plus parent RSS cap on both, file-size0/core0/nproc0/nice10. Missing policy -> neutral refusal, never parent execution. Preload analysis-only modules before filesystem lockdown; no Flask/DB imports; helpers use passed frames. Per-call startup and real-schema100k/200k transport measured locally and non-root Docker0.5CPU/1Gi before pool decision. Azure kernel support remains unverified locally and is a release prerequisite; separate credential-free ACA job/container is the stronger infrastructure option. No migration/frontend change. Released after1135; assistant stays under maintenance.

- Milestone: synchronous first-layer executor, plain column transport, Linux Landlock/seccomp and macOS Seatbelt, parent SIGKILL/reap and container-wide memory admission implemented.
- Focused evidence: macOS22 PASS/1Linux-only skip (before string codec/expanded admission controls); Linux17 PASS/1 test fixture correction required (limit snapshot before lockdown). Ordinary corpus178/183 initially; five lazy imports/timezone failures addressed, focused affected cases22 PASS.
- Machine governor: expanded controls and Linux image rebuild queued normally; no command terminated/retried or bypassed.
- Upstream: #1135 merged53127a54; current mainf18abf6b includes player-card changes. Merge main after implementation commit before final gates.

- Targeted: macOS545PASS/2SKIP; two environment-dependent service/SQLite checks corrected with explicit test configuration and2PASS. Native Linux0.5CPU/1GiB220PASS (maintenance checked on macOS and final full CI). Parent DTO controls9PASS. Real PostgreSQL/psycopg ten-frame loader2PASS; owned aw_sbxf2 dropped (count0).
- Performance final JSON: external logs/SBX2/measurements-{linux,macos}.json; Linux medians100k1.211s/200k1.536s, startup0.526s/0.473s; no pool. Final RSS448MiB Linux/640MiB macOS accommodates measured platform allocator differences; LinuxAS768MiB.
- Lifecycle: Linux parent-death SIGKILL plus20s child backup alarm added; Linux disallows handler/mask/timer changes. Final focused lifecycle controls and gates next.

- Final focused lifecycle: macOS31PASS/2Linux-only skips; non-rootLinux0.5CPU/1GiB32PASS, including parent-exit death/reaping. Additional scalar transport checks preserve NumPy precision/type and named timezone semantics. All first-layer capabilities remain unchanged.
- OSV passed before frozen frontend dependency restore; no lockfile/frontend source change.
- Final verification/delivery is recorded externally in `~/codex-runs/aw-redesign/logs/SBX2.final.md`; avoid post-gate repository edits solely for receipts.

- Current main3949cbac integrated; only documentation/ledger conflicts, resolved by preserving all incoming state plus this lane's additions. No own frontend or migration delta. Final implementation commit16f1b5c4; exact delivery-head gates/CI remain authoritative externally.

- SBX2F1 scope: X1/O8 macOS signals; X2 cancellable parent-crash cleanup; X3/O7 temporal fidelity; O1 timezone cache; O2 referenced-frame scope/input limits; O3 readiness and fixed operator signals; O4 stream transport/admission/headroom; O5 formatting preload; O6 deadline/busy hints; O9 temp lookup/empty-dir cleanup/complete hand-back; O10 real failing-policy tests and required Linux CI coverage.
- Decision: production isolation is Linux-only. macOS refuses without a child; a named trusted test helper exercises the first layer/codec only, with no runtime fallback. Linux policy, signals, immutable timers and parent death remain mandatory.
- Decision: admit before cache copies, select conservative AST/helper dependencies, stream column JSON rather than retain a full payload, check cgroup headroom and assign child limits from remaining budget; measure local full-app baseline under the production container envelope.
- Final fix receipts will live in external logs/SBX2F1.final.md and SBX2F1.report.md; repository source freezes before final gates.

- SBX2F1 implementation: Linux-only mandatory policy; streamed referenced-frame transport; temporal fidelity; real cached readiness/health and fixed logs; dynamic cgroup admission; mandatory Linux policy coverage and full-app container-memory CI.
- SBX2F1 targeted: native non-root Linux aarch640.5CPU/1GiB641PASS/0SKIP; macOS portable602PASS/296Linux-or-PostgreSQL skips. Real PostgreSQL loader probe exposed a macOS-only test expectation, corrected to a clearly named trusted codec/reference path; Linux still executes children.
- SBX2F1 measurements: Linux100k/200k bootstrap315/322ms, serialize126/267ms, end-to-end780/1018ms; full Flask preload/two workers/two threads peak739033088bytes, no OOM, two200k row-wise successes/two10s busy refusals. Exact receipts external logs/SBX2F1/.
- SBX2F1 source freeze follows main integration and final focused loader validation; final cached gates/push/CI are recorded externally rather than editing source after gates. No migration/frontend screenshot changes. Production kernel remains UNCONFIRMED; maintenance is unchanged.

- Main e510612a merged (#1135 already included); only AGENTS/CONTINUITY append conflicts, both histories preserved. PostgreSQL expected head inherited verbatim as p2c3; incoming migration/front-end files are unmodified. Own PR diff remains process isolation only. Corrected local PostgreSQL loader2PASS; owned aw_sbxf2 dropped in finally.
