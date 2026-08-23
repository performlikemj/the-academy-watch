
  // List rows are summaries without `roster`. MatchDetail must never start from a missing roster — a save would
  // then wipe the saved entries — so the selected match is fetched in full once, and the editor renders only after.
  const selectedMatchId = selectedMatch?.id || null
  const hydrated = Array.isArray(selectedMatch?.roster)
  const [hydrateError, setHydrateError] = useState(null)
  const [hydrateAttempt, setHydrateAttempt] = useState(0)
  useEffect(() => {
    if (!selectedMatchId || hydrated) return undefined
    let cancelled = false
    setHydrateError(null)
    APIService.getClubMatch(programId, selectedMatchId)
      .then((full) => {
        if (cancelled) return
        upsertMatch({ ...full, roster: Array.isArray(full?.roster) ? full.roster : [] })
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError?.status === 403) {
          onAccessDenied()
          return
        }
        setHydrateError(errorText(requestError, 'Match details could not be loaded. Try again.'))
      })
    return () => { cancelled = true }
  }, [selectedMatchId, hydrated, hydrateAttempt, programId, upsertMatch, onAccessDenied])
