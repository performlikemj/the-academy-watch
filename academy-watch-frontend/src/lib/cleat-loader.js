import { LOGO_LAYERS, LOGO_PIXEL_SIZE } from './academy-watch-logo.js'

// Boot splash and React loader share these exact, request-free markup/CSS primitives.
// The logo is the real app-icon artwork (see scripts/build-loader-logo.py): the wing keeps
// its own white pixels; only the boot is recoloured along the icon's own shading: `body`
// where the icon is white (plus its white highlights), `detail` on the lace slots/seams.
export const CLUB_PALETTE = Object.freeze([
  { name: 'green', body: '#0F3D2E', detail: '#0E1311' },
  { name: 'claret', body: '#7A1426', detail: '#0E1311' },
  { name: 'navy', body: '#1F3E73', detail: '#0E1311' },
  { name: 'black-gold', body: '#0B0E0D', detail: '#CFAE62' },
  { name: 'orange', body: '#E35D18', detail: '#0E1311' },
  { name: 'sky', body: '#6CACE4', detail: '#0E1311' },
])
export const CLUB_COLOUR_MS = 1200
export const CLUB_TRANSITION_MS = 200
export const LOADER_WIDTH = 144
export const LOADER_HEIGHT = Math.round(LOADER_WIDTH * LOGO_PIXEL_SIZE.height / LOGO_PIXEL_SIZE.width)
const cycleMs = CLUB_COLOUR_MS * CLUB_PALETTE.length
const [still] = CLUB_PALETTE
// Light keyline drawn around the mark on dark surfaces, so a boot whose club colour
// matches the page (navy on a navy club console, black on night) never disappears.
const RIM = 'rgba(243,240,232,.92)'
const rimFilter = ['1px 0', '-1px 0', '0 1px', '0 -1px'].map(offset => `drop-shadow(${offset} 0 ${RIM})`).join(' ')

// Hold each colour for 1s, then ease into the next over 200ms. Six 1.2s phases.
function paletteFrames(property) {
  return CLUB_PALETTE.flatMap((colour, i) => [i * CLUB_COLOUR_MS, (i + 1) * CLUB_COLOUR_MS - CLUB_TRANSITION_MS]
    .map(time => `${time * 100 / cycleMs}%{background-color:${colour[property]}}`)).join('') + `100%{background-color:${still[property]}}`
}
// Each mask image is written once (a custom property) and used by both mask syntaxes.
const mask = url => `--cleat-mask:url(${url});-webkit-mask:var(--cleat-mask) 0 0/100% 100% no-repeat;mask:var(--cleat-mask) 0 0/100% 100% no-repeat`

export const CLEAT_MARK = `<span class="cleat-mark" aria-hidden="true" data-brand-logo="academy-watch-winged-boot"><span class="cleat-art" data-brand-part="art"></span><span class="cleat-boot" data-brand-part="boot"></span><span class="cleat-shade" data-brand-part="shade"></span><span class="cleat-light" data-brand-part="light"></span></span>`

export const CLEAT_CSS = `.cleat-loader{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;width:100%;min-height:160px;color:#0E1311}.dark .cleat-loader,.cleat-loader[data-surface=night]{color:#F3F0E8}.cleat-mark{position:relative;display:block;flex:none;width:${LOADER_WIDTH}px;height:${LOADER_HEIGHT}px}.cleat-mark>span{position:absolute;inset:0}.cleat-art{background:url(${LOGO_LAYERS.art}) 0 0/100% 100% no-repeat}.cleat-boot{background-color:${still.detail};${mask(LOGO_LAYERS.boot)};animation:cleat-detail ${cycleMs}ms ease infinite}.cleat-shade{background-color:${still.body};${mask(LOGO_LAYERS.shade)};animation:cleat-clubs ${cycleMs}ms ease infinite}.cleat-light{background-color:#FFFFFF;${mask(LOGO_LAYERS.light)}}.dark .cleat-loader .cleat-mark,.cleat-loader[data-surface=night] .cleat-mark{filter:${rimFilter}}.cleat-loader[data-surface=chalk]{color:#0E1311}.cleat-loader[data-surface=chalk] .cleat-mark{filter:none}.cleat-caption{font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.18em;line-height:1.5}@keyframes cleat-clubs{${paletteFrames('body')}}@keyframes cleat-detail{${paletteFrames('detail')}}@media(prefers-reduced-motion:reduce){.cleat-loader .cleat-boot,.cleat-loader .cleat-shade{animation:none}}`

export const CLEAT_BOOT = `<div class="cleat-loader" role="status" aria-live="polite" aria-label="Loading">${CLEAT_MARK}<span class="cleat-caption" aria-hidden="true">LOADING</span></div>`

// Nearest painted ancestor decides whether the loader sits on a dark surface (night,
// dark theme, or a club console painted in the club's own colour).
export function detectSurface(element) {
  for (let node = element?.parentElement; node; node = node.parentElement) {
    const match = getComputedStyle(node).backgroundColor.match(/rgba?\(([^)]+)\)/)
    if (!match) continue
    const [r, g, b, a = 1] = match[1].split(/[\s,/]+/).filter(Boolean).map(Number)
    if (a < 0.5) continue
    const lum = [r, g, b].map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] < 0.18 ? 'night' : 'chalk'
  }
  return undefined
}
