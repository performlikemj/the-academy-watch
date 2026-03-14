/**
 * Converts plain text content to formatted HTML.
 * Handles line breaks, bullet points, and basic text structure.
 */

// Common bullet point characters
const BULLET_CHARS = ['•', '·', '-', '*', '–', '—']

// Check if a line looks like a bullet point
function isBulletLine(line) {
  const trimmed = line.trim()
  if (!trimmed) return false
  
  // Check for bullet characters at start
  for (const char of BULLET_CHARS) {
    if (trimmed.startsWith(char + ' ') || trimmed.startsWith(char + '\t')) {
      return true
    }
  }
  
  // Check for numbered lists (1. 2. etc)
  if (/^\d+[\.\)]\s/.test(trimmed)) {
    return true
  }
  
  return false
}

// Extract bullet content without the bullet marker
function extractBulletContent(line) {
  const trimmed = line.trim()
  
  // Remove bullet character
  for (const char of BULLET_CHARS) {
    if (trimmed.startsWith(char + ' ') || trimmed.startsWith(char + '\t')) {
      return trimmed.slice(char.length).trim()
    }
  }
  
  // Handle numbered lists
  const numberedMatch = trimmed.match(/^\d+[\.\)]\s*(.*)/)
  if (numberedMatch) {
    return numberedMatch[1]
  }
  
  return trimmed
}

// Escape HTML characters to prevent XSS
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }
  return text.replace(/[&<>"']/g, char => map[char])
}

/**
 * Main formatting function - converts plain text to HTML
 * @param {string} text - Plain text input
 * @returns {string} - HTML formatted output
 */
export function formatTextToHtml(text) {
  if (!text || typeof text !== 'string') return ''
  
  // If the text already looks like HTML, return as-is
  if (text.includes('<p>') || text.includes('<br') || text.includes('<ul>') || text.includes('<div>')) {
    return text
  }
  
  // Normalize line endings
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  
  // Split by double newlines (paragraph breaks) or single newlines
  const lines = normalized.split('\n')
  
  const result = []
  let currentParagraph = []
  let inList = false
  let listItems = []
  
  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      const content = currentParagraph
        .map(line => escapeHtml(line))
        .join('<br />')
      if (content.trim()) {
        result.push(`<p>${content}</p>`)
      }
      currentParagraph = []
    }
  }
  
  const flushList = () => {
    if (listItems.length > 0) {
      const items = listItems
        .map(item => `<li>${escapeHtml(item)}</li>`)
        .join('')
      result.push(`<ul>${items}</ul>`)
      listItems = []
      inList = false
    }
  }
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmedLine = line.trim()
    
    // Empty line - flush current content
    if (!trimmedLine) {
      if (inList) {
        flushList()
      } else {
        flushParagraph()
      }
      continue
    }
    
    // Check if this is a bullet point
    if (isBulletLine(line)) {
      // Flush any pending paragraph
      if (!inList) {
        flushParagraph()
      }
      inList = true
      listItems.push(extractBulletContent(line))
    } else {
      // Not a bullet - flush any pending list
      if (inList) {
        flushList()
      }
      currentParagraph.push(trimmedLine)
    }
  }
  
  // Flush any remaining content
  if (inList) {
    flushList()
  }
  flushParagraph()
  
  return result.join('')
}

/**
 * Lightweight version that just handles line breaks
 * Use when you don't need full paragraph/list parsing
 */
export function simpleLineBreaks(text) {
  if (!text || typeof text !== 'string') return ''
  
  // If already has HTML, return as-is
  if (text.includes('<br') || text.includes('<p>')) {
    return text
  }
  
  return escapeHtml(text)
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br />')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
    .replace(/<p><\/p>/g, '')
}

export default formatTextToHtml

/**
 * Extract all text content from newsletter JSON structure
 * @param {object} content - Parsed newsletter content object
 * @returns {string} - All text content concatenated
 */
