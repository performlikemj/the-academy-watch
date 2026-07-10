import { getInitials } from '@/lib/name'
// Pure canvas-based branded stat card generator for player profile shares.
// No React — a plain function that draws a 1080x1350 (4:5) PNG and triggers
// a browser download. Never lets a CORS-tainted photo fail the download: it
// falls back to an initials disc, and wraps the canvas export itself in a
// second try so a tainted-canvas SecurityError still produces a card.

// Brand tokens hardcoded here on purpose — canvas can't read CSS custom
// properties. Keep in sync with src/App.css (--primary / --gold / --background).
const COLORS = {
    claret: '#7c2d36',
    claretDeep: '#4a1b20',
    gold: '#b8860b',
    bg: '#faf8f5',
    white: '#ffffff',
}

const CARD_WIDTH = 1080
const CARD_HEIGHT = 1350
const MARGIN = 88
const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

// --- geometry -----------------------------------------------------------

const PHOTO_RADIUS = 168
const PHOTO_CY = 148 + PHOTO_RADIUS
const NAME_Y = PHOTO_CY + PHOTO_RADIUS + 92
const META_Y = NAME_Y + 54
const DIVIDER_Y = META_Y + 66
const GRID_TOP = DIVIDER_Y + 46
const GRID_GAP = 26
const GRID_CELL_W = (CARD_WIDTH - MARGIN * 2 - GRID_GAP) / 2
const GRID_CELL_H = 172
const FOOTER_DIVIDER_Y = CARD_HEIGHT - 178
const FOOTER_WORDMARK_Y = CARD_HEIGHT - 128
const FOOTER_URL_Y = CARD_HEIGHT - 88

// --- small helpers --------------------------------------------------------

function loadImage(src) {
    return new Promise((resolve, reject) => {
        if (!src) {
            reject(new Error('no photo url'))
            return
        }
        const img = new Image()
        img.crossOrigin = 'anonymous'
        img.onload = () => resolve(img)
        img.onerror = () => reject(new Error('image failed to load'))
        img.src = src
    })
}

function roundedRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
}

/** Shrinks the font size until `text` fits `maxWidth`, down to `minSize`. */
function fitFontSize(ctx, text, { maxWidth, maxSize, minSize, weight = '800' }) {
    let size = maxSize
    while (size > minSize) {
        ctx.font = `${weight} ${size}px ${FONT_STACK}`
        if (ctx.measureText(text).width <= maxWidth) break
        size -= 4
    }
    return size
}

function formatNumber(value) {
    if (value === null || typeof value === 'undefined' || Number.isNaN(Number(value))) return '0'
    return String(Math.round(Number(value)))
}

function formatRating(value) {
    if (value === null || typeof value === 'undefined' || Number.isNaN(Number(value))) return '—'
    return Number(value).toFixed(1)
}

function slugify(value) {
    const ascii = (value || 'player')
        .toString()
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '') // strip combining diacritics after NFKD split
    const slug = ascii.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
    return slug || 'player'
}

// --- drawing --------------------------------------------------------------

function drawBackground(ctx) {
    const gradient = ctx.createLinearGradient(0, 0, 0, CARD_HEIGHT)
    gradient.addColorStop(0, COLORS.claret)
    gradient.addColorStop(1, COLORS.claretDeep)
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT)

    // Subtle diagonal accent, top-right corner only.
    ctx.save()
    ctx.globalAlpha = 0.07
    ctx.fillStyle = COLORS.white
    ctx.beginPath()
    ctx.moveTo(CARD_WIDTH * 0.58, 0)
    ctx.lineTo(CARD_WIDTH, 0)
    ctx.lineTo(CARD_WIDTH, CARD_HEIGHT * 0.4)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
}

function drawEyebrow(ctx) {
    ctx.save()
    ctx.fillStyle = COLORS.gold
    ctx.font = `700 26px ${FONT_STACK}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText('P L A Y E R   P R O F I L E', CARD_WIDTH / 2, 96)
    ctx.restore()
}

function drawInitialsDisc(ctx, name) {
    const cx = CARD_WIDTH / 2
    const cy = PHOTO_CY
    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, PHOTO_RADIUS, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,0.12)'
    ctx.fill()
    ctx.lineWidth = 6
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'
    ctx.stroke()
    ctx.restore()

    ctx.save()
    ctx.fillStyle = COLORS.white
    ctx.font = `700 ${Math.round(PHOTO_RADIUS * 0.7)}px ${FONT_STACK}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(getInitials(name), cx, cy + PHOTO_RADIUS * 0.06)
    ctx.restore()
}

