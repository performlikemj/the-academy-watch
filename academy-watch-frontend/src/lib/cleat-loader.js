// Runtime half of the loader: markup, palette and surface detection. It carries no
// artwork. The CSS with the inline logo layers (cleat-splash.js) ships exactly once, in
// index.html's boot splash <style>, which sits outside #root and so stays in the page
// for every React loader (see scripts/sync-cleat-splash.mjs).
//
// The logo is the real app-icon artwork (scripts/build-loader-logo.py). The wing keeps
// its own white pixels; only the boot is recoloured, along the icon's own shading:
// `body` where the icon is white (plus its white highlights), ink on the lace slots and
// seams in every phase, and `trim` on the boot's outer keyline (gold for black-gold).
// Off-phase trim is the gold at zero alpha, so easing in and out never passes through grey.
const NO_TRIM = 'rgba(207,174,98,0)'
export const CLUB_PALETTE = Object.freeze([
  { name: 'green', body: '#0F3D2E', trim: NO_TRIM },
  { name: 'claret', body: '#7A1426', trim: NO_TRIM },
  { name: 'navy', body: '#1F3E73', trim: NO_TRIM },
  { name: 'black-gold', body: '#0B0E0D', trim: '#CFAE62' },
  { name: 'orange', body: '#E35D18', trim: NO_TRIM },
  { name: 'sky', body: '#6CACE4', trim: NO_TRIM },
])
export const INK = '#0E1311'
export const CLUB_COLOUR_MS = 1200
export const CLUB_TRANSITION_MS = 200

export const CLEAT_MARK = `<span class="cleat-mark" aria-hidden="true" data-brand-logo="academy-watch-winged-boot"><span class="cleat-art" data-brand-part="art"></span><span class="cleat-boot" data-brand-part="boot"></span><span class="cleat-shade" data-brand-part="shade"></span><span class="cleat-light" data-brand-part="light"></span><span class="cleat-trim" data-brand-part="trim"></span></span>`

let probe
// Any CSS colour (rgb, oklch, color-mix, ...) -> [r, g, b, a] via a 1x1 canvas.
function toRgba(colour) {
  probe ||= document.createElement('canvas').getContext('2d', { willReadFrequently: true })
  probe.clearRect(0, 0, 1, 1)
  probe.fillStyle = '#000000'
  probe.fillStyle = colour
  probe.fillRect(0, 0, 1, 1)
  return probe.getImageData(0, 0, 1, 1).data
}

// Nearest painted ancestor decides whether the loader sits on a dark surface (night,
// dark theme, or a club console painted in the club's own colour). A background image
// (gradient, photo) cannot be judged from one colour: leave it to the CSS default.
export function detectSurface(element) {
  for (let node = element?.parentElement; node; node = node.parentElement) {
    const style = getComputedStyle(node)
    if (style.backgroundImage && style.backgroundImage !== 'none') return undefined
    const [r, g, b, a] = toRgba(style.backgroundColor)
    if (a < 128) continue
    const lum = [r, g, b].map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] < 0.18 ? 'night' : 'chalk'
  }
  return undefined
}
