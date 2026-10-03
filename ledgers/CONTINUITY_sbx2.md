# Process isolation for the analysis tool

- Goal: second OS boundary after the existing analysis allowlist.
- Constraints: local only; no migration/frontend change; release after #1135; assistant stays under maintenance.
- Base: d9489aee / feat/gol-analysis-isolation.
- Now: implementation and focused verification complete; source freeze for final-head cached gates, ready PR and bounded CI.
- Next: final-head four cached gates; ready PR/25min CI; cleanup and external hand-back.
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
