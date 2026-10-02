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
export const CLUB_TRANSITION_MS = 200
const cycleMs = CLUB_COLOUR_MS * CLUB_PALETTE.length
// Hold each colour for 1s, then ease into the next over 200ms. Six 1.2s phases.
function paletteFrames(properties) {
  return CLUB_PALETTE.flatMap((colour, i) => [i * CLUB_COLOUR_MS, (i + 1) * CLUB_COLOUR_MS - CLUB_TRANSITION_MS]
    .map(time => `${time * 100 / cycleMs}%{${properties(colour)}}`)).join('') + `100%{${properties(CLUB_PALETTE[0])}}`
}
const upperFrames = paletteFrames(({ fill }) => `fill:${fill}`)
const accentFrames = paletteFrames(({ accent }) => `fill:${accent}`)
const laceFrames = paletteFrames(({ fill }) => `stroke:${['#E35D18', '#6CACE4'].includes(fill) ? '#0E1311' : '#F3F0E8'}`)

// Low collar with an open ankle dip, tapered right-facing toe, instep laces and five blades.
export const CLEAT_SVG = '<svg viewBox="0 0 144 96" width="144" height="96" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="cleat-body" d="M20 47 Q20 43 25 44 L29 46 Q38 52 45 44 L50 41 Q54 39 58 43 L67 50 Q82 57 112 57 Q125 58 129 64 Q132 69 125 71 Q96 75 70 73 L20 72 Q17 62 20 47 Z"/><path class="cleat-accent" stroke="none" d="M22 58 L33 58 L39 66 L21 65 Z"/><path class="cleat-details" d="M23 47 Q34 56 46 46 M49 48 L59 45 M55 52 L65 49 M63 55 L72 52 M71 58 L80 55"/><path d="M20 47 Q20 43 25 44 L29 46 Q38 52 45 44 L50 41 Q54 39 58 43 L67 50 Q82 57 112 57 Q125 58 129 64 Q132 69 125 71 Q96 75 70 73 L20 72 Q17 62 20 47 Z M20 67 Q61 71 89 70 Q113 70 130 66 M20 72 L20 76 Q74 80 104 77 L127 73 L129 69 M25 77 L25 84 L32 84 L34 77 M47 78 L48 85 L55 85 L57 78 M72 79 L73 85 L80 85 L82 79 M97 78 L98 84 L105 84 L107 77 M118 75 L119 81 L125 81 L126 74"/></svg>'

export const CLEAT_CSS = `.cleat-loader{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;width:100%;min-height:160px;color:#0E1311}.dark .cleat-loader,.cleat-loader[data-surface=night]{color:#F3F0E8}.cleat-loader svg{display:block;flex:none}.cleat-body{fill:#0F3D2E;stroke:none;animation:cleat-clubs ${cycleMs}ms ease infinite}.cleat-accent{fill:#0F3D2E;animation:cleat-accent ${cycleMs}ms ease infinite}.cleat-details{stroke:#F3F0E8;animation:cleat-laces ${cycleMs}ms ease infinite}.cleat-caption{font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.18em;line-height:1.5}@keyframes cleat-clubs{${upperFrames}}@keyframes cleat-accent{${accentFrames}}@keyframes cleat-laces{${laceFrames}}@media(prefers-reduced-motion:reduce){.cleat-loader .cleat-body,.cleat-loader .cleat-accent{animation:none;fill:#0F3D2E}.cleat-loader .cleat-details{animation:none;stroke:#F3F0E8}}`

export const CLEAT_BOOT = `<div class="cleat-loader" role="status" aria-live="polite" aria-label="Loading">${CLEAT_SVG}<span class="cleat-caption" aria-hidden="true">LOADING</span></div>`
