# DEPS security dependencies

- Goal: one ready, unmerged PR to main; #1089 stays open. #1101 / #1100 are only partly covered and stay open for Dependabot to regroup.
- Branch/base: chore/deps-security / 66e85b2e.
- Source scope complete: hand-edited runtime requirements (2 pins), spike requirements (3 pins), surgical frontend lock (3 package entries); no application changes.
- Pydantic pair retained at 2.13.5 / 2.46.5; all Linux/runtime pins preserved; no regeneration.
- Frontend routine patch bumps, not security fixes: react-router-dom + react-router 7.18.3 → 7.18.4, eslint-plugin-react-refresh 0.5.6 → 0.5.7. Original package.json/ranges unchanged; no unrelated lock churn.
- Other #1100/#1101 non-security group updates intentionally omitted to minimize scope.
- Done: required guidance; all 12 open alerts; OSV/setup PASS (547 packages); Python 3.11 fresh resolver PASS; fresh import PASS; GOL RestrictedPython analysis + refusals PASS.
- PDF decision: reviewed official 70 changelog; rendered actual newsletter and GOL PDFs from repo templates with bundled fonts and offline fixtures at 69/70. Same text, links, page sizes and pixels; visual parity already shown. Advisory not reachable at either production call site; upgrade to 70.0 deferred to a follow-up.
- Final verification/delivery state, gate keys, exact SHA, PR, per-check CI and cleanup are recorded in the external hand-back `~/codex-runs/aw-redesign/logs/DEPS.final.md`; this file retains the source decisions so final-head gates remain reusable.
- Constraints: no shared/staging venv changes; governor foreground only; no features/refactors, no merge or closing #1089/#1101/#1100.

| Alert / advisory | Package / manifest | Severity | Use | Disposition |
| --- | --- | --- | --- | --- |
| #11 GHSA-vxq7-64xx-v4gw | urllib3, spike/video-analysis/ball/requirements.txt | HIGH | Runtime: offline analysis HTTP downloads; outside web image | FIXED 2.7.0 → 2.8.0 |
| #10 GHSA-8988-9cw3-xx77 | urllib3, spike/video-analysis/ball/requirements.txt | HIGH | Runtime: offline analysis HTTP/proxy requests; outside web image | FIXED 2.7.0 → 2.8.0 |
| #8 GHSA-vxq7-64xx-v4gw | urllib3, academy-watch-backend/requirements.txt | HIGH | Runtime: requests/API and download clients | FIXED 2.7.0 → 2.8.0 |
| #7 GHSA-8988-9cw3-xx77 | urllib3, academy-watch-backend/requirements.txt | HIGH | Runtime: requests/API and proxy clients | FIXED 2.7.0 → 2.8.0 |
| #6 GHSA-hp3v-5vw7-fx9w | RestrictedPython, academy-watch-backend/requirements.txt | HIGH | Runtime: services/gol_sandbox.py executes generated pandas analysis | FIXED 8.3 → 8.5 (first fix 8.4); real analysis + denied format/import checks pass |
| #5 GHSA-6v4j-43gg-vj32 | yt-dlp, spike/video-analysis/requirements.txt | HIGH | Runtime: offline download_footage.py CLI; outside web image | FIXED 2026.6.9 → 2026.7.4; current commands use --write-info-json, not --write-link |
| #12 GHSA-gh4c-6fx4-qh6g | urllib3, spike/video-analysis/ball/requirements.txt | MODERATE | Runtime: offline analysis response streaming; outside web image | FIXED 2.7.0 → 2.8.0 |
| #9 GHSA-gh4c-6fx4-qh6g | urllib3, academy-watch-backend/requirements.txt | MODERATE | Runtime: requests/API response streaming | FIXED 2.7.0 → 2.8.0 |
| #3 GHSA-76hw-p97h-883f | gdown, spike/video-analysis/requirements.txt | MODERATE | Runtime: offline Drive folder downloads; outside web image | FIXED 5.2.0 → 5.2.2; CLI smoke passes; current wrapper does not call extractall |
| #1 GHSA-jf6q-chmf-3h3v | weasyprint, academy-watch-backend/requirements.txt | MODERATE | Runtime: newsletter and GOL PDF exports in services/pdf_renderer.py | NOT REACHABLE (both production call sites call `write_pdf()` with no arguments and set no `url_fetcher`); upgrade to 70.0 deferred to a follow-up — visual parity already shown |
| #4 GHSA-rrmf-rvhw-rf47 | torch, spike/video-analysis/requirements.txt | LOW | Runtime: offline GPU RF-DETR spike; outside web image | DEFERRED 2.12.0 → 2.13.0: GPU/model compatibility not established here; repo's optional inference uses torch.jit.trace, not the advisory's torch.jit.script. No claim of transitive unreachability. |
| #2 GHSA-rrmf-rvhw-rf47 | torch, spike/video-analysis/docker/requirements-docker.txt | LOW | Runtime: offline GPU worker image; outside web image | DEFERRED 2.12.0 → 2.13.0: same RF-DETR/CUDA compatibility constraint; separate GPU validation needed. |

## DEPSR refresh

- Done: merged main c7d3e962; only CONTINUITY.md conflicted, both histories retained. All four dependency manifests must remain byte-identical to reviewed bba8c28e.
- Verification attribution: the full backend suite on the NEW versions is the GitHub **Backend Tests** job; the local cached backend gate uses a shared venv with the old versions and does not validate the bumped pins.
- Done: fresh `/tmp/DEPSR-venv` Python 3.11.16 exact-requirements install and pip check PASS; urllib3 2.8.0 / RestrictedPython 8.5 / Pydantic 2.13.5 + core 2.46.5 confirmed. Governed targeted GOL / API-client / PDF-related tests 83 PASS; existing sandbox analysis/refusal probe PASS. Temporary venv deleted.
- Delivery: final-head cached gates, push and bounded GitHub CI verification recorded in the external hand-back; GitHub Backend Tests is required SUCCESS on the refreshed head. No merge.
- Final refreshed-head validation, pushed SHA, per-check CI and cleanup: `~/codex-runs/aw-redesign/logs/DEPSR.final.md`.
