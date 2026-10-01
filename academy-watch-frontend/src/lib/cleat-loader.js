// Boot splash and React loader share these exact, request-free SVG/CSS primitives.
export const CLUB_PALETTE = Object.freeze([
  { fill: '#0F3D2E', accent: '#0F3D2E' },
  { fill: '#7A1426', accent: '#7A1426' },
  { fill: '#1F3E73', accent: '#1F3E73' },
  { fill: '#0B0E0D', accent: '#CFAE62' },
  { fill: '#E35D18', accent: '#E35D18' },
  { fill: '#6CACE4', accent: '#6CACE4' },
])
export const CLUB_COLOUR_MS = 1200
const keyframes = [...CLUB_PALETTE, CLUB_PALETTE[0]].map(({ fill, accent }, i) =>
  `${i * 100 / CLUB_PALETTE.length}%{fill:${fill};stroke:${accent}}`).join('')

export const CLEAT_SVG = '<svg viewBox="0 0 144 96" width="144" height="96" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="cleat-body" d="M18 29 Q24 24 31 30 L40 24 Q45 34 54 39 L78 48 Q91 51 110 53 Q126 55 126 66 L126 71 Q106 77 77 76 L18 73 Z"/><path d="M18 29 Q24 24 31 30 L40 24 Q45 34 54 39 L78 48 Q91 51 110 53 Q126 55 126 66 L126 71 Q106 77 77 76 L18 73 Z M19 65 Q59 70 84 69 Q110 70 125 65 M23 74 L23 82 L31 82 L33 74 M47 75 L48 84 L56 84 L58 75 M87 76 L89 84 L97 84 L99 75 M112 74 L113 81 L120 81 L122 72 M36 34 L44 31 M43 40 L52 36 M52 45 L61 41 M62 49 L71 45"/><path class="cleat-accent" d="M34 50 Q53 62 81 59 L95 58 Q78 69 61 65 Q43 62 34 50 Z"/></svg>'

export const CLEAT_CSS = `.cleat-loader{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;width:100%;min-height:160px;color:#0E1311}.dark .cleat-loader,.cleat-loader[data-surface=night]{color:#F3F0E8}.cleat-loader svg{display:block;flex:none}.cleat-body{fill:#0F3D2E;fill-opacity:.18;stroke:none;animation:cleat-clubs ${CLUB_COLOUR_MS * CLUB_PALETTE.length}ms linear infinite}.cleat-accent{fill:#0F3D2E;fill-opacity:.28;stroke:#0F3D2E;animation:cleat-clubs ${CLUB_COLOUR_MS * CLUB_PALETTE.length}ms linear infinite}.cleat-caption{font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.18em;line-height:1.5}@keyframes cleat-clubs{${keyframes}}@media(prefers-reduced-motion:reduce){.cleat-loader .cleat-body,.cleat-loader .cleat-accent{animation:none;fill:#0F3D2E}.cleat-loader .cleat-accent{stroke:#0F3D2E}}`

export const CLEAT_BOOT = `<div class="cleat-loader" role="status" aria-live="polite" aria-label="Loading">${CLEAT_SVG}<span class="cleat-caption" aria-hidden="true">LOADING</span></div>`
