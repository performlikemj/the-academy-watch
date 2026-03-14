/**
 * Newsletter to Reddit Markdown Converter
 * 
 * Converts newsletter JSON to Reddit-compatible markdown format
 * with proper formatting for sharing on Reddit.
 */

/**
 * Format a date string for display
 */
function formatDate(dateStr) {
    if (!dateStr) return ''
    try {
        const date = new Date(dateStr)
        return date.toLocaleDateString('en-GB', { 
            day: 'numeric', 
            month: 'short', 
            year: 'numeric' 
        })
    } catch {
        return dateStr
    }
}

/**
 * Get result emoji based on match result
 */
function getResultEmoji(result) {
    switch (result?.toUpperCase()) {
        case 'W': return '🟢'
        case 'D': return '🟡'
        case 'L': return '🔴'
        default: return '⚪'
    }
}

/**
 * Format stats line based on player position
 */
function formatStatsLine(stats) {
    if (!stats) return ''
    
    const parts = []
    const minutes = stats.minutes || 0
    parts.push(`${minutes}'`)
    
    const position = stats.position || ''
    
    if (position === 'Goalkeeper' || position === 'G') {
        // Goalkeeper stats
        const saves = stats.saves || 0
        const conceded = stats.goals_conceded || 0
        parts.push(`${saves} saves`)
        parts.push(`${conceded} conceded`)
    } else if (position === 'Defender' || position === 'D') {
        // Defender stats
        if (stats.tackles_total || stats.tackles_interceptions) {
            parts.push(`${stats.tackles_total || 0}T ${stats.tackles_interceptions || 0}I`)
        }
        if (stats.goals > 0 || stats.assists > 0) {
            parts.push(`${stats.goals || 0}G ${stats.assists || 0}A`)
        }
    } else {
        // Midfielder/Forward stats
        parts.push(`${stats.goals || 0}G ${stats.assists || 0}A`)
        if (stats.passes_key) {
            parts.push(`${stats.passes_key} key passes`)
        }
        if (stats.shots_total) {
            parts.push(`${stats.shots_total} shots`)
        }
    }
    
    if (stats.rating) {
        parts.push(`⭐ ${Number(stats.rating).toFixed(1)}`)
    }
    
    return parts.join(' | ')
}

/**
 * Format expanded stats table for a player
 */
function formatExpandedStats(stats) {
    if (!stats) return ''
    
    const lines = []
    
    // Check if we have expanded stats worth showing
    const hasAttacking = stats.shots_total || stats.dribbles_attempts
    const hasPassing = stats.passes_total || stats.passes_key
    const hasDefending = stats.tackles_total || stats.tackles_interceptions
    const hasDuels = stats.duels_total
    const hasGK = (stats.position === 'Goalkeeper' || stats.position === 'G') && (stats.saves || stats.goals_conceded)
    
    if (!hasAttacking && !hasPassing && !hasDefending && !hasDuels && !hasGK) {
        return ''
    }
    
    lines.push('')
    lines.push('| Category | Stat | Value |')
    lines.push('|:---------|:-----|------:|')
    
    // Attacking
    if (hasAttacking) {
        if (stats.shots_total) {
            lines.push(`| ⚽ Attacking | Shots | ${stats.shots_total} (${stats.shots_on || 0} on target) |`)
        }
        if (stats.dribbles_attempts) {
            lines.push(`| ⚽ Attacking | Dribbles | ${stats.dribbles_success || 0}/${stats.dribbles_attempts} |`)
        }
    }
    
    // Passing
    if (hasPassing) {
        if (stats.passes_total) {
            lines.push(`| 🎯 Passing | Passes | ${stats.passes_total} |`)
        }
        if (stats.passes_key) {
            lines.push(`| 🎯 Passing | Key Passes | ${stats.passes_key} |`)
        }
        if (stats.passes_accuracy) {
            lines.push(`| 🎯 Passing | Accuracy | ${stats.passes_accuracy}% |`)
        }
    }
    
    // Defending
    if (hasDefending) {
        if (stats.tackles_total) {
            lines.push(`| 🛡️ Defending | Tackles | ${stats.tackles_total} |`)
        }
        if (stats.tackles_interceptions) {
            lines.push(`| 🛡️ Defending | Interceptions | ${stats.tackles_interceptions} |`)
        }
        if (stats.tackles_blocks) {
            lines.push(`| 🛡️ Defending | Blocks | ${stats.tackles_blocks} |`)
        }
    }
    
    // Duels
    if (hasDuels) {
        lines.push(`| ⚔️ Duels | Won | ${stats.duels_won || 0}/${stats.duels_total} |`)
    }
    
    // Goalkeeper
    if (hasGK) {
        if (stats.saves !== undefined) {
            lines.push(`| 🧤 Goalkeeper | Saves | ${stats.saves} |`)
        }
        if (stats.goals_conceded !== undefined) {
            lines.push(`| 🧤 Goalkeeper | Conceded | ${stats.goals_conceded} |`)
        }
    }
    
    // Discipline
    if (stats.yellows > 0 || stats.reds > 0) {
        lines.push(`| ⚠️ Discipline | Cards | ${stats.yellows || 0}🟨 ${stats.reds || 0}🟥 |`)
    }
    
    return lines.join('\n')
}

