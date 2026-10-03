# N7 — loader uses the real app logo artwork

- Goal (loanarmy-ca BUS 2026-10-03 08:38): MJ said the N6 loader "was the newly redesigned one and not my app's logo". N6 traced the boot's outline into a flat vector with a solid fill; it must LOOK like the icon side by side.
- Branch/PR: fix/loader-real-logo from main 58ccb8c6; PR titled `fix(ui): loader uses the real app logo artwork`; no merge by this lane.
- Master: no vector master exists. `academy-watch-ios/scripts/generate_brand_assets.swift` only crops/upscales `public/assets/loan_army_assets/favicon-512x512.png` into AppIcon-1024 and luma-keys it into LaunchBoot; LaunchBootBody/WingA/WingB are flap slices of the same raster. The favicon is the master.
- Done: `academy-watch-frontend/scripts/build-loader-logo.py` (Pillow + numpy, `.loan` venv) builds four WebP layers at 3x of 144 CSS px: art (real pixels), boot mask, shade (boot luminance -> club colour), light (icon highlights, white). Wing = the master's two bright wing pieces, never tinted. Black-gold paints the lace slots/seams gold.
- Done: CleatLoader auto-detects a dark painted ancestor (navy club console, night) and adds a light 1px rim; explicit `surface` wins. Caption stays ink on chalk panels under the dark theme (N6 bug).
- Done: N6 trace/verify scripts removed; splash re-synced (index.html 20.9 KB -> 59.7 KB, all inline, no request).
- Tests: Node `src/lib/cleat-loader.test.js`; Playwright `e2e/loader-logo.spec.mjs` probes real rendered pixels (wing white in every phase/easing midpoint, body = club colour, lace slots dark/gold, >400 colours = not flat), Reduce Motion still frame, request-free splash, rim/surface detection. Proof images with `N7_SCREENSHOTS=<dir>`.