function drawPhotoDisc(ctx, img) {
    const cx = CARD_WIDTH / 2
    const cy = PHOTO_CY
    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, PHOTO_RADIUS, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()

    const size = PHOTO_RADIUS * 2
    const imgRatio = img.width / img.height || 1
    const drawW = imgRatio > 1 ? size * imgRatio : size
    const drawH = imgRatio > 1 ? size : size / imgRatio
    ctx.drawImage(img, cx - drawW / 2, cy - drawH / 2, drawW, drawH)
    ctx.restore()

    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, PHOTO_RADIUS, 0, Math.PI * 2)
    ctx.lineWidth = 6
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'
    ctx.stroke()
    ctx.restore()
}

function drawName(ctx, name) {
    const maxWidth = CARD_WIDTH - MARGIN * 2
    const size = fitFontSize(ctx, name, { maxWidth, maxSize: 76, minSize: 40, weight: '800' })
    ctx.save()
    ctx.font = `800 ${size}px ${FONT_STACK}`
    ctx.fillStyle = COLORS.white
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(name, CARD_WIDTH / 2, NAME_Y, maxWidth)
    ctx.restore()
}

function drawMetaLine(ctx, parts) {
    const line = parts.filter(Boolean).join('   •   ')
    if (!line) return
    ctx.save()
    ctx.font = `600 32px ${FONT_STACK}`
    ctx.fillStyle = 'rgba(255,255,255,0.78)'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(line, CARD_WIDTH / 2, META_Y, CARD_WIDTH - MARGIN * 2)
    ctx.restore()
}

function drawDivider(ctx, y) {
    ctx.save()
    ctx.strokeStyle = 'rgba(255,255,255,0.18)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(MARGIN, y)
    ctx.lineTo(CARD_WIDTH - MARGIN, y)
    ctx.stroke()
    ctx.restore()
}

function drawStatCell(ctx, x, y, label, value) {
    roundedRectPath(ctx, x, y, GRID_CELL_W, GRID_CELL_H, 20)
    ctx.save()
    ctx.fillStyle = 'rgba(255,255,255,0.08)'
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.font = `800 72px ${FONT_STACK}`
    ctx.fillStyle = COLORS.white
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(value, x + GRID_CELL_W / 2, y + GRID_CELL_H * 0.58)
    ctx.restore()

    ctx.save()
    ctx.font = `700 24px ${FONT_STACK}`
    ctx.fillStyle = COLORS.gold
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(label.toUpperCase(), x + GRID_CELL_W / 2, y + GRID_CELL_H * 0.58 + 42)
    ctx.restore()
}

function drawStatGrid(ctx, stats) {
    stats.forEach((stat, index) => {
        const col = index % 2
        const row = Math.floor(index / 2)
        const x = MARGIN + col * (GRID_CELL_W + GRID_GAP)
        const y = GRID_TOP + row * (GRID_CELL_H + GRID_GAP)
        drawStatCell(ctx, x, y, stat.label, stat.value)
    })
}

function drawFollowCard(ctx) {
    const y = GRID_TOP
    const h = GRID_CELL_H * 2 + GRID_GAP
    roundedRectPath(ctx, MARGIN, y, CARD_WIDTH - MARGIN * 2, h, 24)
    ctx.save()
    ctx.fillStyle = 'rgba(255,255,255,0.08)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(255,255,255,0.2)'
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.restore()

    ctx.save()
    ctx.font = `800 46px ${FONT_STACK}`
    ctx.fillStyle = COLORS.white
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Follow the journey', CARD_WIDTH / 2, y + h / 2 - 24)
    ctx.restore()

    ctx.save()
    ctx.font = `500 28px ${FONT_STACK}`
    ctx.fillStyle = 'rgba(255,255,255,0.72)'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Track every step on The Academy Watch', CARD_WIDTH / 2, y + h / 2 + 30)
    ctx.restore()
}

