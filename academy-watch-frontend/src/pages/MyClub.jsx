import { CleatLoader } from '@/components/CleatLoader'
import '@/styles/floodlight-player.css'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  Building2,
  Check,
  CheckCircle2,
  Loader2,
  LogIn,
  Plus,
  Search,
  ShieldCheck,
  UserCheck,
  X,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { watchEntryRead } from '@/pages/club-console/entry-read'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { VerificationCode, VerificationInstructions } from '@/components/showcase/VerificationCode'
import { MyClubConsole } from '@/pages/MyClubConsole'
import { useClubEntryFeatures } from '@/pages/club-console/useClubEntryFeatures'

const EMPTY_CLUB_RESULTS = { api_teams: [], local_clubs: [] }

const CLAIM_STATUS = {
  pending: { label: 'Pending', className: 'bg-warn/5 text-gold-text border-warn/30' },
  approved: { label: 'Approved', className: 'bg-good/5 text-good border-good/30' },
  rejected: { label: 'Rejected', className: 'bg-danger/5 text-danger border-danger/30' },
  revoked: { label: 'Revoked', className: 'bg-chalk-2 text-muted-foreground border-hairline' },
}

const VERIFICATION_STATUS = {
  unverified: { label: 'Unverified', className: 'bg-warn/5 text-gold-text border-warn/30' },
  code_found: { label: 'Code detected', className: 'bg-good/5 text-good border-good/30' },
  code_not_found: { label: 'Code not found', className: 'bg-danger/5 text-danger border-danger/30' },
}

const AFFILIATION_STATUS = {
  pending: { label: 'Pending review', className: 'bg-warn/5 text-gold-text border-warn/30' },
  self_reported: { label: 'Self-reported', className: 'bg-chalk-2 text-muted-foreground border-hairline' },
}

const RELATIONSHIP_LABELS = {
  player: 'Player',
  agent: 'Agent',
  guardian: 'Parent / Guardian',
  club_official: 'Club official',
}

