  const loadMatches = useCallback(async () => {
    setMatchesLoading(true)
    setMatchesError(null)
    setMatchesLoadFailureCount(0)
    try {
      const response = await APIService.listClubMatches(programId)
      if (!mountedRef.current) return
      setMatches(Array.isArray(response?.matches) ? response.matches : [])
    } catch (error) {
      if (!mountedRef.current) return
      if (error?.status === 403) {
        onAccessDenied()
        return
      }
      setMatches([])
      setMatchesLoadFailureCount(1)
      setMatchesError(errorText(error, 'Matches could not be loaded. Try again.'))
    } finally {
      if (mountedRef.current) setMatchesLoading(false)
    }
  }, [onAccessDenied, programId])