/**
 * Format matches/fixtures for a player
 */
function formatMatches(matches, upcomingFixtures) {
    if ((!matches || matches.length === 0) && (!upcomingFixtures || upcomingFixtures.length === 0)) {
        return ''
    }
    
    const lines = []
    
    // Completed matches
    if (matches && matches.length > 0) {
        lines.push('')
        lines.push('**This Week\'s Matches:**')
        for (const match of matches) {
            const emoji = getResultEmoji(match.result)
            const homeAway = match.home ? '(H)' : '(A)'
            const score = match.score ? `${match.score.home}-${match.score.away}` : ''
            lines.push(`- ${emoji} vs ${match.opponent} ${homeAway} ${score} — *${match.competition || ''}*`)
        }
    }
    
    // Fixtures from upcoming_fixtures that are completed
    if (upcomingFixtures && upcomingFixtures.length > 0) {
        const completedFixtures = upcomingFixtures.filter(f => f.status === 'completed' && f.result)
        const pending = upcomingFixtures.filter(f => f.status !== 'completed' || !f.result)
        
        if (completedFixtures.length > 0 && (!matches || matches.length === 0)) {
            lines.push('')
            lines.push('**Results:**')
            for (const fixture of completedFixtures) {
                const emoji = getResultEmoji(fixture.result)
                const prefix = fixture.is_home ? 'vs' : '@'
                const score = `${fixture.team_score}-${fixture.opponent_score}`
                lines.push(`- ${emoji} ${prefix} ${fixture.opponent} ${score} — *${fixture.competition || ''}*`)
            }
        }
        
        if (pending.length > 0) {
            lines.push('')
            lines.push('**Upcoming:**')
            for (const fixture of pending) {
                const prefix = fixture.is_home ? 'vs' : '@'
                const dateStr = fixture.date ? formatDate(fixture.date.substring(0, 10)) : ''
                lines.push(`- ${prefix} ${fixture.opponent} — *${fixture.competition || ''}* (${dateStr})`)
            }
        }
    }
    
    return lines.join('\n')
}

/**
 * Format links for a player item
 */
function formatLinks(links) {
    if (!links || links.length === 0) return ''
    
    const lines = ['', '**Links:**']
    for (const link of links) {
        const url = typeof link === 'string' ? link : link.url
        const title = (typeof link === 'object' && link.title) ? link.title : 'Link'
        if (url) {
            const isYoutube = url.includes('youtube.com') || url.includes('youtu.be')
            const icon = isYoutube ? '🎬' : '🔗'
            lines.push(`- ${icon} [${title}](${url})`)
        }
    }
    return lines.join('\n')
}

