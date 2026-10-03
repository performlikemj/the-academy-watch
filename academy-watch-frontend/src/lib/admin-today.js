// Admin Today: turn queue counts into the rows an admin acts on. Queues with
// nothing waiting are counted, never listed.
import { clubCheckLine, clubCheckSummary } from './club-checks.js'

const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`

// key -> [area, singular, plural, summary line]
const QUEUE_WORDS = {
    manual: ['Review', 'manually added player to check', 'manually added players to check', 'Players submitted by hand'],
    takes: ['Review', 'community take to review', 'community takes to review', 'Written by fans'],
    submissions: ['Review', 'quick take to review', 'quick takes to review', 'Sent in by readers'],
    flags: ['Review', 'player flag to look at', 'player flags to look at', 'Someone says a player record is wrong'],
    tracking: ['Review', 'tracking request', 'tracking requests', 'A club someone wants followed'],
    links: ['Review', 'player link to check', 'player links to check', 'Suggested links for a player page'],
    club_claims: ['Club', 'club wants to be verified', 'clubs want to be verified', 'Check the evidence, then approve or reject'],
    club_profiles: ['Content', 'club page edit to approve', 'club page edits to approve', 'Profile changes sent by a club'],
    club_updates: ['Content', 'club update to approve', 'club updates to approve', 'News posts sent by a club'],
    scout_verifications: ['Scout', 'person asks to be a verified scout', 'people ask to be verified scouts', 'Check who they are and who they scout for'],
    profile_claims: ['People', 'player page claim to review', 'player page claims to review', 'A player or guardian asking for their page'],
    showcase_profiles: ['People', 'player page edit to approve', 'player page edits to approve', 'Changes a player made to their page'],
    local_players: ['People', 'community player to review', 'community players to review', 'Players added by the community'],
    local_clubs: ['Club', 'community club to review', 'community clubs to review', 'Clubs added by the community'],
    affiliations: ['Club', 'club affiliation to confirm', 'club affiliations to confirm', 'A player says they play for a club'],
    official_claims: ['Club', 'club official claim to review', 'club official claims to review', 'Someone says they run a club'],
    showcase_media: ['People', 'showcase photo to approve', 'showcase photos to approve', 'Photos players uploaded'],
    reports: ['Safety', 'safety report waiting', 'safety reports waiting', 'Reported by a user'],
    safeguarding: ['Safety', 'safeguarding case open', 'safeguarding cases open', 'First action is due within 24 hours'],
}
const WARN = new Set(['reports', 'safeguarding'])

function queueRow(queue) {
    const [area, one, many, summary] = QUEUE_WORDS[queue.key] || ['Review', `${String(queue.label || queue.key).toLowerCase()} waiting`, `${String(queue.label || queue.key).toLowerCase()} waiting`, 'Waiting for a decision']
    return { key: queue.key, tone: WARN.has(queue.key) ? 'warn' : 'gold', title: plural(queue.count, one, many), summary, area, href: queue.href || null }
}

function listNames(names) {
    const shown = names.filter(Boolean).slice(0, 3)
    return shown.length ? `${shown.join(' · ')}${names.length > shown.length ? ` and ${names.length - shown.length} more` : ''}` : null
}

/**
 * queues: [{ key, label, href, count }] — the server's counts (or the legacy inbox counts).
 * claims / scouts: the pending lists when they could be read, else null. They only name a
 * row the counts already report, or add that row when the counts do not cover it.
 * Returns { rows, clear } — clear = how many counted queues have nothing waiting.
 */
export function todayRows({ queues = [], claims = null, scouts = null, overdue = 0, revenue = null, ops = null, businessHref = null } = {}) {
    const counted = queues.map(queue => ({ ...queue, count: Number(queue.count) || 0 }))
    const has = key => counted.some(queue => queue.key === key)
    if (claims && !has('club_claims')) counted.push({ key: 'club_claims', href: '/admin/funding?tab=claims', count: claims.length })
    if (scouts && !has('scout_verifications')) counted.push({ key: 'scout_verifications', href: '/admin/trust?tab=verifications', count: Number(scouts.total) || 0 })
    const rows = counted.filter(queue => queue.count > 0).map(queue => {
        const row = queueRow(queue)
        if (queue.key === 'club_claims' && claims?.length) {
            if (claims.length === 1) {
                const [claim] = claims
                return { ...row, title: `${claim.program?.name || 'A club'} wants to be a verified club`, summary: clubCheckLine(clubCheckSummary(claim.evidence)), href: `/admin/funding?tab=claims&claim=${claim.id}` }
            }
            return { ...row, summary: listNames(claims.map(claim => claim.program?.name)) || row.summary }
        }
        if (queue.key === 'scout_verifications' && scouts?.rows?.length) {
            if (queue.count === 1) {
                const [scout] = scouts.rows
                return { ...row, title: `${scout.full_name} asks to be a verified scout`, summary: [scout.role_title, scout.organization].filter(Boolean).join(' · ') || row.summary }
            }
            return { ...row, summary: listNames(scouts.rows.map(scout => scout.full_name)) || row.summary }
        }
        if (queue.key === 'safeguarding' && overdue > 0) return { ...row, summary: `${overdue} past the 24-hour first action` }
        return row
    })
    // Safety first, then everything else in the order the server lists it.
    rows.sort((left, right) => Number(right.tone === 'warn') - Number(left.tone === 'warn'))
    if (revenue?.past_due > 0) rows.push({ key: 'past_due', tone: 'warn', title: plural(revenue.past_due, 'subscription is past due', 'subscriptions are past due'), summary: 'A payment failed and has not been recovered', area: 'Money', href: businessHref })
    if (revenue?.webhook_failed_last_24h > 0) rows.push({ key: 'webhooks', tone: 'warn', title: plural(revenue.webhook_failed_last_24h, 'payment notice failed in the last 24 hours', 'payment notices failed in the last 24 hours'), summary: 'Stripe could not deliver them', area: 'Money', href: businessHref })
    if (ops?.tracked?.placeholder_names > 0) rows.push({ key: 'placeholders', tone: 'gold', title: plural(ops.tracked.placeholder_names, 'player has a placeholder name', 'players have placeholder names'), summary: 'Repair them in Operations', area: 'Data', href: '/admin/operations' })
    if (ops?.tracked?.owning_club_active > 0) rows.push({ key: 'owning_club', tone: 'gold', title: plural(ops.tracked.owning_club_active, 'player is tracked at their own club', 'players are tracked at their own club'), summary: 'Repair them in Operations', area: 'Data', href: '/admin/operations' })
    return { rows, clear: counted.filter(queue => queue.count === 0).length, counted: counted.length }
}

/** The line under the list. Speaks only for the queues that were counted. */
export function clearLine({ rows, clear }) {
    if (!rows.length) return clear > 0 ? `Nothing is waiting. All ${clear} queues are clear.` : 'Nothing is waiting.'
    if (clear === 0) return null
    return `Everything else is clear. ${clear} other ${clear === 1 ? 'queue has' : 'queues have'} nothing waiting.`
}
