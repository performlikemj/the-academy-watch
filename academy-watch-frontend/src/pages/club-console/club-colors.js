const CHALK = '#F3F0E8'
const WHITE = '#FFFFFF'
const INK = '#0E1311'
const GOLD = '#CFAE62'

function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map(channel => parseInt(channel, 16) / 255)
  const linear = rgb.map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
}

export function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

// Saved primaries meet AA against white, not necessarily chalk. The ink
// fallback also keeps an unsaved light colour readable in the live preview.
export function clubSurfaceColors(primary, accent) {
  const background = /^#[0-9a-f]{6}$/i.test(primary) ? primary : '#0F3D2E'
  const foreground = contrast(CHALK, background) >= 4.5 ? CHALK : contrast(WHITE, background) >= 4.5 ? WHITE : INK
  const emphasis = /^#[0-9a-f]{6}$/i.test(accent) && contrast(accent, background) >= 4.5 ? accent : foreground
  const active = '#' + background.slice(1).match(/../g).map(channel => Math.floor(parseInt(channel, 16) * 0.88).toString(16).padStart(2, '0')).join('')
  return {
    '--club-foreground': foreground,
    '--club-emphasis': emphasis,
    '--club-focus': contrast(GOLD, background) >= 3 ? GOLD : foreground,
    '--club-active': active,
  }
}