function drawFooter(ctx, shareUrl) {
    drawDivider(ctx, FOOTER_DIVIDER_Y)

    ctx.save()
    ctx.font = `800 32px ${FONT_STACK}`
    try {
        ctx.letterSpacing = '4px'
    } catch {
        // letterSpacing isn't supported everywhere — the fallback still reads fine.
    }
    ctx.fillStyle = COLORS.gold
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText('THE ACADEMY WATCH', CARD_WIDTH / 2, FOOTER_WORDMARK_Y)
    ctx.restore()

    if (shareUrl) {
        ctx.save()
        ctx.font = `500 26px ${FONT_STACK}`
        ctx.fillStyle = 'rgba(255,255,255,0.68)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'alphabetic'
        const displayUrl = shareUrl.replace(/^https?:\/\//i, '')
        ctx.fillText(displayUrl, CARD_WIDTH / 2, FOOTER_URL_Y, CARD_WIDTH - MARGIN * 2)
        ctx.restore()
    }
}

function isGoalkeeper(position) {
    return String(position || '').toLowerCase().includes('keeper')
}

function buildStats({ seasonTotals, position }) {
    const apps = { label: 'Apps', value: formatNumber(seasonTotals?.appearances) }
    const rating = { label: 'Rating', value: formatRating(seasonTotals?.avgRating) }
    if (isGoalkeeper(position)) {
        return [
            apps,
            { label: 'Saves', value: formatNumber(seasonTotals?.saves) },
            { label: 'Conceded', value: formatNumber(seasonTotals?.goalsConceded) },
            rating,
        ]
    }
    return [
        apps,
        { label: 'Goals', value: formatNumber(seasonTotals?.goals) },
        { label: 'Assists', value: formatNumber(seasonTotals?.assists) },
        rating,
    ]
}

function hasStats(seasonTotals) {
    return !!seasonTotals && Number(seasonTotals.appearances) > 0
}

function drawCard(ctx, { playerName, profile, seasonTotals, position, photoImg, shareUrl }) {
    ctx.clearRect(0, 0, CARD_WIDTH, CARD_HEIGHT)
    drawBackground(ctx)
    drawEyebrow(ctx)

    const name = playerName || profile?.name || 'Academy Player'
    if (photoImg) {
        drawPhotoDisc(ctx, photoImg)
    } else {
        drawInitialsDisc(ctx, name)
    }

    drawName(ctx, name)
    drawMetaLine(ctx, [position || profile?.position, profile?.age ? `${profile.age}yo` : null, profile?.nationality])
    drawDivider(ctx, DIVIDER_Y)

    if (hasStats(seasonTotals)) {
        drawStatGrid(ctx, buildStats({ seasonTotals, position: position || profile?.position }))
    } else {
        drawFollowCard(ctx)
    }

    drawFooter(ctx, shareUrl)
}

function canvasToDataUrl(canvas) {
    // toDataURL throws a SecurityError synchronously if the canvas was
    // tainted by a cross-origin photo the server didn't send CORS headers for.
    return canvas.toDataURL('image/png')
}

function downloadDataUrl(dataUrl, filename) {
    if (typeof document === 'undefined') return
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
}

/**
 * Draws and downloads a branded 1080x1350 player stat card PNG.
 * Never throws for CORS reasons — falls back to a photo-less card.
 */
export async function generateStatCard({ playerName, profile, seasonTotals, position, shareUrl } = {}) {
    const canvas = document.createElement('canvas')
    canvas.width = CARD_WIDTH
    canvas.height = CARD_HEIGHT
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas 2D context unavailable')

    const photoUrl = profile?.photo || profile?.photo_url || null
    let photoImg = null
    if (photoUrl) {
        try {
            photoImg = await loadImage(photoUrl)
        } catch (err) {
            console.warn('Stat card: player photo failed to load, using initials fallback', err)
            photoImg = null
        }
    }

    const drawArgs = { playerName, profile, seasonTotals, position, photoImg, shareUrl }
    drawCard(ctx, drawArgs)

    let dataUrl
    try {
        dataUrl = canvasToDataUrl(canvas)
    } catch (err) {
        console.warn('Stat card export failed (likely a tainted canvas); retrying without the photo', err)
        drawCard(ctx, { ...drawArgs, photoImg: null })
        dataUrl = canvasToDataUrl(canvas)
    }

    const filename = `${slugify(playerName || profile?.name)}-academy-watch.png`
    downloadDataUrl(dataUrl, filename)
    return true
}

export const STAT_CARD_DIMENSIONS = { width: CARD_WIDTH, height: CARD_HEIGHT }