/**
 * Convert newsletter JSON to Reddit-formatted markdown
 * 
 * @param {Object} newsletter - The newsletter JSON object
 * @param {Object} options - Conversion options
 * @param {boolean} options.includeExpandedStats - Include detailed stats tables (default: true)
 * @param {boolean} options.includeLinks - Include links section (default: true)
 * @param {string} options.webUrl - URL to the full newsletter (optional)
 * @returns {string} Reddit-compatible markdown
 */
export function convertNewsletterToMarkdown(newsletter, options = {}) {
    const {
        includeExpandedStats = true,
        includeLinks = true,
        webUrl = null
    } = options
    
    if (!newsletter) return ''
    
    // Parse structured content if it's a string
    let content = newsletter
    if (typeof newsletter.structured_content === 'string') {
        try {
            content = JSON.parse(newsletter.structured_content)
        } catch {
            content = newsletter
        }
    } else if (newsletter.enriched_content) {
        content = newsletter.enriched_content
    }
    
    const lines = []
    
    // Header
    const title = content.title || newsletter.title || 'Academy Watch'
    lines.push(`# ${title}`)
    lines.push('')

    // Meta info
    const range = content.range
    if (range && range.length === 2) {
        lines.push(`📅 **Week:** ${formatDate(range[0])} — ${formatDate(range[1])}`)
    }
    if (content.season) {
        lines.push(`🏆 **Season:** ${content.season}`)
    }
    lines.push('')
    lines.push('---')
    lines.push('')
    
    // Summary
    if (content.summary) {
        lines.push(`> ${content.summary}`)
        lines.push('')
    }
    
    // Highlights
    if (content.highlights && content.highlights.length > 0) {
        lines.push('## ⭐ Highlights')
        lines.push('')
        for (const highlight of content.highlights) {
            lines.push(`- ${highlight}`)
        }
        lines.push('')
    }
    
    // By The Numbers
    if (content.by_numbers) {
        const bn = content.by_numbers
        lines.push('## 📊 By The Numbers')
        lines.push('')
        
        if (bn.minutes_leaders && bn.minutes_leaders.length > 0) {
            const leaders = bn.minutes_leaders.map(r => `${r.player} (${r.minutes}')`).join(', ')
            lines.push(`**Minutes Leaders:** ${leaders}`)
            lines.push('')
        }
        
        if (bn.ga_leaders && bn.ga_leaders.length > 0) {
            const leaders = bn.ga_leaders.map(r => `${r.player} (${r.g}G ${r.a}A)`).join(', ')
            lines.push(`**G+A Leaders:** ${leaders}`)
            lines.push('')
        }
    }
    
    // Sections (Player Reports)
    const sections = content.sections || []
    for (const section of sections) {
        if (!section || typeof section !== 'object') continue

        const sectionTitle = section.title || 'Players'
        lines.push(`## 📋 ${sectionTitle}`)
        lines.push('')

        // Collect items: either flat or from subsections
        const itemGroups = []
        if (section.subsections && section.subsections.length > 0) {
            for (const sub of section.subsections) {
                if (!sub || typeof sub !== 'object') continue
                itemGroups.push({ label: sub.label, items: sub.items || [] })
            }
        } else {
            itemGroups.push({ label: null, items: section.items || [] })
        }

        for (const group of itemGroups) {
            if (group.label) {
                lines.push(`### ${group.label}`)
                lines.push('')
            }
            for (const item of group.items) {
                if (!item || typeof item !== 'object') continue

                const playerName = item.player_name || 'Unknown Player'
                const loanTeam = item.loan_team || item.loan_team_name || ''

                // Player header
                lines.push(`### ${playerName}`)
                if (loanTeam) {
                    lines.push(`*Currently at ${loanTeam}*`)
                }
                lines.push('')

                // Stats line
                const canTrack = item.can_fetch_stats !== false
                if (canTrack && item.stats) {
                    const statsLine = formatStatsLine(item.stats)
                    if (statsLine) {
                        lines.push(`**Stats:** ${statsLine}`)
                        lines.push('')
                    }

                    // Expanded stats table
                    if (includeExpandedStats) {
                        const expandedStats = formatExpandedStats(item.stats)
                        if (expandedStats) {
                            lines.push(expandedStats)
                            lines.push('')
                        }
                    }
                } else if (!canTrack) {
                    lines.push('*Stats not available for this player*')
                    lines.push('')
                }

                // Week summary
                if (item.week_summary) {
                    lines.push(item.week_summary)
                    lines.push('')
                }

                // Matches
                const matchesSection = formatMatches(item.matches, item.upcoming_fixtures)
                if (matchesSection) {
                    lines.push(matchesSection)
                    lines.push('')
                }

                // Links
                if (includeLinks && item.links && item.links.length > 0) {
                    lines.push(formatLinks(item.links))
                    lines.push('')
                }

                lines.push('---')
                lines.push('')
            }
        }
    }
    
    // Footer
    lines.push('')
    lines.push('---')
    lines.push('')
    lines.push('*Generated by [The Academy Watch](https://theacademywatch.com) — Weekly academy watch newsletters for football fans*')
    
    if (webUrl) {
        lines.push('')
        lines.push(`📰 [View full newsletter with interactive stats](${webUrl})`)
    }
    
    return lines.join('\n')
}

