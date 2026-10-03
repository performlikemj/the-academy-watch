// Artwork half of the loader: the CSS with the inline logo layers and the boot splash
// markup. Imported only by scripts/sync-cleat-splash.mjs and tests, never by app code:
// index.html carries this CSS once, request-free, for the splash and every React loader.
import { LOGO_LAYERS, LOGO_PIXEL_SIZE } from './academy-watch-logo.js'
import { CLEAT_MARK, CLUB_COLOUR_MS, CLUB_PALETTE, CLUB_TRANSITION_MS, INK } from './cleat-loader.js'

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

export const CLEAT_CSS = `.cleat-loader{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;width:100%;min-height:160px;color:${INK}}.dark .cleat-loader,.cleat-loader[data-surface=night]{color:#F3F0E8}.cleat-mark{position:relative;display:block;flex:none;width:${LOADER_WIDTH}px;height:${LOADER_HEIGHT}px}.cleat-mark>span{position:absolute;inset:0}.cleat-art{background:url(${LOGO_LAYERS.art}) 0 0/100% 100% no-repeat}.cleat-boot{background-color:${INK};${mask(LOGO_LAYERS.boot)}}.cleat-shade{background-color:${still.body};${mask(LOGO_LAYERS.shade)};animation:cleat-clubs ${cycleMs}ms ease infinite}.cleat-light{background-color:#FFFFFF;${mask(LOGO_LAYERS.light)}}.cleat-trim{background-color:${still.trim};${mask(LOGO_LAYERS.trim)};animation:cleat-trim ${cycleMs}ms ease infinite}.dark .cleat-loader .cleat-mark,.cleat-loader[data-surface=night] .cleat-mark{filter:${rimFilter}}.cleat-loader[data-surface=chalk]{color:${INK}}.cleat-loader[data-surface=chalk] .cleat-mark{filter:none}.cleat-caption{font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.18em;line-height:1.5}@keyframes cleat-clubs{${paletteFrames('body')}}@keyframes cleat-trim{${paletteFrames('trim')}}@media(prefers-reduced-motion:reduce){.cleat-loader .cleat-shade,.cleat-loader .cleat-trim{animation:none}}`

export const CLEAT_BOOT = `<div class="cleat-loader" role="status" aria-live="polite" aria-label="Loading">${CLEAT_MARK}<span class="cleat-caption" aria-hidden="true">LOADING</span></div>`
