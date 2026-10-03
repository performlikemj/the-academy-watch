// Match the server's match_date DESC NULLS LAST, id DESC ordering after writes.
export function sortClubMatches(matches) {
  return [...matches].sort((a, b) => {
    if ((a.match_date || null) !== (b.match_date || null)) {
      if (!a.match_date) return 1
      if (!b.match_date) return -1
      return a.match_date > b.match_date ? -1 : 1
    }
    return b.id - a.id
  })
}