/**
 * Convert newsletter to a more compact Reddit format
 * Good for shorter posts or comments
 * 
 * @param {Object} newsletter - The newsletter JSON object
 * @returns {string} Compact Reddit markdown
 */
export function convertNewsletterToCompactMarkdown(newsletter) {
    if (!newsletter) return ''
    
    // Parse structured content if it's a string
    let content = newsletter
    if (typeof newsletter.structured_content === 'string') {
        try {
            content = JSON.parse(newsletter.structured_content)
        } catch {
            content = newsletter
        }
    } else if (newsletter.enriched_content) {
        content = newsletter.enriched_content
    }
    
    const lines = []
    
    // Header
    const title = content.title || newsletter.title || 'Academy Watch'
    lines.push(`# ${title}`)
    lines.push('')

    // Date range
    const range = content.range
    if (range && range.length === 2) {
        lines.push(`📅 ${formatDate(range[0])} — ${formatDate(range[1])}`)
        lines.push('')
    }
    
    // Quick summary
    if (content.summary) {
        lines.push(`> ${content.summary}`)
        lines.push('')
    }
    
    // Player table
    const sections = content.sections || []
    for (const section of sections) {
        if (!section || typeof section !== 'object') continue

        // Collect all items (flat or from subsections)
        const allItems = []
        if (section.subsections && section.subsections.length > 0) {
            for (const sub of section.subsections) {
                if (sub && sub.items) allItems.push(...sub.items)
            }
        } else {
            allItems.push(...(section.items || []))
        }
        if (allItems.length === 0) continue

        lines.push(`**${section.title || 'Players'}**`)
        lines.push('')
        lines.push('| Player | Team | Stats |')
        lines.push('|:-------|:-----|:------|')

        for (const item of allItems) {
            if (!item || typeof item !== 'object') continue

            const playerName = item.player_name || 'Unknown'
            const loanTeam = item.loan_team || item.loan_team_name || '-'

            let statsStr = '-'
            if (item.stats) {
                const s = item.stats
                const mins = s.minutes || 0
                const goals = s.goals || 0
                const assists = s.assists || 0
                const rating = s.rating ? `⭐${Number(s.rating).toFixed(1)}` : ''
                statsStr = `${mins}' ${goals}G ${assists}A ${rating}`.trim()
            }

            lines.push(`| ${playerName} | ${loanTeam} | ${statsStr} |`)
        }

        lines.push('')
    }
    
    lines.push('---')
    lines.push('*via [The Academy Watch](https://theacademywatch.com)*')
    
    return lines.join('\n')
}

export default {
    convertNewsletterToMarkdown,
    convertNewsletterToCompactMarkdown
}

