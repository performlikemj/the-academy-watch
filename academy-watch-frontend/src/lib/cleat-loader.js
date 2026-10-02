import { LOGO_PATHS } from './academy-watch-logo.js'

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
// A is the shipped choice. Set to 'B' to colour the still wing as well.
export const LOGO_COLOUR_VARIANT = 'A'
export function logoSvg(variant = LOGO_COLOUR_VARIANT) {
  return `<svg viewBox="54 104 490 330" width="144" height="97" fill="none" aria-hidden="true" data-brand-logo="academy-watch-winged-boot" data-colour-variant="${variant}"><path class="cleat-body" data-brand-part="body" fill-rule="evenodd" d="${LOGO_PATHS.body}"/><path class="cleat-accent" data-brand-part="sole" fill-rule="evenodd" d="${LOGO_PATHS.sole}"/><path class="cleat-wing${variant === 'B' ? ' cleat-body' : ''}" data-brand-part="wing" fill-rule="evenodd" d="${LOGO_PATHS.wing}"/></svg>`
}
export const CLEAT_SVG = logoSvg()

export const CLEAT_CSS = `.cleat-loader{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;width:100%;min-height:160px;color:#0E1311}.dark .cleat-loader,.cleat-loader[data-surface=night]{color:#F3F0E8}.cleat-loader svg{display:block;flex:none}.cleat-body{fill:#0F3D2E;stroke:currentColor;stroke-width:1.5;paint-order:stroke fill;animation:cleat-clubs ${cycleMs}ms ease infinite}.cleat-accent{fill:#0F3D2E;animation:cleat-accent ${cycleMs}ms ease infinite}.cleat-wing:not(.cleat-body){fill:currentColor}.cleat-caption{font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.18em;line-height:1.5}@keyframes cleat-clubs{${upperFrames}}@keyframes cleat-accent{${accentFrames}}@media(prefers-reduced-motion:reduce){.cleat-loader .cleat-body,.cleat-loader .cleat-accent{animation:none;fill:#0F3D2E}}`

export const CLEAT_BOOT = `<div class="cleat-loader" role="status" aria-live="polite" aria-label="Loading">${CLEAT_SVG}<span class="cleat-caption" aria-hidden="true">LOADING</span></div>`
