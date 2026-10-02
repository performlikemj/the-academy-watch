# N6 — loader is the logo

- Goal: restore existing Academy Watch winged-boot geometry to React loader and request-free inline splash.
- Status: implementation complete; branch fix/loader-is-the-logo from main919be8af, fast-forwarded to eddba4ac.
- Constraints: frontend only; no picker/dependency changes; foreground governed heavy commands; no wing movement; A default (neutral wing), B comparison (cycling wing), single constant switch.
- Evidence: DESIGN §3 and BUS15:53 correction read; Swift generator extracts favicon crop, has no vector geometry. Trace LaunchBootBody/WingA/WingB; measure vs LaunchBoot@3x at600px.
- Done: OSV547 clean; frozen frontend dependencies restored, lockfile unchanged.
- Done: pixel contour trace of unchanged600px LaunchBoot brand source; neutral still wing A, cycling still wing B, original sole as gold accent; tiny adaptive stroke follows existing boot contour for black/night visibility.
- Done: targeted Node5 pass; browser parity/phase/reduced-motion/CSP proof specs prepared; existing picker test bodies unchanged; fixture now answers main’s shared /api/features bootstrap.
- Proof:600px IoU0.9810617279648762; white-ink mask difference0.30194444%canvas/1.89382720%union; no registration/warp. Overlay, metrics/scripts and84A/B+4splash PNGs in shots/N6; four contact sheets reviewed.
- Initial verification27dd36b0: cached Node299/lint0errors192inherited warnings/build pass; browser17pass16fixture failures (main changed bootstrap to /api/features, fixture answered old endpoint only). No picker implementation changes.
- Now: final-head gates/browser delivery tracked in `~/codex-runs/aw-redesign/logs/N6.final.md`; this external delivery ledger is updated with exact receipts, SHA/PR and cleanup.
- Typecheck: JavaScript project has no standalone typecheck; governed Vite build checks compilation.
- Audit: original redesign existed only in shared CLEAT_SVG and generated splash; all call sites inherit corrected artwork. Favicons/header/logo/empty states/404/teaser/email/OG contain no additional replacement. Exact inventory logs/N6.inventory.md.
- Next: unit/browser checks, screenshot comparison/index, final-head frontend gates, push/ready PR, external hand-back and cleanup.