function extractTextFromNewsletterContent(content) {
  if (!content || typeof content !== 'object') return ''

  let text = ''

  // Extract title
  if (content.title) text += content.title + ' '

  // Extract summary
  if (content.summary) text += content.summary + ' '

  // Extract highlights
  if (Array.isArray(content.highlights)) {
    text += content.highlights.join(' ') + ' '
  }

  // Extract by_numbers section
  if (content.by_numbers) {
    if (Array.isArray(content.by_numbers.minutes_leaders)) {
      text += content.by_numbers.minutes_leaders.map(l => l.name || '').join(' ') + ' '
    }
    if (Array.isArray(content.by_numbers.ga_leaders)) {
      text += content.by_numbers.ga_leaders.map(l => l.name || '').join(' ') + ' '
    }
  }

  // Extract sections and items
  if (Array.isArray(content.sections)) {
    for (const section of content.sections) {
      if (section.title) text += section.title + ' '
      if (section.content) text += section.content + ' '

      if (Array.isArray(section.items)) {
        for (const item of section.items) {
          if (item.name) text += item.name + ' '
          if (item.week_summary) text += item.week_summary + ' '
          if (Array.isArray(item.match_notes)) {
            text += item.match_notes.join(' ') + ' '
          }
        }
      }
    }
  }

  return text
}

/**
 * Estimate reading time from newsletter content
 * @param {string|object} content - Newsletter content (JSON string or parsed object)
 * @returns {string} - Human-readable reading time (e.g., "3 min read")
 */
export function estimateReadingTime(content) {
  const WORDS_PER_MINUTE = 200

  if (!content) return ''

  let text = ''

  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      text = extractTextFromNewsletterContent(parsed)
    } catch {
      // If not JSON, treat as plain text
      text = content
    }
  } else if (typeof content === 'object') {
    text = extractTextFromNewsletterContent(content)
  }

  const wordCount = text.split(/\s+/).filter(Boolean).length
  const minutes = Math.ceil(wordCount / WORDS_PER_MINUTE)

  if (minutes < 1) return '< 1 min read'
  if (minutes === 1) return '1 min read'
  return `${minutes} min read`
}

/**
 * Truncate text at word boundary with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} - Truncated text
 */
function truncateAtWord(text, maxLength) {
  if (!text || text.length <= maxLength) return text || ''

  // Find the last space before maxLength
  const truncated = text.substring(0, maxLength)
  const lastSpace = truncated.lastIndexOf(' ')

  if (lastSpace > maxLength * 0.7) {
    return truncated.substring(0, lastSpace) + '...'
  }
  return truncated + '...'
}

/**
 * Extract a preview excerpt from newsletter content
 * @param {string|object} content - Newsletter content (JSON string or parsed object)
 * @param {number} maxLength - Maximum excerpt length (default 150)
 * @returns {string} - Content excerpt
 */
export function extractNewsletterExcerpt(content, maxLength = 150) {
  if (!content) return ''

  let parsed = content

  if (typeof content === 'string') {
    try {
      parsed = JSON.parse(content)
    } catch {
      // If not JSON, return truncated plain text
      return truncateAtWord(content, maxLength)
    }
  }

  if (!parsed || typeof parsed !== 'object') return ''

  // Priority 1: Summary
  if (parsed.summary && typeof parsed.summary === 'string') {
    return truncateAtWord(parsed.summary, maxLength)
  }

  // Priority 2: First highlight
  if (Array.isArray(parsed.highlights) && parsed.highlights[0]) {
    return truncateAtWord(parsed.highlights[0], maxLength)
  }

  // Priority 3: First section's first item week_summary
  if (Array.isArray(parsed.sections) && parsed.sections[0]) {
    const section = parsed.sections[0]
    if (section.content) {
      return truncateAtWord(section.content, maxLength)
    }
    if (Array.isArray(section.items) && section.items[0]?.week_summary) {
      return truncateAtWord(section.items[0].week_summary, maxLength)
    }
  }

  return ''
}













