# Video Analysis — research artifacts (2026-06-10)

Raw outputs from the multi-agent research/design/critique workflow that produced
`ledgers/CONTINUITY_video-analysis.md`. **That ledger is the authoritative, corrected design** —
`draft.md` here is the pre-critique draft and contains known errors the critiques caught
(the $8 floor-price arithmetic, "tens of MB" preview-storage estimate, public video-reports
endpoint, jersey OCR in Phase C). Kept for provenance: verified repo licenses, 2026 Azure GPU
pricing with sources, and the codebase recon are expensive to regenerate.

- `recon_repoResearch.json` — OSS football-CV landscape, licenses verified per repo
- `recon_infraResearch.json` — GPU infra options, pricing, upload/storage, billing patterns
- `recon_plumbing.json` — codebase integration recon (jobs, uploads, auth, Stripe state)
- `recon_models.json` — data-model recon (TrackedPlayer, stats models, migration conventions)
- `draft.md` — pre-critique architecture draft (superseded)
- `critique_feasibility.json` / `critique_product.json` — adversarial reviews; their required
  changes are folded into the ledger
