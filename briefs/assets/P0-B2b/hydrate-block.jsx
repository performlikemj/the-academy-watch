
  // List rows are summaries without `roster`. MatchDetail must never start from a missing roster — a save would
  // then wipe the saved entries — so the selected match is fetched in full once, and the editor renders only after.
  const selectedMatchId = selectedMatch?.id || null
  const hydrated = Array.isArray(selectedMatch?.roster)
  const [hydrateError, setHydrateError] = useState(null) // { id, message } for the match whose fetch failed
  const [hydrateAttempt, setHydrateAttempt] = useState(0)
  useEffect(() => {
    if (!selectedMatchId || hydrated) return undefined
    let cancelled = false
    APIService.getClubMatch(programId, selectedMatchId)
      .then((full) => {
        if (cancelled) return
        setHydrateError(null)
        upsertMatch({ ...full, roster: Array.isArray(full?.roster) ? full.roster : [] })
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError?.status === 403) {
          onAccessDenied()
          return
        }
        setHydrateError({ id: selectedMatchId, message: errorText(requestError, 'Match details could not be loaded. Try again.') })
      })
    return () => { cancelled = true }
  }, [selectedMatchId, hydrated, hydrateAttempt, programId, upsertMatch, onAccessDenied])
  const hydrateMessage = hydrateError?.id === selectedMatchId ? hydrateError.message : null