function formatDate(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function StatusBadge({ status, styles }) {
  const badge = styles[status] || { label: status || 'Unknown', className: 'bg-chalk-2 text-muted-foreground border-hairline' }
  return <Badge className={badge.className}>{badge.label}</Badge>
}

function VerificationBadge({ status }) {
  return <StatusBadge status={status || 'unverified'} styles={VERIFICATION_STATUS} />
}

function SignedOutState({ onSignIn }) {
  return (
    <div className="fl-club-entry min-h-screen bg-chalk">
      <div className="mx-auto flex max-w-7xl items-center justify-center px-4 py-24 sm:px-6 lg:px-8">
        <Card className="w-full max-w-md overflow-hidden border-border/80">
          <CardContent className="flex flex-col items-center gap-4 px-8 py-12 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Building2 className="h-6 w-6 text-primary" />
            </span>
            <h1 className="text-xl font-bold tracking-tight text-foreground">Sign in to manage your club</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Claim the club you represent, review player affiliations and vouch for people you know.
            </p>
            <Button onClick={onSignIn}>
              <LogIn className="mr-1.5 h-4 w-4" />
              Sign in
            </Button>
            <Link to="/local-players/new" className="text-sm font-medium text-primary hover:underline">
              Create a player profile
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function ClubModerationWorkspace({
  clubs,
  actingAffiliationId,
  affiliationNotes,
  onAffiliationNoteChange,
  onReviewAffiliation,
  onVouch,
}) {
  return clubs.map((clubEntry) => {
    const pendingAffiliations = Array.isArray(clubEntry.pending_affiliations) ? clubEntry.pending_affiliations : []
    const vouchableClaims = Array.isArray(clubEntry.vouchable_player_claims) ? clubEntry.vouchable_player_claims : []
    return (
      <section key={clubEntry.claim?.id || clubEntry.club_name} className="space-y-4" aria-labelledby={`club-${clubEntry.claim?.id}-heading`}>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/15 bg-primary/5 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Approved club</p>
            <h2 id={`club-${clubEntry.claim?.id}-heading`} className="mt-1 text-2xl font-bold tracking-tight text-foreground">
              {clubEntry.club_name || clubEntry.claim?.club_name || 'Your club'}
            </h2>
            {clubEntry.claim?.role_title ? (
              <p className="mt-1 text-sm text-muted-foreground">Your role: {clubEntry.claim.role_title}</p>
            ) : null}
          </div>
          <Badge className="border-good/30 bg-good/5 text-good">
            <ShieldCheck className="mr-1 h-3.5 w-3.5" />
            Verified official
          </Badge>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Player affiliations</CardTitle>
              <CardDescription>Confirm or reject players who name this club on their showcase.</CardDescription>
            </CardHeader>
            <CardContent>
              {pendingAffiliations.length === 0 ? (
                <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                  No affiliations need your review.
                </p>
              ) : (
                <div className="space-y-3">
                  {pendingAffiliations.map((affiliation) => {
                    const isActing = actingAffiliationId === affiliation.id
                    const affiliationStatus = AFFILIATION_STATUS[affiliation.status] || AFFILIATION_STATUS.pending
                    return (
                      <div key={affiliation.id} className="space-y-3 rounded-lg border border-border/80 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <Link to={`/players/${affiliation.player_api_id}`} className="font-semibold text-foreground hover:text-primary hover:underline">
                              Player #{affiliation.player_api_id}
                            </Link>
                            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                              <span>Season: {affiliation.season || 'Not provided'}</span>
                              {formatDate(affiliation.created_at) ? <span>Submitted {formatDate(affiliation.created_at)}</span> : null}
                            </div>
                          </div>
                          <Badge className={affiliationStatus.className}>{affiliationStatus.label}</Badge>
                        </div>
                        {affiliation.review_note ? (
                          <p className="text-xs text-muted-foreground">Previous note: {affiliation.review_note}</p>
                        ) : null}
                        <div className="space-y-2">
                          <Input
                            value={affiliationNotes[affiliation.id] || ''}
                            onChange={(event) => onAffiliationNoteChange(affiliation.id, event.target.value)}
                            placeholder="Rejection note (optional)"
                            aria-label={`Rejection note for player ${affiliation.player_api_id}`}
                            maxLength={1000}
                            disabled={isActing}
                          />
                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-danger/30 text-danger hover:bg-danger/5"
                              disabled={Boolean(actingAffiliationId)}
                              onClick={() => onReviewAffiliation(affiliation, 'reject')}
                            >
                              {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                              Reject
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-good/30 text-good hover:bg-good/5"
                              disabled={Boolean(actingAffiliationId)}
                              onClick={() => onReviewAffiliation(affiliation, 'confirm')}
                            >
                              {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                              Confirm
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Player claim vouching</CardTitle>
              <CardDescription>Identity approval only. Profile content remains separately moderated.</CardDescription>
            </CardHeader>
            <CardContent>
              {vouchableClaims.length === 0 ? (
                <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                  No player claims are waiting for a vouch.
                </p>
              ) : (
                <div className="space-y-3">
                  {vouchableClaims.map((claim) => (
                    <div key={claim.id} className="flex flex-col gap-3 rounded-lg border border-border/80 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link to={`/players/${claim.player_api_id}`} className="font-semibold text-foreground hover:text-primary hover:underline">
                            Player #{claim.player_api_id}
                          </Link>
                          <VerificationBadge status={claim.verification_status} />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {RELATIONSHIP_LABELS[claim.relationship_type] || claim.relationship_type || 'Claimant'}
                          {formatDate(claim.created_at) ? ` · Submitted ${formatDate(claim.created_at)}` : ''}
                        </p>
                        {formatDate(claim.verification_checked_at) ? (
                          <p className="text-xs text-muted-foreground">Social profile checked {formatDate(claim.verification_checked_at)}</p>
                        ) : null}
                      </div>
                      <Button size="sm" onClick={() => onVouch(claim, clubEntry.club_name)} className="shrink-0">
                        <UserCheck className="mr-1.5 h-4 w-4" />
                        Vouch
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    )
  })
}

export function MyClub() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()

  if (!auth?.token) return <SignedOutState onSignIn={openLoginModal} />

  return <AuthenticatedMyClub key={auth.token} />
}

function AuthenticatedMyClub() {
  const [clubParams, setClubParams] = useSearchParams()
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()

  const [claims, setClaims] = useState([])
  const [clubs, setClubs] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadedToken, setLoadedToken] = useState(null)
  const [hasLoadedData, setHasLoadedData] = useState(false)
  const [dataError, setDataError] = useState(false)
  const [message, setMessage] = useState(null)
  const [programClaims, setProgramClaims] = useState([])
  const [programClaimsLoaded, setProgramClaimsLoaded] = useState(false)
  const [programClaimsError, setProgramClaimsError] = useState(false)
  const [programClaimsAttempt, setProgramClaimsAttempt] = useState(0)
  const [consoleEligibility, setConsoleEligibility] = useState({ candidates: null, pending: false, allowed: [], deniedProgramIds: [], erroredProgramIds: [] })
  const [selectedProgramId, setSelectedProgramId] = useState(null)

  const [claimOpen, setClaimOpen] = useState(false)
  const [clubSearch, setClubSearch] = useState('')
  const [clubSearchBusy, setClubSearchBusy] = useState(false)
  const [clubSearchComplete, setClubSearchComplete] = useState(false)
  const [clubSearchError, setClubSearchError] = useState(null)
  const [clubResults, setClubResults] = useState(EMPTY_CLUB_RESULTS)
  const [selectedClub, setSelectedClub] = useState(null)
  const [roleTitle, setRoleTitle] = useState('')
  const [claimMessage, setClaimMessage] = useState('')
  const [claimBusy, setClaimBusy] = useState(false)
  const [claimDone, setClaimDone] = useState(false)
  const [claimError, setClaimError] = useState(null)
  const [createdClaim, setCreatedClaim] = useState(null)

  const [verifyOpen, setVerifyOpen] = useState(false)
  const [verifyClaim, setVerifyClaim] = useState(null)
  const [proofUrl, setProofUrl] = useState('')
  const [verifyBusy, setVerifyBusy] = useState(false)
  const [verifyDone, setVerifyDone] = useState(false)
  const [verifyError, setVerifyError] = useState(null)
  const [verifyResult, setVerifyResult] = useState(null)
  const [codeCopyState, setCodeCopyState] = useState('idle')

  const [affiliationNotes, setAffiliationNotes] = useState({})
  const [actingAffiliationId, setActingAffiliationId] = useState(null)
  const [vouchTarget, setVouchTarget] = useState(null)
  const [vouchBusy, setVouchBusy] = useState(false)
  const [vouchError, setVouchError] = useState(null)

  const activeTokenRef = useRef(auth?.token)
  const dataRequestRef = useRef(0)
  const eligibilityRequestRef = useRef(0)
  const eligibilityStateRef = useRef(consoleEligibility)
  const clubSearchRequestRef = useRef(0)
  const verifyRequestRef = useRef(0)
  const verifyCloseTimerRef = useRef(null)

  useLayoutEffect(() => {
    activeTokenRef.current = auth?.token
    return () => {
      activeTokenRef.current = null
    }
  }, [auth?.token])

  useLayoutEffect(() => { eligibilityStateRef.current = consoleEligibility }, [consoleEligibility])

  const clearVerifyCloseTimer = useCallback(() => {
    if (verifyCloseTimerRef.current) {
      clearTimeout(verifyCloseTimerRef.current)
      verifyCloseTimerRef.current = null
    }
  }, [])

  useEffect(() => clearVerifyCloseTimer, [clearVerifyCloseTimer])

  const refreshData = useCallback(async ({ showLoading = false } = {}) => {
    const expectedToken = activeTokenRef.current
    if (!expectedToken) return false
    const requestId = dataRequestRef.current + 1
    dataRequestRef.current = requestId
    if (showLoading) {
      setLoading(true)
      setDataError(false)
    }
    try {
      const read = () => Promise.allSettled([APIService.getMyClubClaims(), APIService.getMyClub()])
      const results = await (showLoading ? watchEntryRead(read, () => {
        if (dataRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return
        setDataError(true)
        setLoadedToken(expectedToken)
        setLoading(false)
      }) : read())
      if (dataRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return false
      const failure = results.find(result => result.status === 'rejected')
      if (failure) throw failure.reason
      const [claimsResponse, clubsResponse] = results.map(result => result.value)
      setClaims(Array.isArray(claimsResponse?.claims) ? claimsResponse.claims : [])
      setClubs(Array.isArray(clubsResponse?.clubs) ? clubsResponse.clubs : [])
      setHasLoadedData(true)
      setDataError(false)
      return true
    } catch (error) {
      if (dataRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
        if (showLoading) setDataError(true)
        setMessage(current => !showLoading && current?.type === 'success'
          ? { ...current, text: `${current.text}. Saved, but the list couldn't be refreshed. Reload to see it.` }
          : { type: 'error', text: error.body?.error || error.message || 'Failed to load club data' })
      }
      return false
    } finally {
      if (dataRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
        setLoadedToken(expectedToken)
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (!auth?.token) {
      dataRequestRef.current += 1
      return undefined
    }
    const timer = setTimeout(() => {
      refreshData({ showLoading: true })
    }, 0)
    return () => {
      clearTimeout(timer)
      dataRequestRef.current += 1
    }
  }, [auth?.token, refreshData])

  useEffect(() => {
    if (!auth?.token) return undefined
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const response = await watchEntryRead(() => APIService.getMyProgramClaims(), () => {
          if (!cancelled && activeTokenRef.current === auth.token) {
            setProgramClaimsError(true)
            setProgramClaimsLoaded(true)
          }
        })
        if (!cancelled && activeTokenRef.current === auth.token) {
          setProgramClaims(Array.isArray(response?.claims) ? response.claims : [])
          setProgramClaimsLoaded(true)
          setProgramClaimsError(false)
        }
      } catch {
        if (!cancelled && activeTokenRef.current === auth.token) {
          setProgramClaimsError(true)
          setProgramClaimsLoaded(true)
        }
      }
    }, 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [auth?.token, programClaimsAttempt])

  const approvedProgramClaims = useMemo(() => programClaims.filter((programClaim) => (
    programClaim?.status === 'approved'
    && programClaim?.program?.platform_status === 'approved'
    && Number.isInteger(Number(programClaim?.program?.id))
    && Number(programClaim.program.id) > 0
  )), [programClaims])

  // Club staff access (dark): invited staff have no club claim, so their clubs come from their access grants.
  const staffFlagState = useClubEntryFeatures()
  const staffFlag = staffFlagState.enabled
  const [staffPrograms, setStaffPrograms] = useState([])
  const [staffProgramsLoaded, setStaffProgramsLoaded] = useState(false)
  const [staffProgramsError, setStaffProgramsError] = useState(false)
  const [staffProgramsAttempt, setStaffProgramsAttempt] = useState(0)
  useEffect(() => {
    if (!auth?.token || staffFlag !== true) return undefined
    let cancelled = false
    const expectedToken = auth.token
    const unavailable = () => {
      if (cancelled || activeTokenRef.current !== expectedToken) return
      setStaffProgramsError(true)
      setStaffProgramsLoaded(true)
    }
    watchEntryRead(() => APIService.request('/me/club-access'), unavailable).then((data) => {
      if (cancelled || activeTokenRef.current !== expectedToken) return
      setStaffPrograms((Array.isArray(data?.programs) ? data.programs : [])
        .filter((row) => Number.isInteger(Number(row?.program?.id)))
        .map((row) => ({ status: 'approved', program: row.program, staff_access: row.access })))
      setStaffProgramsLoaded(true)
      setStaffProgramsError(false)
    }).catch(unavailable)
    return () => { cancelled = true }
  }, [auth?.token, staffFlag, staffProgramsAttempt])
  const consoleCandidates = useMemo(() => {
    if (staffPrograms.length === 0) return approvedProgramClaims
    const claimed = new Set(approvedProgramClaims.map((programClaim) => Number(programClaim.program.id)))
    const added = staffPrograms.filter((row) => !claimed.has(Number(row.program.id)))
    return added.length ? [...approvedProgramClaims, ...added] : approvedProgramClaims
  }, [approvedProgramClaims, staffPrograms])
  const discoverySettled = programClaimsLoaded && !staffFlagState.pending
    && (staffFlag !== true || staffProgramsLoaded)

  // Discovery is additive. Share checks across candidate snapshots so an
  // independent source can grant entry without waiting or repeating a roster.
  const rosterReadsRef = useRef(new Map())
  const checkProgram = useCallback((programId, retry = false) => {
    if (retry) rosterReadsRef.current.delete(programId)
    if (!rosterReadsRef.current.has(programId)) {
      rosterReadsRef.current.set(programId, APIService.getClubRoster(programId))
    }
    return rosterReadsRef.current.get(programId)
  }, [])
  useEffect(() => {
    let cancelled = false
    const requestId = ++eligibilityRequestRef.current
    const expectedToken = auth?.token
    const timer = setTimeout(() => {
      const previous = eligibilityStateRef.current
      const retained = previous.allowed.filter(({ programClaim }) => consoleCandidates.some(row => Number(row.program.id) === Number(programClaim.program.id)))
      const deniedProgramIds = previous.deniedProgramIds.filter(id => consoleCandidates.some(row => Number(row.program.id) === id))
      const unchecked = consoleCandidates.filter(row => !retained.some(item => Number(item.programClaim.program.id) === Number(row.program.id)) && !deniedProgramIds.includes(Number(row.program.id)))
      let remaining = unchecked.length
      setConsoleEligibility({ candidates: consoleCandidates, pending: remaining > 0, allowed: retained, deniedProgramIds, erroredProgramIds: [] })
      for (const programClaim of unchecked) {
        const programId = Number(programClaim.program.id)
        let waiting = true
        const finishWaiting = () => { if (waiting) { waiting = false; remaining-- } }
        const current = () => !cancelled && activeTokenRef.current === expectedToken && eligibilityRequestRef.current === requestId
        watchEntryRead(() => checkProgram(programId), () => {
          if (!current()) return
          finishWaiting()
          setConsoleEligibility(state => ({ ...state, pending: remaining > 0, erroredProgramIds: [...new Set([...state.erroredProgramIds, programId])] }))
        }).then(roster => ({ programClaim, roster }), error => error).then(result => {
          if (cancelled || activeTokenRef.current !== expectedToken || eligibilityRequestRef.current !== requestId) return
          finishWaiting()
          setConsoleEligibility(current => ({
            ...current,
            pending: remaining > 0,
            allowed: result.programClaim ? [...current.allowed, result].sort((a, b) => consoleCandidates.findIndex(row => Number(row.program.id) === Number(a.programClaim.program.id)) - consoleCandidates.findIndex(row => Number(row.program.id) === Number(b.programClaim.program.id))) : current.allowed,
            deniedProgramIds: result.status === 403 ? [...current.deniedProgramIds, programId] : current.deniedProgramIds,
            erroredProgramIds: !result.programClaim && result.status !== 403 ? [...new Set([...current.erroredProgramIds, programId])] : current.erroredProgramIds.filter(id => id !== programId),
          }))
          if (result.programClaim) setSelectedProgramId(current => current ?? programId)
        })
      }
    }, 0)
    return () => {
      cancelled = true
      if (eligibilityRequestRef.current === requestId) eligibilityRequestRef.current += 1
      clearTimeout(timer)
    }
  }, [consoleCandidates, auth?.token, checkProgram])

  useEffect(() => {
    const query = clubSearch.trim()
    if (!claimOpen || claimDone || query.length < 2) return undefined

    const requestId = clubSearchRequestRef.current + 1
    clubSearchRequestRef.current = requestId
    const expectedToken = auth?.token
    const timer = setTimeout(async () => {
      if (clubSearchRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return
      setClubSearchBusy(true)
      setClubSearchError(null)
      try {
        const response = await APIService.searchClubs(query)
        if (clubSearchRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return
        setClubResults({
          api_teams: Array.isArray(response?.api_teams) ? response.api_teams : [],
          local_clubs: Array.isArray(response?.local_clubs) ? response.local_clubs : [],
        })
        setClubSearchComplete(true)
      } catch (error) {
        if (clubSearchRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return
        setClubResults(EMPTY_CLUB_RESULTS)
        setClubSearchComplete(false)
        setClubSearchError(error.body?.error || error.message || 'Failed to search clubs')
      } finally {
        if (clubSearchRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
          setClubSearchBusy(false)
        }
      }
    }, 300)

    return () => {
      clearTimeout(timer)
      if (clubSearchRequestRef.current === requestId) clubSearchRequestRef.current += 1
    }
  }, [auth?.token, claimDone, claimOpen, clubSearch])

  const resetClaimDialog = () => {
    clubSearchRequestRef.current += 1
    setClubSearch('')
    setClubSearchBusy(false)
    setClubSearchComplete(false)
    setClubSearchError(null)
    setClubResults(EMPTY_CLUB_RESULTS)
    setSelectedClub(null)
    setRoleTitle('')
    setClaimMessage('')
    setClaimBusy(false)
    setClaimDone(false)
    setClaimError(null)
    setCreatedClaim(null)
    setCodeCopyState('idle')
  }

  const openClaimDialog = () => {
    if (!auth?.token) {
      openLoginModal()
      return
    }
    resetClaimDialog()
    setClaimOpen(true)
  }

  const updateClubSearch = (value) => {
    clubSearchRequestRef.current += 1
    setClubSearch(value)
    setClubSearchBusy(false)
    setClubSearchComplete(false)
    setClubSearchError(null)
    setClubResults(EMPTY_CLUB_RESULTS)
    setSelectedClub(null)
    setClaimError(null)
  }

  const chooseClub = (kind, club) => {
    setSelectedClub({ kind, club })
    setClaimError(null)
  }

  const submitClaim = async () => {
    const title = roleTitle.trim()
    if (claimBusy) return
    if (!selectedClub) {
      setClaimError('Select a club from the search results.')
      return
    }
    if (title.length < 2) {
      setClaimError('Enter a role title of at least 2 characters.')
      return
    }

    const expectedToken = auth?.token
    const clubPayload = selectedClub.kind === 'api'
      ? { team_api_id: selectedClub.club.team_api_id }
      : { local_club_id: selectedClub.club.id }
    setClaimBusy(true)
    setClaimError(null)
    try {
      const response = await APIService.submitClubClaim({
        ...clubPayload,
        role_title: title,
        message: claimMessage.trim() || undefined,
      })
      if (activeTokenRef.current !== expectedToken) return
      setCreatedClaim(response?.claim || null)
      setClaimDone(true)
      setMessage({ type: 'success', text: 'Club claim submitted for review' })
      await refreshData()
    } catch (error) {
      if (activeTokenRef.current === expectedToken) {
        setClaimError(error.body?.error || error.message || 'Failed to submit club claim')
      }
    } finally {
      if (activeTokenRef.current === expectedToken) setClaimBusy(false)
    }
  }

  const copyVerificationCode = async (code) => {
    if (!code) return
    const expectedToken = activeTokenRef.current
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      setCodeCopyState('failed')
      return
    }
    try {
      await navigator.clipboard.writeText(code)
      if (activeTokenRef.current === expectedToken) setCodeCopyState('copied')
    } catch {
      if (activeTokenRef.current === expectedToken) setCodeCopyState('failed')
    }
  }

  const openVerificationDialog = (claim) => {
    clearVerifyCloseTimer()
    verifyRequestRef.current += 1
    setVerifyClaim(claim)
    setProofUrl(claim.verification_proof_url || '')
    setVerifyBusy(false)
    setVerifyDone(false)
    setVerifyError(null)
    setVerifyResult(null)
    setCodeCopyState('idle')
    setVerifyOpen(true)
  }

  const closeVerificationDialog = () => {
    if (verifyBusy) return
    clearVerifyCloseTimer()
    verifyRequestRef.current += 1
    setVerifyOpen(false)
    setVerifyClaim(null)
    setVerifyDone(false)
    setVerifyError(null)
    setVerifyResult(null)
  }

  const submitVerification = async () => {
    const url = proofUrl.trim()
    if (!url || verifyBusy || !verifyClaim?.id) return
    const expectedToken = auth?.token
    const claimId = verifyClaim.id
    const requestId = verifyRequestRef.current + 1
    verifyRequestRef.current = requestId
    setVerifyBusy(true)
    setVerifyDone(false)
    setVerifyError(null)
    setVerifyResult(null)
    try {
      const response = await APIService.verifyClubClaimProof(claimId, { proof_url: url })
      const checkedClaim = response?.claim || null
      if (verifyRequestRef.current !== requestId || activeTokenRef.current !== expectedToken) return
      setVerifyResult(checkedClaim)
      setVerifyClaim(checkedClaim || verifyClaim)
      setVerifyDone(true)
      await refreshData()
      if (checkedClaim?.verification_status === 'code_found') {
        verifyCloseTimerRef.current = setTimeout(() => {
          if (verifyRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
            setVerifyOpen(false)
            setVerifyClaim(null)
            setVerifyDone(false)
            setVerifyResult(null)
          }
          verifyCloseTimerRef.current = null
        }, 1600)
      }
    } catch (error) {
      if (verifyRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
        setVerifyError(error.body?.error || error.message || 'Failed to check this profile')
      }
    } finally {
      if (verifyRequestRef.current === requestId && activeTokenRef.current === expectedToken) {
        setVerifyBusy(false)
      }
    }
  }

  const reviewAffiliation = async (affiliation, action) => {
    if (actingAffiliationId) return
    const expectedToken = auth?.token
    setActingAffiliationId(affiliation.id)
    try {
      if (action === 'confirm') {
        await APIService.confirmClubAffiliation(affiliation.id)
      } else {
        await APIService.rejectClubAffiliation(affiliation.id, {
          note: affiliationNotes[affiliation.id]?.trim() || undefined,
        })
      }
      if (activeTokenRef.current !== expectedToken) return
      setMessage({
        type: 'success',
        text: action === 'confirm' ? 'Player affiliation confirmed' : 'Player affiliation rejected',
      })
      setAffiliationNotes((current) => {
        const next = { ...current }
        delete next[affiliation.id]
        return next
      })
      await refreshData()
    } catch (error) {
      if (activeTokenRef.current === expectedToken) {
        setMessage({ type: 'error', text: error.body?.error || error.message || 'Failed to update affiliation' })
      }
    } finally {
      if (activeTokenRef.current === expectedToken) setActingAffiliationId(null)
    }
  }

  const openVouchDialog = (claim, clubName) => {
    setVouchTarget({ claim, clubName })
    setVouchError(null)
  }

  const submitVouch = async () => {
    if (!vouchTarget?.claim?.id || vouchBusy) return
    const expectedToken = auth?.token
    setVouchBusy(true)
    setVouchError(null)
    try {
      await APIService.vouchPlayerClaim(vouchTarget.claim.id)
      if (activeTokenRef.current !== expectedToken) return
      setMessage({ type: 'success', text: `Player #${vouchTarget.claim.player_api_id} claim approved by your vouch` })
      setVouchTarget(null)
      await refreshData()
    } catch (error) {
      if (activeTokenRef.current === expectedToken) {
        const text = error.body?.error || error.message || 'Failed to vouch for player claim'
        setVouchError(text)
        setMessage({ type: 'error', text })
      }
    } finally {
      if (activeTokenRef.current === expectedToken) setVouchBusy(false)
    }
  }

  const clubResultCount = clubResults.api_teams.length + clubResults.local_clubs.length
  const activeConsoleProgram = consoleEligibility.allowed.find(({ programClaim }) => (
    Number(programClaim.program.id) === Number(clubParams.get("program") || selectedProgramId)
  )) || consoleEligibility.allowed[0]
  const handleConsoleAccessDenied = useCallback((programId) => {
    setConsoleEligibility((current) => ({
      ...current,
      allowed: current.allowed.filter(({ programClaim }) => Number(programClaim.program.id) !== Number(programId)),
      deniedProgramIds: [...new Set([...current.deniedProgramIds, Number(programId)])],
    }))
  }, [])

  const retryConsoleEligibility = useCallback(async () => {
    const expectedToken = auth?.token
    const retryProgramIds = consoleEligibility.erroredProgramIds
    if (!expectedToken || consoleEligibility.pending || retryProgramIds.length === 0) return
    const retryProgramIdSet = new Set(retryProgramIds.map(Number))
    const retryClaims = consoleCandidates.filter((programClaim) => (
      retryProgramIdSet.has(Number(programClaim.program.id))
    ))
    const requestId = ++eligibilityRequestRef.current
    setConsoleEligibility((current) => ({ ...current, pending: true }))
    let remaining = retryClaims.length
    await Promise.all(retryClaims.map(async programClaim => {
      const programId = Number(programClaim.program.id)
      let roster
      let error
      let waiting = true
      const finishWaiting = () => { if (waiting) { waiting = false; remaining-- } }
      try {
        roster = await watchEntryRead(() => checkProgram(programId, true), () => {
          if (activeTokenRef.current !== expectedToken || eligibilityRequestRef.current !== requestId) return
          finishWaiting()
          setConsoleEligibility(current => ({ ...current, pending: remaining > 0 }))
        })
      } catch (failure) { error = failure }
      if (activeTokenRef.current !== expectedToken || eligibilityRequestRef.current !== requestId) return
      finishWaiting()
      setConsoleEligibility(current => ({
        ...current,
        pending: remaining > 0,
        allowed: error ? current.allowed : [...current.allowed, { programClaim, roster }].sort((a, b) => consoleCandidates.findIndex(row => Number(row.program.id) === Number(a.programClaim.program.id)) - consoleCandidates.findIndex(row => Number(row.program.id) === Number(b.programClaim.program.id))),
        deniedProgramIds: error?.status === 403 ? [...new Set([...current.deniedProgramIds, programId])] : current.deniedProgramIds,
        erroredProgramIds: !error || error.status === 403 ? current.erroredProgramIds.filter(id => id !== programId) : current.erroredProgramIds,
      }))
      if (!error) setSelectedProgramId(current => current ?? programId)
    }))
  }, [consoleCandidates, auth?.token, consoleEligibility.erroredProgramIds, consoleEligibility.pending, checkProgram])

  const retryClubAccess = () => {
    if (!loading && (dataError || !hasLoadedData)) {
      setMessage(null)
      refreshData({ showLoading: true })
    }
    if (programClaimsError) {
      setProgramClaimsLoaded(false)
      setProgramClaimsError(false)
      setProgramClaimsAttempt(current => current + 1)
    }
    if (staffFlagState.error) staffFlagState.retry()
    if (staffProgramsError) {
      setStaffProgramsLoaded(false)
      setStaffProgramsError(false)
      setStaffProgramsAttempt(current => current + 1)
    }
    retryConsoleEligibility()
  }

  const pendingAffiliationIds = new Set()
  const vouchableClaimIds = new Set()
  for (const clubEntry of clubs) {
    for (const affiliation of clubEntry.pending_affiliations || []) {
      if (affiliation?.id != null) pendingAffiliationIds.add(String(affiliation.id))
    }
    for (const claim of clubEntry.vouchable_player_claims || []) {
      if (claim?.id != null) vouchableClaimIds.add(String(claim.id))
    }
  }
  const moderationCount = pendingAffiliationIds.size + vouchableClaimIds.size
  const moderationWorkspace = (
    <ClubModerationWorkspace
      clubs={clubs}
      actingAffiliationId={actingAffiliationId}
      affiliationNotes={affiliationNotes}
      onAffiliationNoteChange={(affiliationId, value) => setAffiliationNotes((current) => ({ ...current, [affiliationId]: value }))}
      onReviewAffiliation={reviewAffiliation}
      onVouch={openVouchDialog}
    />
  )
  const statusAlert = message ? (
    <Alert className={message.type === 'error' ? 'border-danger/30 bg-danger/5' : 'border-good/30 bg-good/5'}>
      {message.type === 'error' ? (
        <AlertCircle className="h-4 w-4 text-danger" />
      ) : (
        <CheckCircle2 className="h-4 w-4 text-good" />
      )}
      <AlertDescription className={message.type === 'error' ? 'text-danger' : 'text-good'}>
        {message.text}
      </AlertDescription>
    </Alert>
  ) : null
  const readsPending = loading || loadedToken !== auth.token || !discoverySettled
    || consoleEligibility.candidates !== consoleCandidates || consoleEligibility.pending
  const discoveryError = dataError || programClaimsError || staffFlagState.error || staffProgramsError
    || (!activeConsoleProgram && consoleEligibility.erroredProgramIds.length > 0)
  const hasLegacyWorkspace = hasLoadedData && (claims.length > 0 || clubs.length > 0)
  const hasWorkspace = Boolean(activeConsoleProgram) || hasLegacyWorkspace
  const accessPending = !hasWorkspace && readsPending
  const accessError = !hasWorkspace && (discoveryError || !hasLoadedData || consoleEligibility.erroredProgramIds.length > 0)
  const showConsole = Boolean(activeConsoleProgram)
  const activeProgramId = showConsole ? Number(activeConsoleProgram.programClaim.program.id) : null
  const openingProgram = showConsole && consoleEligibility.pending && consoleCandidates.find(row => (
    Number(row.program.id) === Number(clubParams.get('program')) && Number(row.program.id) !== activeProgramId
  ))
  const discoveryStatus = discoveryError ? (
    <Alert role="status"><AlertDescription>
      Some of your clubs couldn&apos;t be checked. <Button onClick={retryClubAccess}>Retry</Button>
    </AlertDescription></Alert>
  ) : readsPending && !openingProgram ? <p role="status">Checking your other clubs…</p> : null

  return (
    <div className={showConsole ? undefined : 'fl-club-entry min-h-screen bg-chalk'}>
      {showConsole ? (
        <MyClubConsole
          key={activeProgramId}
          programClaim={activeConsoleProgram.programClaim}
          initialRoster={activeConsoleProgram.roster}
          programOptions={consoleEligibility.allowed.map(({ programClaim }) => programClaim)}
          moderationContent={clubs.length > 0 ? <div className="space-y-4">{statusAlert}{moderationWorkspace}</div> : null}
          moderationCount={moderationCount}
          entryStatus={discoveryStatus || openingProgram ? <>{discoveryStatus}{openingProgram && <p role="status">Opening {openingProgram.program.name} when it&apos;s ready…</p>}</> : null}
          erroredProgramCount={consoleEligibility.erroredProgramIds.length}
          checkingPrograms={consoleEligibility.pending}
          onProgramChange={id => { setSelectedProgramId(id); setClubParams({ program: String(id) }) }}
          onRetryPrograms={retryConsoleEligibility}
          onAccessDenied={() => handleConsoleAccessDenied(activeProgramId)}
        />
      ) : (
        <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="eyebrow mb-4 inline-flex items-center gap-2">
              <ShieldCheck className="h-3.5 w-3.5" />
              Club officials
            </p>
            <h1 className="display text-[56px] sm:text-[72px]">My Club</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
              Prove your role, confirm who represents your club and vouch for player identities you know firsthand.
            </p>
          </div>
          <Button
            onClick={openClaimDialog}
            className="shrink-0"
            disabled={accessPending || accessError}
          >
            <Plus className="mr-1.5 h-4 w-4" />
            Claim your club
          </Button>
        </header>

        {hasLegacyWorkspace && discoveryStatus}
        {!accessError && statusAlert}

        {!accessPending && accessError ? (
          <Alert className="border-warn/30 bg-warn/5">
            <AlertCircle className="h-4 w-4 text-gold-text" />
            <AlertDescription className="flex flex-wrap items-center gap-3 text-gold-text">
              We couldn&apos;t load your club. Try again.
              <Button
                variant="outline"
                className="min-h-11 min-w-20 text-gold-text"
                onClick={retryClubAccess}
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {accessPending ? (
          <Card>
            <CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              <CleatLoader />
            </CardContent>
          </Card>
        ) : accessError ? null : (
          <>
            {claims.length === 0 ? (
              <Card className="overflow-hidden border-dashed">
                <CardContent className="flex flex-col items-center gap-4 px-6 py-14 text-center">
                  <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                    <Building2 className="h-6 w-6 text-primary" />
                  </span>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight text-foreground">Represent a club?</h2>
                    <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
                      Claim an official or community club, verify your role through a public social profile and wait for admin approval.
                    </p>
                  </div>
                  <Button onClick={openClaimDialog}>Claim your club</Button>
                  <Link to="/local-players/new" className="text-sm font-medium text-primary hover:underline">
                    Create a player profile
                  </Link>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Your club claims</CardTitle>
                  <CardDescription>Admin approval is required before club-management tools unlock.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {claims.map((claim) => (
                    <div key={claim.id} className="flex flex-col gap-4 rounded-lg border border-border/80 bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-foreground">{claim.club_name || 'Club claim'}</h3>
                          <StatusBadge status={claim.status} styles={CLAIM_STATUS} />
                          <VerificationBadge status={claim.verification_status} />
                        </div>
                        <p className="text-sm text-muted-foreground">{claim.role_title || 'Club official'}</p>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                          {formatDate(claim.created_at) ? <span>Submitted {formatDate(claim.created_at)}</span> : null}
                          {formatDate(claim.verification_checked_at) ? (
                            <span>Social profile checked {formatDate(claim.verification_checked_at)}</span>
                          ) : null}
                        </div>
                      </div>
                      {claim.status === 'pending' ? (
                        <Button variant="outline" size="sm" onClick={() => openVerificationDialog(claim)} className="shrink-0">
                          <ShieldCheck className="mr-1.5 h-4 w-4" />
                          Verify claim
                        </Button>
                      ) : null}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {moderationWorkspace}
          </>
        )}
        </div>
      )}

      <Dialog
        open={claimOpen}
        onOpenChange={(open) => {
          if (claimBusy) return
          setClaimOpen(open)
          if (!open) resetClaimDialog()
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Claim your club</DialogTitle>
            <DialogDescription>
              Search official and community clubs, then tell us the role you hold. Every claim is reviewed.
            </DialogDescription>
          </DialogHeader>

          {claimDone ? (
            <div className="space-y-4 py-2">
              <div className="flex items-center gap-2 text-sm text-good" role="status" aria-live="polite">
                <Check className="h-4 w-4" />
                Submitted for review
              </div>
              <VerificationCode
                code={createdClaim?.verification_code}
                copyState={codeCopyState}
                onCopy={copyVerificationCode}
              />
              <VerificationInstructions />
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="my-club-search">Search clubs</Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="my-club-search"
                    type="search"
                    placeholder="Search by club name"
                    value={clubSearch}
                    onChange={(event) => updateClubSearch(event.target.value)}
                    maxLength={200}
                    disabled={claimBusy}
                    className="pl-9"
                    autoComplete="off"
                  />
                </div>
                {clubSearch.trim().length > 0 && clubSearch.trim().length < 2 ? (
                  <p className="text-xs text-muted-foreground">Enter at least 2 characters.</p>
                ) : null}
              </div>

              {clubSearchBusy ? (
                <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground" role="status">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching clubs…
                </div>
              ) : null}

              {clubSearchError ? <p className="text-xs text-destructive" role="alert">{clubSearchError}</p> : null}

              {!clubSearchBusy && clubSearchComplete && clubResultCount > 0 ? (
                <div className="max-h-64 space-y-4 overflow-y-auto pr-1">
                  {clubResults.api_teams.length > 0 ? (
                    <div className="space-y-2">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Official clubs</p>
                      <div className="space-y-1" role="listbox" aria-label="Official clubs">
                        {clubResults.api_teams.map((club) => {
                          const selected = selectedClub?.kind === 'api'
                            && Number(selectedClub.club.team_api_id) === Number(club.team_api_id)
                          return (
                            <button
                              key={`api-${club.team_api_id}`}
                              type="button"
                              role="option"
                              aria-selected={selected}
                              onClick={() => chooseClub('api', club)}
                              disabled={claimBusy}
                              className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${selected
                                ? 'border-primary/50 bg-primary/5'
                                : 'border-border/70 hover:border-primary/30 hover:bg-muted/50'}`}
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-medium text-foreground">{club.name}</span>
                                {club.country ? <span className="block truncate text-xs text-muted-foreground">{club.country}</span> : null}
                              </span>
                              {selected ? <Check className="h-4 w-4 shrink-0 text-primary" /> : null}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}

                  {clubResults.local_clubs.length > 0 ? (
                    <div className="space-y-2">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Community clubs</p>
                      <div className="space-y-1" role="listbox" aria-label="Community clubs">
                        {clubResults.local_clubs.map((club) => {
                          const selected = selectedClub?.kind === 'local'
                            && Number(selectedClub.club.id) === Number(club.id)
                          const location = [club.city, club.country].filter(Boolean).join(', ')
                          return (
                            <button
                              key={`local-${club.id}`}
                              type="button"
                              role="option"
                              aria-selected={selected}
                              onClick={() => chooseClub('local', club)}
                              disabled={claimBusy}
                              className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${selected
                                ? 'border-primary/50 bg-primary/5'
                                : 'border-border/70 hover:border-primary/30 hover:bg-muted/50'}`}
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-medium text-foreground">{club.name}</span>
                                {location || club.level ? (
                                  <span className="block truncate text-xs text-muted-foreground">
                                    {[location, club.level].filter(Boolean).join(' · ')}
                                  </span>
                                ) : null}
                              </span>
                              {selected ? <Check className="h-4 w-4 shrink-0 text-primary" /> : null}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {!clubSearchBusy && clubSearchComplete && clubResultCount === 0 ? (
                <p className="rounded-md border border-dashed px-3 py-5 text-center text-sm text-muted-foreground">
                  No matching clubs found.
                </p>
              ) : null}

              {selectedClub ? (
                <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
                  <Check className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 truncate font-medium text-foreground">Selected: {selectedClub.club.name}</span>
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="my-club-role-title">Your role title</Label>
                <Input
                  id="my-club-role-title"
                  value={roleTitle}
                  onChange={(event) => setRoleTitle(event.target.value)}
                  placeholder="e.g. Academy director"
                  minLength={2}
                  maxLength={100}
                  disabled={claimBusy}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="my-club-claim-message">Message (optional)</Label>
                <Textarea
                  id="my-club-claim-message"
                  value={claimMessage}
                  onChange={(event) => setClaimMessage(event.target.value)}
                  placeholder="Anything that helps us verify your role"
                  maxLength={1000}
                  rows={3}
                  disabled={claimBusy}
                />
              </div>

              {claimError ? <p className="text-xs text-destructive" role="alert">{claimError}</p> : null}
            </div>
          )}

          {claimDone ? (
            <DialogFooter>
              <Button onClick={() => { setClaimOpen(false); resetClaimDialog() }}>Done</Button>
            </DialogFooter>
          ) : (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setClaimOpen(false)} disabled={claimBusy}>Cancel</Button>
              <Button onClick={submitClaim} disabled={claimBusy || !selectedClub || roleTitle.trim().length < 2}>
                {claimBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                {claimBusy ? 'Submitting…' : 'Submit claim'}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={verifyOpen} onOpenChange={(open) => { if (!open) closeVerificationDialog() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Verify your club role</DialogTitle>
            <DialogDescription>
              A best-effort social profile check helps our admin review your claim. It does not approve the claim automatically.
            </DialogDescription>
          </DialogHeader>

          {verifyDone ? (
            <div className="space-y-3 py-2" role="status" aria-live="polite">
              <div className={verifyResult?.verification_status === 'code_found'
                ? 'flex items-start gap-2 text-sm font-medium text-good'
                : 'flex items-start gap-2 text-sm font-medium text-gold-text'}>
                {verifyResult?.verification_status === 'code_found' ? (
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
                ) : (
                  <Search className="mt-0.5 h-4 w-4 shrink-0" />
                )}
                <span>
                  {verifyResult?.verification_status === 'code_found'
                    ? 'Code detected — an admin will review your claim'
                    : "We couldn't find the code"}
                </span>
              </div>
              {verifyResult?.verification_note ? (
                <p className="rounded-md bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                  {verifyResult.verification_note}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <VerificationCode
                code={verifyClaim?.verification_code}
                copyState={codeCopyState}
                onCopy={copyVerificationCode}
              />
              <VerificationInstructions />
              <div className="space-y-2">
                <Label htmlFor="club-claim-proof-url">Public profile URL</Label>
                <Input
                  id="club-claim-proof-url"
                  type="url"
                  placeholder="https://instagram.com/your-club-profile"
                  value={proofUrl}
                  onChange={(event) => setProofUrl(event.target.value)}
                  maxLength={500}
                  disabled={verifyBusy}
                  aria-invalid={Boolean(verifyError)}
                  aria-describedby={verifyError ? 'club-claim-proof-error' : undefined}
                />
              </div>
              {verifyError ? (
                <p id="club-claim-proof-error" className="text-xs text-destructive" role="alert">{verifyError}</p>
              ) : null}
            </div>
          )}

          {!verifyDone ? (
            <DialogFooter>
              <Button variant="ghost" onClick={closeVerificationDialog} disabled={verifyBusy}>Cancel</Button>
              <Button onClick={submitVerification} disabled={verifyBusy || !proofUrl.trim()}>
                {verifyBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                {verifyBusy ? 'Checking…' : 'Verify'}
              </Button>
            </DialogFooter>
          ) : verifyResult?.verification_status !== 'code_found' ? (
            <DialogFooter>
              <Button variant="ghost" onClick={closeVerificationDialog}>Close</Button>
              <Button
                variant="outline"
                onClick={() => {
                  setVerifyDone(false)
                  setVerifyResult(null)
                }}
              >
                Try again
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(vouchTarget)}
        onOpenChange={(open) => {
          if (!open && !vouchBusy) {
            setVouchTarget(null)
            setVouchError(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Vouch for Player #{vouchTarget?.claim?.player_api_id}</DialogTitle>
            <DialogDescription>
              Confirm this person&apos;s identity for {vouchTarget?.clubName || 'your club'}.
            </DialogDescription>
          </DialogHeader>
          <Alert className="border-warn/30 bg-warn/5">
            <AlertCircle className="h-4 w-4 text-gold-text" />
            <AlertDescription className="text-gold-text">
              Vouching approves this claim immediately. Only vouch for players you know are who they say they are.
            </AlertDescription>
          </Alert>
          {vouchError ? <p className="text-sm text-destructive" role="alert">{vouchError}</p> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setVouchTarget(null)} disabled={vouchBusy}>Cancel</Button>
            <Button onClick={submitVouch} disabled={vouchBusy}>
              {vouchBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <UserCheck className="mr-1.5 h-4 w-4" />}
              {vouchBusy ? 'Approving…' : 'Confirm vouch'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default MyClub
