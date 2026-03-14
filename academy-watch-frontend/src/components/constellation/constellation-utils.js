/**
 * Constellation visualization utilities
 * Data transforms, node sizing, and color helpers for the academy network graph.
 */

import { CONSTELLATION_STATUS_COLORS } from '../../lib/theme-constants'

// Re-export from theme-constants so existing consumers don't break
export const STATUS_COLORS = CONSTELLATION_STATUS_COLORS

export const STATUS_LABELS = {
    first_team: 'First Team',
    on_loan: 'On Loan',
    academy: 'Academy',
    released: 'Released',
    sold: 'Sold',
}

/**
 * Get the display label for a status, with optional team name for first_team.
 */
export function getStatusLabel(status, teamName) {
    if (status === 'first_team' && teamName) {
        return `${teamName} First Team`
    }
    return STATUS_LABELS[status] || status?.replace('_', ' ') || 'Unknown'
}

// Link type colors (semi-transparent for lattice feel)
export const LINK_COLORS = {
    loan: 'rgba(234,179,8,0.6)',
    permanent: 'rgba(148,163,184,0.5)',
    return: 'rgba(34,197,94,0.4)',
}

/**
 * Calculate node radius based on player count.
 * Parent node is always larger.
 */
export function nodeRadius(node) {
    if (node.is_parent) return 24
    return Math.max(8, Math.sqrt(node.player_count || 1) * 6)
}

/**
 * Get node color based on link types or parent status.
 */
export function nodeColor(node) {
    if (node.is_parent) return '#eab308' // gold for parent
    const types = node.link_types || []
    if (types.includes('loan') && types.includes('permanent')) return '#8b5cf6' // purple mix
    if (types.includes('permanent')) return '#f97316' // orange
    return '#d97706' // amber default (loan)
}

/**
 * Get link width based on player count (thinner for lattice feel).
 */
export function linkWidth(link) {
    return Math.max(0.5, (link.player_count || 1) * 0.8)
}

/**
 * Get link dash pattern — dashed for loans, solid for everything else.
 */
export function linkLineDash(link) {
    if (link.link_type === 'loan') return [4, 2]
    return null
}

/**
 * Get link color based on link type.
 */
export function linkColor(link) {
    return LINK_COLORS[link.link_type] || LINK_COLORS.loan
}

/**
 * Get initials from a club name (max 3 chars).
 */
export function clubInitials(name) {
    if (!name) return '?'
    const words = name.split(/\s+/)
    if (words.length === 1) return words[0].substring(0, 3).toUpperCase()
    return words.map(w => w[0]).join('').substring(0, 3).toUpperCase()
}
