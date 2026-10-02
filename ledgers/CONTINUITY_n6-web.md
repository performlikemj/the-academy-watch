# N6 — loader is the logo

- Goal: restore existing Academy Watch winged-boot geometry to React loader and request-free inline splash.
- Status: in-progress; branch fix/loader-is-the-logo from main919be8af, fast-forwarded to eddba4ac.
- Constraints: frontend only; no picker/dependency changes; foreground governed heavy commands; no wing movement; A default (neutral wing), B comparison (cycling wing), single constant switch.
- Evidence: DESIGN §3 and BUS15:53 correction read; Swift generator extracts favicon crop, has no vector geometry. Trace LaunchBootBody/WingA/WingB; measure vs LaunchBoot@3x at600px.
- Done: OSV547 clean; frozen frontend dependencies restored, lockfile unchanged.
- Done: pixel contour trace of unchanged600px LaunchBoot brand source; neutral still wing A, cycling still wing B, original sole as gold accent; tiny adaptive stroke follows existing boot contour for black/night visibility.
- Done: targeted Node5 pass; browser parity/phase/reduced-motion/CSP proof specs prepared; existing picker test bodies unchanged.
- Now: final-head gates and one lane browser run; results/metrics in external hand-back.
- Next: unit/browser checks, screenshot comparison/index, final-head frontend gates, push/ready PR, external hand-back and cleanup.
