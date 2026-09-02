import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Clapperboard,
  CalendarDays,
  ShieldCheck,
  UserSquare,
  Plus,
  Pencil,
  Trash2,
  ArrowUp,
  ArrowDown,
  Loader2,
  Check,
  Sparkles,
  Image as ImageIcon,
  ImagePlus,
  Star,
  Search,
  Building2,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { formatDateOnly, toLocalISODate } from '@/lib/dateOnly'
import { track } from '@/lib/track'
import { isYouTubeUrl } from '@/lib/youtube'
import { VideoEmbed } from '@/components/VideoEmbed'
import { ProvenanceChip } from '@/components/SelfReportedBadge'
import { VerificationCode, VerificationInstructions } from '@/components/showcase/VerificationCode'
import { useAuth, useAuthUI } from '@/context/AuthContext'

const RELATIONSHIP_OPTIONS = [
  { value: 'player', label: 'Player' },
  { value: 'agent', label: 'Agent' },
  { value: 'guardian', label: 'Parent / Guardian' },
  { value: 'club_official', label: 'Club official' },
]

const CLAIM_CONTRACT_STATUS_OPTIONS = [
  { value: 'free_agent', label: 'Free agent' },
  { value: 'contracted', label: 'Contracted' },
  { value: 'unknown', label: 'Not sure' },
]

const FOOT_OPTIONS = [
  { value: 'left', label: 'Left' },
  { value: 'right', label: 'Right' },
  { value: 'both', label: 'Both' },
]

const CONTRACT_STATUS_OPTIONS = [
  { value: 'under_contract', label: 'Under contract' },
  { value: 'expiring', label: 'Contract expiring' },
  { value: 'free_agent', label: 'Free agent' },
]

const AVAILABILITY_OPTIONS = [
  { value: 'open_to_moves', label: 'Open to moves' },
  { value: 'not_looking', label: 'Not looking' },
  { value: 'trial_available', label: 'Available for trials' },
]

const CLUB_LEVEL_OPTIONS = [
  { value: 'grassroots', label: 'Grassroots' },
  { value: 'academy', label: 'Academy' },
  { value: 'youth', label: 'Youth' },
  { value: 'semi_pro', label: 'Semi-professional' },
  { value: 'professional', label: 'Professional' },
  { value: 'other', label: 'Other' },
]

const EMPTY_CLUB_RESULTS = { api_teams: [], local_clubs: [] }
const EMPTY_LOCAL_CLUB_FORM = { name: '', country: '', city: '', level: '' }
const PUBLIC_AFFILIATION_STATUSES = new Set(['self_reported', 'club_confirmed'])
const GAME_OWNER_RELATIONSHIPS = new Set(['player', 'guardian', 'agent'])

const PHOTO_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const PHOTO_MAX_BYTES = 8 * 1024 * 1024
const MATCH_HOME_AWAY_OPTIONS = [
  { value: 'home', label: 'Home' },
  { value: 'away', label: 'Away' },
  { value: 'neutral', label: 'Neutral venue' },
]

function emptyMatchForm() {
  return {
    match_date: '',
    competition: '',
    opponent: '',
    home_away: 'home',
    result_for: '',
    result_against: '',
    minutes: '0',
    goals: '0',
    assists: '0',
    yellows: '0',
    reds: '0',
    saves: '',
    goals_conceded: '',
    note: '',
  }
}

function matchToForm(match) {
  const form = emptyMatchForm()
  for (const key of Object.keys(form)) {
    if (match?.[key] !== null && typeof match?.[key] !== 'undefined') {
      form[key] = String(match[key])
    }
  }
  return form
}

function parseBoundedInteger(value, fieldLabel, maximum, { nullable = false } = {}) {
  if (nullable && value === '') return { value: null }
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > maximum) {
    return { error: `${fieldLabel} must be a whole number from 0 to ${maximum}.` }
  }
  return { value: parsed }
}

function validateMatchForm(form, isGoalkeeper) {
  if (!formatDateOnly(form.match_date)) return 'Enter a valid match date.'
  if (form.match_date > toLocalISODate(new Date())) return 'Match date cannot be in the future.'

  const competition = form.competition.trim()
  if (competition.length > 120) return 'Competition must be 120 characters or fewer.'

  const opponent = form.opponent.trim()
  if (!opponent) return 'Enter the opponent.'
  if (opponent.length > 120) return 'Opponent must be 120 characters or fewer.'
  if (!MATCH_HOME_AWAY_OPTIONS.some((option) => option.value === form.home_away)) {
    return 'Choose whether the game was home, away or at a neutral venue.'
  }

  for (const [key, label] of [['result_for', 'Score for'], ['result_against', 'Score against']]) {
    const parsed = parseBoundedInteger(form[key], label, 20, { nullable: true })
    if (parsed.error) return parsed.error
  }

  const minutes = parseBoundedInteger(form.minutes, 'Minutes', 130)
  if (minutes.error) return minutes.error
  for (const [key, label] of [
    ['goals', 'Goals'],
    ['assists', 'Assists'],
    ['yellows', 'Yellow cards'],
    ['reds', 'Red cards'],
  ]) {
    const parsed = parseBoundedInteger(form[key], label, 20)
    if (parsed.error) return parsed.error
  }
  if (isGoalkeeper) {
    for (const [key, label] of [['saves', 'Saves'], ['goals_conceded', 'Goals conceded']]) {
      const parsed = parseBoundedInteger(form[key], label, 20, { nullable: true })
      if (parsed.error) return parsed.error
    }
  }
  if (form.note.trim().length > 500) return 'Note must be 500 characters or fewer.'
  return null
}

function buildMatchPayload(form, isGoalkeeper) {
  const integer = (key, nullable = false) => (
    nullable && form[key] === '' ? null : Number(form[key])
  )
  return {
    match_date: form.match_date,
    competition: form.competition.trim() || null,
    opponent: form.opponent.trim(),
    home_away: form.home_away,
    result_for: integer('result_for', true),
    result_against: integer('result_against', true),
    minutes: integer('minutes'),
    goals: integer('goals'),
    assists: integer('assists'),
    yellows: integer('yellows'),
    reds: integer('reds'),
    saves: isGoalkeeper ? integer('saves', true) : null,
    goals_conceded: isGoalkeeper ? integer('goals_conceded', true) : null,
    note: form.note.trim() || null,
  }
}

function isGoalkeeperPosition(position) {
  const normalized = String(position || '').trim().toLowerCase()
  return /(^|[^a-z])(g|gk|goalkeeper|keeper)(?=$|[^a-z])/.test(normalized)
}

function normalizeSeasonStart(value) {
  const match = String(value ?? '').trim().match(/^(\d{4})(?:\/\d{2,4})?$/)
  return match ? Number(match[1]) : null
}

function matchMutationError(error, fallback) {
  if (error?.status === 401) return 'Your session expired. Sign in and try again.'
  if (error?.status === 403) return 'Only an approved profile owner can manage these games.'
  if (error?.status === 404) return 'This game is no longer available. Refresh and try again.'
  if (error?.status === 409) return error.body?.error || 'This game conflicts with an existing entry.'
  if (error?.status === 400 || error?.status === 422) {
    return error.body?.error || 'Check the game details and try again.'
  }
  return error?.body?.error || error?.message || fallback
}

// Synthetic newsletter-sourced reel items carry string ids like "yt-123" and
// are not owner-editable (no reorder/delete). Real PlayerLink rows are integers.
const isSynthetic = (item) =>
  typeof item?.id === 'string' && item.id.startsWith('yt-')

function toDateInputValue(value) {
  if (!value) return ''
  const text = String(value)
  const dateOnly = text.match(/^\d{4}-\d{2}-\d{2}/)?.[0]
  if (dateOnly) return dateOnly
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10)
}

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || null
}

function validatePhoto(file) {
  if (!file) return 'Choose a photo to upload.'
  if (!PHOTO_TYPES.has(file.type)) return 'Choose a JPEG, PNG or WebP image.'
  if (file.size > PHOTO_MAX_BYTES) return 'Photos must be 8MB or smaller.'
  return null
}

function SectionHeader({ icon: Icon, eyebrow, title, action }) {
  return (
    <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-start">
      <div className="min-w-0">
        <p className="mb-1 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
          <Icon className="h-3.5 w-3.5" />
          {eyebrow}
        </p>
        {title && <h2 className="text-xl font-bold tracking-tight text-foreground">{title}</h2>}
      </div>
      {action}
    </div>
  )
}

function AffiliationStatusBadge({ status }) {
  if (status === 'club_confirmed') {
    return (
      <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-800">
        Club-confirmed
      </Badge>
    )
  }
  if (status === 'pending') {
    return (
      <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
        Pending review
      </Badge>
    )
  }
  if (status === 'rejected') {
    return (
      <Badge variant="outline" className="border-rose-200 bg-rose-50 text-rose-800">
        Rejected
      </Badge>
    )
  }
  return <Badge variant="secondary">Self-reported</Badge>
}

export function ShowcaseSection({
  playerApiId,
  canonicalPlayerApiId,
  playerName,
  playerPosition,
  season,
  local = false,
  onSeasonStatsChange,
}) {
  const { token } = useAuth()
  const { logout, openLoginModal } = useAuthUI()
  const subjectKey = `${local ? 'local' : 'api'}:${playerApiId}`
  const matchPlayerApiId = canonicalPlayerApiId == null
    ? local ? `-${String(playerApiId)}` : String(playerApiId)
    : String(canonicalPlayerApiId)
  const matchSeason = normalizeSeasonStart(season)
  const goalkeeper = isGoalkeeperPosition(playerPosition)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showcase, setShowcase] = useState(null)
  const [loadedSubjectKey, setLoadedSubjectKey] = useState(null)
  const [myClaims, setMyClaims] = useState([])

  // User/club-fed game rows. Signed ids stay strings at this boundary so a
  // local player's reserved leading minus is never lost to numeric coercion.
  const [games, setGames] = useState([])
  const [gamesLoadedKey, setGamesLoadedKey] = useState(null)
  const [gamesLoadError, setGamesLoadError] = useState(null)
  const [gamesRequest, setGamesRequest] = useState(0)
  const gamesQueryKey = `${matchPlayerApiId}:${matchSeason ?? 'all'}:${token || 'public'}:${gamesRequest}`
  const gamesQueryKeyRef = useRef(gamesQueryKey)
  const gamesLoaded = gamesLoadedKey === gamesQueryKey
  const gamesLoading = !gamesLoaded
  const visibleGames = gamesLoaded ? games : []
  const [gameOpen, setGameOpen] = useState(false)
  const [gameForm, setGameForm] = useState(emptyMatchForm)
  const [gameEditTarget, setGameEditTarget] = useState(null)
  const [gameBusy, setGameBusy] = useState(false)
  const [gameError, setGameError] = useState(null)
  const [gameDeleteOpen, setGameDeleteOpen] = useState(false)
  const [gameDeleteTarget, setGameDeleteTarget] = useState(null)
  const [gameDeleteBusy, setGameDeleteBusy] = useState(false)
  const [gameDeleteError, setGameDeleteError] = useState(null)
  const optimisticGameIdRef = useRef(0)

  useLayoutEffect(() => {
    gamesQueryKeyRef.current = gamesQueryKey
  }, [gamesQueryKey])

  // Claim dialog
  const [claimOpen, setClaimOpen] = useState(false)
  const [claimRelationship, setClaimRelationship] = useState('player')
  const [claimContractStatus, setClaimContractStatus] = useState('')
  const [claimCurrentClubName, setClaimCurrentClubName] = useState('')
  const [claimMessage, setClaimMessage] = useState('')
  const [claimBusy, setClaimBusy] = useState(false)
  const [claimDone, setClaimDone] = useState(false)
  const [claimError, setClaimError] = useState(null)
  const [createdClaim, setCreatedClaim] = useState(null)

  // Social-proof verification dialog
  const [verifyOpen, setVerifyOpen] = useState(false)
  const [proofUrl, setProofUrl] = useState('')
  const [verifyBusy, setVerifyBusy] = useState(false)
  const [verifyDone, setVerifyDone] = useState(false)
  const [verifyError, setVerifyError] = useState(null)
  const [verifyResult, setVerifyResult] = useState(null)
  const [codeCopyState, setCodeCopyState] = useState('idle')

  // Add-video dialog
  const [videoOpen, setVideoOpen] = useState(false)
  const [videoUrl, setVideoUrl] = useState('')
  const [videoTitle, setVideoTitle] = useState('')
  const [videoBusy, setVideoBusy] = useState(false)
  const [videoDone, setVideoDone] = useState(false)
  const [videoError, setVideoError] = useState(null)

  // Photo upload dialog + inline gallery mutations
  const [photoOpen, setPhotoOpen] = useState(false)
  const [photoFile, setPhotoFile] = useState(null)
  const [photoInputKey, setPhotoInputKey] = useState(0)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoDone, setPhotoDone] = useState(false)
  const [photoError, setPhotoError] = useState(null)
  const [photoActionOpen, setPhotoActionOpen] = useState(false)
  const [photoActionBusy, setPhotoActionBusy] = useState(false)
  const [photoActionDone, setPhotoActionDone] = useState(false)
  const [photoActionError, setPhotoActionError] = useState(null)
  const [photoActionCopy, setPhotoActionCopy] = useState({ title: 'Update photos', done: 'Photos updated' })
  const [photoDeleteTarget, setPhotoDeleteTarget] = useState(null)

  // Club affiliation dialog + delete confirmation
  const [clubOpen, setClubOpen] = useState(false)
  const [clubSearch, setClubSearch] = useState('')
  const [clubSearchBusy, setClubSearchBusy] = useState(false)
  const [clubSearchComplete, setClubSearchComplete] = useState(false)
  const [clubSearchError, setClubSearchError] = useState(null)
  const [clubResults, setClubResults] = useState(EMPTY_CLUB_RESULTS)
  const [selectedClub, setSelectedClub] = useState(null)
  const [clubSeason, setClubSeason] = useState('')
  const [createClubMode, setCreateClubMode] = useState(false)
  const [localClubForm, setLocalClubForm] = useState(EMPTY_LOCAL_CLUB_FORM)
  const [duplicateClub, setDuplicateClub] = useState(null)
  const [clubBusy, setClubBusy] = useState(false)
  const [clubDone, setClubDone] = useState(false)
  const [clubError, setClubError] = useState(null)
  const [clubDeleteOpen, setClubDeleteOpen] = useState(false)
  const [clubDeleteTarget, setClubDeleteTarget] = useState(null)
  const [clubDeleteBusy, setClubDeleteBusy] = useState(false)
  const [clubDeleteDone, setClubDeleteDone] = useState(false)
  const [clubDeleteError, setClubDeleteError] = useState(null)

  // Edit-profile dialog
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileForm, setProfileForm] = useState({
    bio: '',
    positions: '',
    preferred_foot: '',
    height_cm: '',
    contract_status: '',
    contract_until: '',
    availability: '',
    nationality_secondary: '',
    languages: '',
    agent_name: '',
    agent_contact_email: '',
  })
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileDone, setProfileDone] = useState(false)
  const [profileError, setProfileError] = useState(null)

  // Reel mutation busy state
  const [reelBusy, setReelBusy] = useState(false)

  const fetchData = useCallback(async () => {
    const [sc, claims] = await Promise.all([
      APIService.getPlayerShowcase(playerApiId, { local }),
      token ? APIService.getMyClaims().catch(() => null) : Promise.resolve(null),
    ])
    const claimsArr = Array.isArray(claims) ? claims : claims?.claims || []
    return { sc, claimsArr }
  }, [local, playerApiId, token])

  // PlayerPage is reused across /players/:id navigations — track the active
  // subject so an in-flight refresh for another API/local player never lands.
  const activeSubjectRef = useRef(subjectKey)
  const previousSubjectRef = useRef(subjectKey)
  const closeTimersRef = useRef({})
  const clubSearchRequestRef = useRef(0)
  const isActiveSubject = () => activeSubjectRef.current === subjectKey

  const clearCloseTimer = useCallback((key) => {
    const timer = closeTimersRef.current[key]
    if (timer) {
      clearTimeout(timer)
      delete closeTimersRef.current[key]
    }
  }, [])

  const clearAllCloseTimers = useCallback(() => {
    Object.values(closeTimersRef.current).forEach((timer) => clearTimeout(timer))
    closeTimersRef.current = {}
  }, [])

  const scheduleClose = useCallback((key, subject, close) => {
    if (activeSubjectRef.current !== subject) return
    clearCloseTimer(key)
    closeTimersRef.current[key] = setTimeout(() => {
      delete closeTimersRef.current[key]
      if (activeSubjectRef.current === subject) close()
    }, 1600)
  }, [clearCloseTimer])

  useLayoutEffect(() => {
    activeSubjectRef.current = subjectKey
  }, [subjectKey])

  useEffect(() => clearAllCloseTimers, [clearAllCloseTimers])

  useEffect(() => {
    let cancelled = false
    APIService.getPlayerMatches(matchPlayerApiId, matchSeason == null ? {} : { season: matchSeason })
      .then((response) => {
        if (cancelled) return
        setGames(Array.isArray(response?.matches) ? response.matches : [])
        setGamesLoadError(null)
        setGamesLoadedKey(gamesQueryKey)
      })
      .catch((requestError) => {
        if (cancelled) return
        setGames([])
        setGamesLoadError(requestError?.status === 404 ? null : 'Games could not be loaded. Try again.')
        setGamesLoadedKey(gamesQueryKey)
      })
    return () => { cancelled = true }
  }, [gamesQueryKey, matchPlayerApiId, matchSeason])

  useEffect(() => {
    let cancelled = false
    if (previousSubjectRef.current !== subjectKey) {
      previousSubjectRef.current = subjectKey
      clearAllCloseTimers()
      setClaimOpen(false)
      setClaimContractStatus('')
      setClaimCurrentClubName('')
      setClaimBusy(false)
      setClaimDone(false)
      setClaimError(null)
      setCreatedClaim(null)
      setVerifyOpen(false)
      setProofUrl('')
      setVerifyBusy(false)
      setVerifyDone(false)
      setVerifyError(null)
      setVerifyResult(null)
      setCodeCopyState('idle')
      setVideoOpen(false)
      setVideoBusy(false)
      setGameOpen(false)
      setGameForm(emptyMatchForm())
      setGameEditTarget(null)
      setGameBusy(false)
      setGameError(null)
      setGameDeleteOpen(false)
      setGameDeleteTarget(null)
      setGameDeleteBusy(false)
      setGameDeleteError(null)
      setPhotoOpen(false)
      setPhotoFile(null)
      setPhotoBusy(false)
      setPhotoDone(false)
      setPhotoError(null)
      setPhotoActionOpen(false)
      setPhotoActionBusy(false)
      setPhotoActionDone(false)
      setPhotoActionError(null)
      setPhotoDeleteTarget(null)
      setPhotoInputKey((key) => key + 1)
      clubSearchRequestRef.current += 1
      setClubOpen(false)
      setClubSearch('')
      setClubSearchBusy(false)
      setClubSearchComplete(false)
      setClubSearchError(null)
      setClubResults(EMPTY_CLUB_RESULTS)
      setSelectedClub(null)
      setClubSeason('')
      setCreateClubMode(false)
      setLocalClubForm(EMPTY_LOCAL_CLUB_FORM)
      setDuplicateClub(null)
      setClubBusy(false)
      setClubDone(false)
      setClubError(null)
      setClubDeleteOpen(false)
      setClubDeleteTarget(null)
      setClubDeleteBusy(false)
      setClubDeleteDone(false)
      setClubDeleteError(null)
      setProfileOpen(false)
      setProfileBusy(false)
      setReelBusy(false)
    }
    setLoading(true)
    setError(false)
    fetchData()
      .then(({ sc, claimsArr }) => {
        if (cancelled) return
        setShowcase(sc || null)
        setMyClaims(claimsArr)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) {
          setLoadedSubjectKey(subjectKey)
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [clearAllCloseTimers, fetchData, subjectKey])

  useEffect(() => {
    const query = clubSearch.trim()
    if (!clubOpen || createClubMode || query.length < 2) return undefined

    const requestId = clubSearchRequestRef.current + 1
    clubSearchRequestRef.current = requestId
    const subject = subjectKey
    const timer = setTimeout(async () => {
      if (clubSearchRequestRef.current !== requestId || activeSubjectRef.current !== subject) return
      setClubSearchBusy(true)
      setClubSearchError(null)
      try {
        const response = await APIService.searchClubs(query)
        if (clubSearchRequestRef.current !== requestId || activeSubjectRef.current !== subject) return
        setClubResults({
          api_teams: Array.isArray(response?.api_teams) ? response.api_teams : [],
          local_clubs: Array.isArray(response?.local_clubs) ? response.local_clubs : [],
        })
        setClubSearchComplete(true)
      } catch (err) {
        if (clubSearchRequestRef.current !== requestId || activeSubjectRef.current !== subject) return
        setClubResults(EMPTY_CLUB_RESULTS)
        setClubSearchComplete(false)
        setClubSearchError(err.body?.error || err.message || 'Failed to search clubs')
      } finally {
        if (clubSearchRequestRef.current === requestId && activeSubjectRef.current === subject) {
          setClubSearchBusy(false)
        }
      }
    }, 300)

    return () => {
      clearTimeout(timer)
      if (clubSearchRequestRef.current === requestId) clubSearchRequestRef.current += 1
    }
  }, [clubOpen, clubSearch, createClubMode, subjectKey])

  const refresh = useCallback(async () => {
    const subject = subjectKey
    try {
      const { sc, claimsArr } = await fetchData()
      if (activeSubjectRef.current !== subject) return
      setShowcase(sc || null)
      setMyClaims(claimsArr)
    } catch {
      // best-effort refresh
    }
  }, [fetchData, subjectKey])

  if (loading || loadedSubjectKey !== subjectKey) {
    return (
      <Card>
        <CardContent className="space-y-4 py-6">
          <Skeleton className="h-4 w-24" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Skeleton className="aspect-video w-full rounded-lg" />
            <Skeleton className="aspect-video w-full rounded-lg" />
          </div>
        </CardContent>
      </Card>
    )
  }

  // On error render nothing — never break the page.
  if (error || !showcase) return null

  const reel = Array.isArray(showcase.reel) ? showcase.reel : []
  const photos = Array.isArray(showcase.photos) ? showcase.photos : []
  const affiliations = Array.isArray(showcase.affiliations) ? showcase.affiliations : []
  const profile = showcase.profile || null
  const verified = !local && Array.isArray(showcase.verified_footage) ? showcase.verified_footage : []
  const claimStatus = showcase.claim_status // 'unclaimed' | 'claimed'

  const signedSubjectId = Number(playerApiId)
  const myClaim = myClaims.find((claim) => {
    const apiClaimMatches = !local && Number(claim.player_api_id) === signedSubjectId
    const localClaimId = Number(claim.local_player_id)
    const localClaimMatches = local
      ? localClaimId === signedSubjectId || String(claim.player_api_id) === matchPlayerApiId
      : signedSubjectId < 0 && (
          localClaimId === signedSubjectId || localClaimId === Math.abs(signedSubjectId)
        )
    return apiClaimMatches || localClaimMatches
  })
  const isOwner = myClaim?.status === 'approved'
  const canManageGames = isOwner && GAME_OWNER_RELATIONSHIPS.has(myClaim?.relationship_type)
  const visibleAffiliations = affiliations.filter(
    (affiliation) => isOwner || PUBLIC_AFFILIATION_STATUSES.has(affiliation.status),
  )

  const approvedPhotos = photos
    .filter((photo) => photo.status === 'approved')
    .sort((a, b) => {
      const primaryOrder = Number(Boolean(b.is_primary)) - Number(Boolean(a.is_primary))
      if (primaryOrder) return primaryOrder
      const aOrder = a.sort_order == null ? Number.MAX_SAFE_INTEGER : a.sort_order
      const bOrder = b.sort_order == null ? Number.MAX_SAFE_INTEGER : b.sort_order
      return aOrder - bOrder || a.id - b.id
    })
  const pendingPhotos = photos.filter((photo) => photo.status === 'pending' || photo.status === 'pending_upload')
  const rejectedPhotos = photos.filter((photo) => photo.status === 'rejected')
  const visiblePhotos = isOwner
    ? [...approvedPhotos, ...pendingPhotos, ...rejectedPhotos]
    : approvedPhotos.filter((photo) => photo.public_url)
  const primaryPhotos = approvedPhotos.filter((photo) => photo.is_primary)
  const reorderablePhotos = approvedPhotos.filter((photo) => !photo.is_primary)

  // Claim strip shows for non-owners who either have a claim (show its status) or
  // can still claim an unclaimed profile.
  const showClaimStrip = !local && !isOwner && (myClaim ? true : claimStatus === 'unclaimed')

  const hasContent = reel.length > 0
    || visiblePhotos.length > 0
    || visibleAffiliations.length > 0
    || profile
    || verified.length > 0
    || visibleGames.length > 0
  if (!hasContent && !isOwner && !showClaimStrip && gamesLoaded && !gamesLoadError) return null

  const reorderableIds = reel.filter((i) => !isSynthetic(i)).map((i) => i.id)

  const openClaimDialog = () => {
    if (local) return
    if (!token) {
      openLoginModal()
      return
    }
    clearCloseTimer('claim')
    setClaimError(null)
    setClaimDone(false)
    setCreatedClaim(null)
    setCodeCopyState('idle')
    setClaimOpen(true)
  }

  const submitClaim = async () => {
    if (local || claimBusy) return
    if (claimRelationship === 'player' && !claimContractStatus) {
      setClaimError('Select your current contract status.')
      return
    }
    const pid = playerApiId
    setClaimBusy(true)
    setClaimError(null)
    try {
      const response = await APIService.submitProfileClaim(pid, {
        relationship_type: claimRelationship,
        message: claimMessage.trim() || undefined,
        contract_status: claimRelationship === 'player' ? claimContractStatus : undefined,
        current_club_name: claimRelationship === 'player'
          ? claimCurrentClubName.trim() || undefined
          : undefined,
      }, { local })
      track('claim_submitted', { player_api_id: pid, relationship: claimRelationship })
      if (isActiveSubject()) {
        setCreatedClaim(response?.claim || null)
        setClaimDone(true)
      }
      await refresh()
    } catch (err) {
      if (isActiveSubject()) {
        setClaimError(err.body?.error || err.message || 'Failed to submit claim')
      }
    } finally {
      if (isActiveSubject()) setClaimBusy(false)
    }
  }

  const copyVerificationCode = async (code) => {
    if (!code) return
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      if (isActiveSubject()) setCodeCopyState('failed')
      return
    }
    try {
      await navigator.clipboard.writeText(code)
      if (isActiveSubject()) setCodeCopyState('copied')
    } catch {
      if (isActiveSubject()) setCodeCopyState('failed')
    }
  }

  const openVerificationDialog = () => {
    if (local) return
    clearCloseTimer('verify')
    setProofUrl(myClaim?.verification_proof_url || '')
    setVerifyError(null)
    setVerifyDone(false)
    setVerifyResult(null)
    setCodeCopyState('idle')
    setVerifyOpen(true)
  }

  const submitVerification = async () => {
    const url = proofUrl.trim()
    if (local || !url || verifyBusy || !myClaim?.id) return
    const claimId = myClaim.id
    setVerifyBusy(true)
    setVerifyError(null)
    setVerifyDone(false)
    setVerifyResult(null)
    try {
      const response = await APIService.verifyClaimProof(claimId, { proof_url: url })
      const checkedClaim = response?.claim || null
      if (isActiveSubject()) {
        setVerifyResult(checkedClaim)
        setVerifyDone(true)
      }
      await refresh()
      if (checkedClaim?.verification_status === 'code_found') {
        scheduleClose('verify', subjectKey, () => {
          setVerifyOpen(false)
          setVerifyDone(false)
        })
      }
    } catch (err) {
      if (isActiveSubject()) {
        setVerifyError(err.body?.error || err.message || 'Failed to check this profile')
      }
    } finally {
      if (isActiveSubject()) setVerifyBusy(false)
    }
  }

  const openVideoDialog = () => {
    clearCloseTimer('video')
    setVideoError(null)
    setVideoDone(false)
    setVideoOpen(true)
  }

  const submitVideo = async () => {
    const url = videoUrl.trim()
    if (!url || videoBusy) return
    if (!isYouTubeUrl(url)) {
      setVideoError('Please enter a valid YouTube link.')
      return
    }
    const pid = playerApiId
    setVideoBusy(true)
    setVideoError(null)
    try {
      await APIService.addShowcaseReelItem(pid, { url, title: videoTitle.trim() || undefined }, { local })
      if (isActiveSubject()) {
        setVideoDone(true)
        setVideoUrl('')
        setVideoTitle('')
      }
      await refresh()
      scheduleClose('video', subjectKey, () => {
        setVideoOpen(false)
        setVideoDone(false)
      })
    } catch (err) {
      if (isActiveSubject()) {
        setVideoError(err.body?.error || err.message || 'Failed to add video')
      }
    } finally {
      if (isActiveSubject()) setVideoBusy(false)
    }
  }

  const openPhotoDialog = () => {
    clearCloseTimer('photoUpload')
    setPhotoFile(null)
    setPhotoError(null)
    setPhotoDone(false)
    setPhotoInputKey((key) => key + 1)
    setPhotoOpen(true)
  }

  const choosePhoto = (event) => {
    const file = event.target.files?.[0] || null
    const validationError = validatePhoto(file)
    setPhotoFile(validationError ? null : file)
    setPhotoError(validationError)
    if (validationError) event.target.value = ''
  }

  const submitPhoto = async () => {
    if (photoBusy) return
    const validationError = validatePhoto(photoFile)
    if (validationError) {
      setPhotoError(validationError)
      return
    }

    const pid = playerApiId
    const file = photoFile
    setPhotoBusy(true)
    setPhotoError(null)
    try {
      const created = await APIService.createShowcasePhoto(pid, {
        content_type: file.type,
        size_bytes: file.size,
      }, { local })
      await APIService.uploadPhotoToUrl(created.upload, file)
      await APIService.completeShowcasePhoto(pid, created.media.id, { local })
      if (isActiveSubject()) {
        setPhotoDone(true)
        setPhotoFile(null)
        setPhotoInputKey((key) => key + 1)
      }
      await refresh()
      scheduleClose('photoUpload', subjectKey, () => {
        setPhotoOpen(false)
        setPhotoDone(false)
      })
    } catch (err) {
      if (isActiveSubject()) {
        setPhotoError(
          err.status === 503
            ? "Photo uploads aren't enabled yet"
            : err.body?.error || err.message || 'Failed to upload photo',
        )
        await refresh()
      }
    } finally {
      if (isActiveSubject()) setPhotoBusy(false)
    }
  }

  const openProfileDialog = () => {
    clearCloseTimer('profile')
    setProfileForm({
      bio: profile?.bio || '',
      positions: profile?.positions || '',
      preferred_foot: profile?.preferred_foot || '',
      height_cm: profile?.height_cm != null ? String(profile.height_cm) : '',
      contract_status: profile?.contract_status || '',
      contract_until: toDateInputValue(profile?.contract_until),
      availability: profile?.availability || '',
      nationality_secondary: profile?.nationality_secondary || '',
      languages: profile?.languages || '',
      agent_name: profile?.agent_name || '',
      agent_contact_email: profile?.agent_contact_email || '',
    })
    setProfileError(null)
    setProfileDone(false)
    setProfileOpen(true)
  }

  const submitProfile = async () => {
    if (profileBusy) return
    const pid = playerApiId
    setProfileBusy(true)
    setProfileError(null)
    try {
      const heightRaw = profileForm.height_cm.trim()
      await APIService.updateShowcaseProfile(pid, {
        bio: profileForm.bio.trim(),
        positions: profileForm.positions.trim(),
        preferred_foot: profileForm.preferred_foot || null,
        height_cm: heightRaw ? parseInt(heightRaw, 10) : null,
        contract_status: profileForm.contract_status || null,
        contract_until: profileForm.contract_until || null,
        availability: profileForm.availability || null,
        nationality_secondary: profileForm.nationality_secondary.trim() || null,
        languages: profileForm.languages.trim() || null,
        agent_name: profileForm.agent_name.trim() || null,
        agent_contact_email: profileForm.agent_contact_email.trim() || null,
      }, { local })
      if (isActiveSubject()) setProfileDone(true)
      await refresh()
      scheduleClose('profile', subjectKey, () => setProfileOpen(false))
    } catch (err) {
      if (isActiveSubject()) {
        setProfileError(err.body?.error || err.message || 'Failed to update profile')
      }
    } finally {
      if (isActiveSubject()) setProfileBusy(false)
    }
  }

  const moveReelItem = async (index, dir) => {
    const target = index + dir
    if (target < 0 || target >= reel.length || reelBusy) return
    if (isSynthetic(reel[index]) || isSynthetic(reel[target])) return
    const next = [...reel]
    ;[next[index], next[target]] = [next[target], next[index]]
    const ordered_ids = next.filter((i) => !isSynthetic(i)).map((i) => i.id)
    const pid = playerApiId
    setReelBusy(true)
    try {
      await APIService.reorderShowcaseReel(pid, { ordered_ids }, { local })
      await refresh()
    } catch {
      // ignore — order unchanged on failure
    } finally {
      if (isActiveSubject()) setReelBusy(false)
    }
  }

  const deleteReelItem = async (linkId) => {
    if (reelBusy) return
    const pid = playerApiId
    setReelBusy(true)
    try {
      await APIService.deleteShowcaseReelItem(pid, linkId, { local })
      await refresh()
    } catch {
      // ignore
    } finally {
      if (isActiveSubject()) setReelBusy(false)
    }
  }

  const beginPhotoAction = (copy) => {
    clearCloseTimer('photoAction')
    setPhotoActionCopy(copy)
    setPhotoActionOpen(true)
    setPhotoActionBusy(true)
    setPhotoActionDone(false)
    setPhotoActionError(null)
    setPhotoDeleteTarget(null)
  }

  const finishPhotoAction = (subject) => {
    if (activeSubjectRef.current !== subject) return
    setPhotoActionDone(true)
    scheduleClose('photoAction', subject, () => {
      setPhotoActionOpen(false)
      setPhotoActionDone(false)
    })
  }

  const requestDeletePhoto = (mediaId) => {
    if (photoActionBusy) return
    clearCloseTimer('photoAction')
    setPhotoActionCopy({ title: 'Delete photo', done: 'Photo deleted' })
    setPhotoDeleteTarget(mediaId)
    setPhotoActionDone(false)
    setPhotoActionError(null)
    setPhotoActionOpen(true)
  }

  const movePhoto = async (mediaId, dir) => {
    if (photoActionBusy) return
    const index = reorderablePhotos.findIndex((photo) => photo.id === mediaId)
    const target = index + dir
    if (index < 0 || target < 0 || target >= reorderablePhotos.length) return
    const next = [...reorderablePhotos]
    ;[next[index], next[target]] = [next[target], next[index]]
    const ordered_ids = [...primaryPhotos, ...next].map((photo) => photo.id)
    const pid = playerApiId
    beginPhotoAction({ title: 'Reorder photos', done: 'Photo order updated' })
    try {
      await APIService.reorderShowcasePhotos(pid, { ordered_ids }, { local })
      if (isActiveSubject()) setPhotoActionDone(true)
      await refresh()
      finishPhotoAction(subjectKey)
    } catch (err) {
      if (isActiveSubject()) {
        setPhotoActionError(err.body?.error || err.message || 'Failed to reorder photos')
      }
    } finally {
      if (isActiveSubject()) setPhotoActionBusy(false)
    }
  }

  const setPrimaryPhoto = async (mediaId) => {
    if (photoActionBusy) return
    const pid = playerApiId
    beginPhotoAction({ title: 'Set primary photo', done: 'Primary photo updated' })
    try {
      await APIService.setShowcasePhotoPrimary(pid, mediaId, { local })
      if (isActiveSubject()) setPhotoActionDone(true)
      await refresh()
      finishPhotoAction(subjectKey)
    } catch (err) {
      if (isActiveSubject()) {
        setPhotoActionError(err.body?.error || err.message || 'Failed to set primary photo')
      }
    } finally {
      if (isActiveSubject()) setPhotoActionBusy(false)
    }
  }

  const deletePhoto = async (mediaId) => {
    if (photoActionBusy) return
    const pid = playerApiId
    beginPhotoAction({ title: 'Delete photo', done: 'Photo deleted' })
    try {
      await APIService.deleteShowcasePhoto(pid, mediaId, { local })
      if (isActiveSubject()) setPhotoActionDone(true)
      await refresh()
      finishPhotoAction(subjectKey)
    } catch (err) {
      if (isActiveSubject()) {
        setPhotoActionError(err.body?.error || err.message || 'Failed to delete photo')
      }
    } finally {
      if (isActiveSubject()) setPhotoActionBusy(false)
    }
  }

  const resetClubDialog = () => {
    clubSearchRequestRef.current += 1
    setClubSearch('')
    setClubSearchBusy(false)
    setClubSearchComplete(false)
    setClubSearchError(null)
    setClubResults(EMPTY_CLUB_RESULTS)
    setSelectedClub(null)
    setClubSeason('')
    setCreateClubMode(false)
    setLocalClubForm(EMPTY_LOCAL_CLUB_FORM)
    setDuplicateClub(null)
    setClubBusy(false)
    setClubDone(false)
    setClubError(null)
  }

  const openClubDialog = () => {
    clearCloseTimer('clubAdd')
    resetClubDialog()
    setClubOpen(true)
  }

  const updateClubSearch = (value) => {
    clubSearchRequestRef.current += 1
    setClubSearch(value)
    setClubSearchBusy(false)
    setClubSearchComplete(false)
    setClubSearchError(null)
    setClubResults(EMPTY_CLUB_RESULTS)
    setSelectedClub(null)
    setDuplicateClub(null)
    setClubError(null)
  }

  const chooseClub = (kind, club) => {
    setSelectedClub({ kind, club })
    setCreateClubMode(false)
    setDuplicateClub(null)
    setClubError(null)
  }

  const toggleCreateClub = () => {
    const next = !createClubMode
    clubSearchRequestRef.current += 1
    setClubSearchBusy(false)
    setCreateClubMode(next)
    setSelectedClub(null)
    setDuplicateClub(null)
    setClubError(null)
    if (next) {
      setLocalClubForm({ ...EMPTY_LOCAL_CLUB_FORM, name: clubSearch.trim() })
    }
  }

  const submitClub = async () => {
    if (clubBusy) return
    if (createClubMode && !localClubForm.name.trim()) {
      setClubError('Enter the club name.')
      return
    }
    if (!createClubMode && !selectedClub) {
      setClubError('Select a club from the search results.')
      return
    }

    const pid = playerApiId
    let stage = createClubMode ? 'create' : 'affiliation'
    setClubBusy(true)
    setClubDone(false)
    setClubError(null)
    setDuplicateClub(null)
    try {
      let selection = selectedClub
      if (createClubMode) {
        const response = await APIService.createLocalClub({
          name: localClubForm.name.trim(),
          country: localClubForm.country.trim() || undefined,
          city: localClubForm.city.trim() || undefined,
          level: localClubForm.level || undefined,
        })
        const club = response?.club
        if (!club?.id) throw new Error('The club was created without an id')
        selection = { kind: 'local', club }
        stage = 'affiliation'
      }

      const affiliationPayload = selection.kind === 'api'
        ? { team_api_id: selection.club.team_api_id }
        : { local_club_id: selection.club.id }
      const season = clubSeason.trim()
      await APIService.addPlayerAffiliation(pid, {
        ...affiliationPayload,
        season: season || undefined,
      }, { local })
      if (isActiveSubject()) setClubDone(true)
      await refresh()
      scheduleClose('clubAdd', subjectKey, () => {
        setClubOpen(false)
        setClubDone(false)
      })
    } catch (err) {
      if (!isActiveSubject()) return
      if (stage === 'create' && err.status === 409 && err.body?.existing) {
        setDuplicateClub(err.body.existing)
        setClubError('A matching community club already exists. Use that club instead.')
      } else {
        setClubError(err.body?.error || err.message || 'Failed to add club')
      }
    } finally {
      if (isActiveSubject()) setClubBusy(false)
    }
  }

  const requestDeleteClub = (affiliation) => {
    if (clubDeleteBusy) return
    clearCloseTimer('clubDelete')
    setClubDeleteTarget(affiliation)
    setClubDeleteDone(false)
    setClubDeleteError(null)
    setClubDeleteOpen(true)
  }

  const deleteClub = async () => {
    if (clubDeleteBusy || !clubDeleteTarget?.id) return
    const pid = playerApiId
    const affiliationId = clubDeleteTarget.id
    setClubDeleteBusy(true)
    setClubDeleteDone(false)
    setClubDeleteError(null)
    try {
      await APIService.deletePlayerAffiliation(pid, affiliationId, { local })
      if (isActiveSubject()) setClubDeleteDone(true)
      await refresh()
      scheduleClose('clubDelete', subjectKey, () => {
        setClubDeleteOpen(false)
        setClubDeleteDone(false)
        setClubDeleteTarget(null)
      })
    } catch (err) {
      if (isActiveSubject()) {
        setClubDeleteError(err.body?.error || err.message || 'Failed to remove club')
      }
    } finally {
      if (isActiveSubject()) setClubDeleteBusy(false)
    }
  }

  const handleExpiredGameSession = (requestError) => {
    if (requestError?.status !== 401) return
    setGameOpen(false)
    setGameEditTarget(null)
    setGameForm(emptyMatchForm())
    setGameError(null)
    setGameBusy(false)
    setGameDeleteOpen(false)
    setGameDeleteTarget(null)
    setGameDeleteError(null)
    setGameDeleteBusy(false)
    logout({ clearAdminKey: true })
    openLoginModal()
  }

  const refreshFilteredGames = async () => {
    const queryKey = gamesQueryKey
    try {
      const response = await APIService.getPlayerMatches(
        matchPlayerApiId,
        matchSeason == null ? {} : { season: matchSeason },
      )
      if (!isActiveSubject() || gamesQueryKeyRef.current !== queryKey) return false
      setGames(Array.isArray(response?.matches) ? response.matches : [])
      setGamesLoadError(null)
      setGamesLoadedKey(queryKey)
      return true
    } catch (requestError) {
      if (!isActiveSubject() || gamesQueryKeyRef.current !== queryKey) return false
      if (requestError?.status === 404) {
        setGames([])
        setGamesLoadError(null)
      } else {
        setGamesLoadError('Games changed, but the latest list could not be loaded. Try again.')
      }
      setGamesLoadedKey(queryKey)
      return requestError?.status === 404
    }
  }

  const reconcileSeasonStats = (response, fallbackSeason) => {
    if (!onSeasonStatsChange) return
    const statsQueryKey = gamesQueryKey
    const returnedStats = response?.season_stats
    const returnedSeason = normalizeSeasonStart(returnedStats?.season)
    if (returnedStats && (matchSeason == null || returnedSeason === matchSeason)) {
      onSeasonStatsChange(returnedStats)
      return
    }
    const statsSeason = matchSeason
      ?? returnedSeason
      ?? normalizeSeasonStart(response?.season)
      ?? normalizeSeasonStart(fallbackSeason)
    if (statsSeason == null) return
    APIService.getPublicPlayerSeasonStats(matchPlayerApiId, statsSeason)
      .then((nextStats) => {
        if (
          activeSubjectRef.current === subjectKey
          && gamesQueryKeyRef.current === statsQueryKey
        ) onSeasonStatsChange(nextStats)
      })
      .catch(() => {})
  }

  const openAddGameDialog = () => {
    if (!canManageGames) return
    setGameEditTarget(null)
    setGameForm(emptyMatchForm())
    setGameError(null)
    setGameOpen(true)
  }

  const openEditGameDialog = (match) => {
    if (!canManageGames || !match?.editable) return
    setGameEditTarget(match)
    setGameForm(matchToForm(match))
    setGameError(null)
    setGameOpen(true)
  }

  const submitGame = async () => {
    if (!canManageGames || gameBusy) return
    const validationError = validateMatchForm(gameForm, goalkeeper)
    if (validationError) {
      setGameError(validationError)
      return
    }

    const payload = buildMatchPayload(gameForm, goalkeeper)
    const mutationQueryKey = gamesQueryKey
    const editing = gameEditTarget
    const targetId = editing?.id
    optimisticGameIdRef.current += 1
    const optimisticId = `optimistic-${subjectKey}-${optimisticGameIdRef.current}`
    const optimisticMatch = {
      ...(editing || {}),
      ...payload,
      id: editing ? targetId : optimisticId,
      player_api_id: matchPlayerApiId,
      season: editing?.season ?? matchSeason,
      source: editing?.source || 'self',
      status: editing?.status || 'self_reported',
      editable: true,
      provenance: editing?.provenance || {
        source_category: 'self',
        source_label: 'Self-reported',
        primary_source: 'user',
      },
    }

    if (editing) {
      setGames((current) => current.map((match) => (
        String(match.id) === String(targetId) ? optimisticMatch : match
      )))
    } else {
      setGames((current) => [optimisticMatch, ...current])
    }

    setGameBusy(true)
    setGameError(null)
    try {
      const response = editing
        ? await APIService.updatePlayerMatch(matchPlayerApiId, targetId, payload)
        : await APIService.createPlayerMatch(matchPlayerApiId, payload)
      if (!response?.match?.id) throw new Error('The saved game was not returned')
      if (!isActiveSubject()) return
      setGameOpen(false)
      setGameEditTarget(null)
      setGameForm(emptyMatchForm())
      if (gamesQueryKeyRef.current !== mutationQueryKey) return
      const replacedId = String(editing ? targetId : optimisticId)
      const returnedId = String(response.match.id)
      setGames((current) => {
        let replaced = false
        const next = []
        for (const match of current) {
          const currentId = String(match.id)
          if (currentId === replacedId) {
            if (!replaced) next.push(response.match)
            replaced = true
          } else if (currentId !== returnedId) {
            next.push(match)
          }
        }
        if (!replaced) next.unshift(response.match)
        return next
      })
      await refreshFilteredGames()
      if (!isActiveSubject() || gamesQueryKeyRef.current !== mutationQueryKey) return
      reconcileSeasonStats(response, response.match.season)
    } catch (requestError) {
      if (!isActiveSubject()) return
      if (gamesQueryKeyRef.current === mutationQueryKey) {
        if (editing) {
          setGames((current) => current.map((match) => (
            String(match.id) === String(targetId) ? editing : match
          )))
        } else {
          setGames((current) => current.filter((match) => String(match.id) !== optimisticId))
        }
        setGameError(matchMutationError(requestError, 'Failed to save this game.'))
      }
      handleExpiredGameSession(requestError)
    } finally {
      if (isActiveSubject()) setGameBusy(false)
    }
  }

  const requestDeleteGame = (match) => {
    if (!canManageGames || !match?.editable || gameDeleteBusy) return
    setGameDeleteTarget(match)
    setGameDeleteError(null)
    setGameDeleteOpen(true)
  }

  const deleteGame = async () => {
    if (!canManageGames || !gameDeleteTarget?.id || gameDeleteBusy) return
    const mutationQueryKey = gamesQueryKey
    const target = gameDeleteTarget
    const targetId = target.id
    const previousIndex = games.findIndex((match) => String(match.id) === String(targetId))
    setGames((current) => current.filter((match) => String(match.id) !== String(targetId)))
    setGameDeleteBusy(true)
    setGameDeleteError(null)
    try {
      const response = await APIService.deletePlayerMatch(matchPlayerApiId, targetId)
      if (!isActiveSubject()) return
      setGameDeleteOpen(false)
      setGameDeleteTarget(null)
      if (gamesQueryKeyRef.current !== mutationQueryKey) return
      await refreshFilteredGames()
      if (!isActiveSubject() || gamesQueryKeyRef.current !== mutationQueryKey) return
      reconcileSeasonStats(response, target.season)
    } catch (requestError) {
      if (!isActiveSubject()) return
      if (gamesQueryKeyRef.current === mutationQueryKey) {
        setGames((current) => {
          if (current.some((match) => String(match.id) === String(targetId))) return current
          const next = [...current]
          const restoreAt = previousIndex < 0 ? 0 : Math.min(previousIndex, next.length)
          next.splice(restoreAt, 0, target)
          return next
        })
        setGameDeleteError(matchMutationError(requestError, 'Failed to delete this game.'))
      }
      handleExpiredGameSession(requestError)
    } finally {
      if (isActiveSubject()) setGameDeleteBusy(false)
    }
  }

  const clubResultCount = clubResults.api_teams.length + clubResults.local_clubs.length
  const canCreateClub = clubSearch.trim().length >= 2
    && clubSearchComplete
    && !clubSearchBusy
    && clubResultCount === 0

  return (
    <Card>
      <CardContent className="space-y-8 py-6">
        {/* Header */}
        <SectionHeader
          icon={Sparkles}
          eyebrow="Showcase"
          title={`${playerName || 'Player'} — Showcase`}
          action={
            isOwner ? (
              <div className="flex w-full shrink-0 flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
                {canManageGames ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={openAddGameDialog}
                    disabled={gamesLoading}
                    className="gap-1.5"
                  >
                    <CalendarDays className="h-3.5 w-3.5" />
                    Add a game
                  </Button>
                ) : null}
                <Button variant="outline" size="sm" onClick={openVideoDialog} className="gap-1.5">
                  <Plus className="h-3.5 w-3.5" />
                  Add video
                </Button>
                <Button variant="outline" size="sm" onClick={openProfileDialog} className="gap-1.5">
                  <Pencil className="h-3.5 w-3.5" />
                  Edit profile
                </Button>
              </div>
            ) : null
          }
        />

        {isOwner && (
          <p className="-mt-4 text-xs text-muted-foreground">
            You manage this profile. Photos, videos and profile edits are reviewed before they appear publicly.
          </p>
        )}

        {/* 1. Photos */}
        {(visiblePhotos.length > 0 || isOwner) && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <ImageIcon className="h-3.5 w-3.5" />
                Photos
              </p>
              {isOwner && (
                <Button variant="outline" size="sm" onClick={openPhotoDialog} disabled={photoBusy} className="gap-1.5">
                  <ImagePlus className="h-3.5 w-3.5" />
                  Add photo
                </Button>
              )}
            </div>

            {visiblePhotos.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {visiblePhotos.map((photo, index) => {
                  const approved = photo.status === 'approved'
                  const pending = photo.status === 'pending'
                  const pendingUpload = photo.status === 'pending_upload'
                  const rejected = photo.status === 'rejected'
                  const imageUrl = approved ? photo.public_url : photo.pending_preview_url
                  const reorderIndex = reorderablePhotos.findIndex((item) => item.id === photo.id)
                  return (
                    <div key={photo.id} className="min-w-0 space-y-2">
                      <div className="group relative aspect-[4/3] overflow-hidden rounded-lg border border-border/70 bg-secondary/50">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={`${playerName || 'Player'} showcase photo ${index + 1}`}
                            width={640}
                            height={480}
                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02] motion-reduce:transform-none motion-reduce:transition-none"
                            loading="lazy"
                          />
                        ) : (
                          <div
                            className="flex h-full flex-col items-center justify-center gap-2 px-3 text-center text-muted-foreground"
                            role="img"
                            aria-label="Photo preview unavailable"
                          >
                            <ImageIcon className="h-7 w-7 opacity-50" />
                            <span className="text-[11px]">
                              {pendingUpload ? 'Upload incomplete' : 'Preview unavailable'}
                            </span>
                          </div>
                        )}

                        <div className="absolute inset-x-2 top-2 flex flex-wrap items-center gap-1.5">
                          {approved && photo.is_primary && (
                            <Badge className="border-white/30 bg-foreground/80 text-background shadow-sm">
                              <Star className="mr-1 h-3 w-3 fill-current" />
                              Primary
                            </Badge>
                          )}
                          {pending && (
                            <Badge variant="outline" className="border-amber-200 bg-amber-50/95 text-amber-800 shadow-sm">
                              Pending review
                            </Badge>
                          )}
                          {pendingUpload && (
                            <Badge variant="outline" className="border-amber-200 bg-amber-50/95 text-amber-800 shadow-sm">
                              Upload incomplete
                            </Badge>
                          )}
                          {rejected && (
                            <Badge variant="outline" className="border-rose-200 bg-rose-50/95 text-rose-800 shadow-sm">
                              Rejected
                            </Badge>
                          )}
                        </div>
                      </div>

                      {isOwner && (
                        <div className="flex min-h-7 items-center justify-between gap-1 px-0.5">
                          {approved ? (
                            <div className="flex items-center gap-0.5">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                disabled={photoActionBusy || photo.is_primary}
                                onClick={() => setPrimaryPhoto(photo.id)}
                                aria-label={photo.is_primary ? 'Primary photo' : 'Set as primary photo'}
                              >
                                <Star className={`h-3.5 w-3.5 ${photo.is_primary ? 'fill-current text-amber-600' : ''}`} />
                              </Button>
                              {!photo.is_primary && (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    disabled={photoActionBusy || reorderIndex <= 0}
                                    onClick={() => movePhoto(photo.id, -1)}
                                    aria-label="Move photo left"
                                  >
                                    <ArrowUp className="h-3.5 w-3.5 -rotate-90" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    disabled={photoActionBusy || reorderIndex === reorderablePhotos.length - 1}
                                    onClick={() => movePhoto(photo.id, 1)}
                                    aria-label="Move photo right"
                                  >
                                    <ArrowDown className="h-3.5 w-3.5 -rotate-90" />
                                  </Button>
                                </>
                              )}
                            </div>
                          ) : (
                            <span className="text-[11px] text-muted-foreground">
                              {pendingUpload ? 'Remove and try again' : 'Visible only to you'}
                            </span>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                            disabled={photoActionBusy}
                            onClick={() => requestDeletePhoto(photo.id)}
                            aria-label="Delete photo"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      )}

                      {isOwner && rejected && photo.review_note && (
                        <p className="break-words px-0.5 text-xs leading-relaxed text-rose-700">
                          Review note: {photo.review_note}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : (
              <button
                type="button"
                onClick={openPhotoDialog}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-8 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
              >
                <ImagePlus className="h-4 w-4" />
                Add the first photo
              </button>
            )}

          </div>
        )}

        {/* 2. Clubs */}
        {(visibleAffiliations.length > 0 || isOwner) && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Building2 className="h-3.5 w-3.5" />
                Clubs
              </p>
              {isOwner && (
                <Button variant="outline" size="sm" onClick={openClubDialog} disabled={clubBusy} className="gap-1.5">
                  <Plus className="h-3.5 w-3.5" />
                  Add club
                </Button>
              )}
            </div>

            {visibleAffiliations.length > 0 ? (
              <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border/70">
                {visibleAffiliations.map((affiliation) => (
                  <div key={affiliation.id} className="px-3 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-semibold text-foreground">
                          {affiliation.club_name || 'Club'}
                        </p>
                        {affiliation.season && (
                          <p className="mt-0.5 text-xs text-muted-foreground">Season {affiliation.season}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <AffiliationStatusBadge status={affiliation.status} />
                        {isOwner && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            disabled={clubDeleteBusy}
                            onClick={() => requestDeleteClub(affiliation)}
                            aria-label={`Remove ${affiliation.club_name || 'club'}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>
                    {isOwner && affiliation.status === 'rejected' && affiliation.review_note && (
                      <p className="mt-2 break-words text-xs leading-relaxed text-rose-700">
                        Review note: {affiliation.review_note}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <button
                type="button"
                onClick={openClubDialog}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-6 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
              >
                <Plus className="h-4 w-4" />
                Add your first club
              </button>
            )}
          </div>
        )}

        {/* 3. Highlight reel */}
        {reel.length > 0 && (
          <div className="space-y-3">
            <p className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <Clapperboard className="h-3.5 w-3.5" />
              Highlight reel
            </p>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {reel.map((item, index) => {
                const synthetic = isSynthetic(item)
                const pending = item.status === 'pending'
                return (
                  <div key={item.id} className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2 px-1">
                      <div className="flex min-w-0 items-center gap-2">
                        {item.title && (
                          <span className="truncate text-sm font-medium text-foreground/80">{item.title}</span>
                        )}
                        {pending && (
                          <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                            Pending review
                          </Badge>
                        )}
                      </div>
                      {isOwner && !synthetic && (
                        <div className="flex shrink-0 items-center gap-0.5">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            disabled={reelBusy || index === 0}
                            onClick={() => moveReelItem(index, -1)}
                            aria-label="Move up"
                          >
                            <ArrowUp className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            disabled={reelBusy || index === reorderableIds.length - 1}
                            onClick={() => moveReelItem(index, 1)}
                            aria-label="Move down"
                          >
                            <ArrowDown className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            disabled={reelBusy}
                            onClick={() => deleteReelItem(item.id)}
                            aria-label="Remove video"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      )}
                      {isOwner && synthetic && (
                        <span className="shrink-0 text-[11px] text-muted-foreground/70">from newsletter</span>
                      )}
                    </div>
                    <VideoEmbed url={item.url} title={item.title} />
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 4. Self-reported profile */}
        {profile && (
          <div className="min-w-0 space-y-3 rounded-lg border border-border/70 bg-secondary/40 p-4">
            <div className="flex items-center gap-2">
              <UserSquare className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold text-foreground">Player profile</span>
              <Badge variant="secondary">Self-reported</Badge>
            </div>
            {profile.bio && <p className="text-sm leading-relaxed text-foreground/90">{profile.bio}</p>}
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              {profile.positions && (
                <div>
                  <span className="text-muted-foreground">Positions: </span>
                  <span className="break-words font-medium text-foreground">{profile.positions}</span>
                </div>
              )}
              {profile.preferred_foot && (
                <div>
                  <span className="text-muted-foreground">Preferred foot: </span>
                  <span className="font-medium capitalize text-foreground">{profile.preferred_foot}</span>
                </div>
              )}
              {profile.height_cm != null && (
                <div>
                  <span className="text-muted-foreground">Height: </span>
                  <span className="font-medium text-foreground">{profile.height_cm} cm</span>
                </div>
              )}
              {(profile.contract_status || profile.contract_until) && (
                <div>
                  <span className="text-muted-foreground">Contract: </span>
                  <span className="font-medium text-foreground">
                    {optionLabel(CONTRACT_STATUS_OPTIONS, profile.contract_status) || 'Status not specified'}
                    {formatDateOnly(profile.contract_until) ? ` · until ${formatDateOnly(profile.contract_until)}` : ''}
                  </span>
                </div>
              )}
              {profile.availability && optionLabel(AVAILABILITY_OPTIONS, profile.availability) && (
                <div>
                  <span className="text-muted-foreground">Availability: </span>
                  <span className="font-medium text-foreground">
                    {optionLabel(AVAILABILITY_OPTIONS, profile.availability)}
                  </span>
                </div>
              )}
              {profile.nationality_secondary && (
                <div>
                  <span className="text-muted-foreground">Second nationality: </span>
                  <span className="break-words font-medium text-foreground">{profile.nationality_secondary}</span>
                </div>
              )}
              {profile.languages && (
                <div>
                  <span className="text-muted-foreground">Languages: </span>
                  <span className="break-words font-medium text-foreground">{profile.languages}</span>
                </div>
              )}
              {profile.agent_name && (
                <div>
                  <span className="text-muted-foreground">Agent: </span>
                  <span className="break-words font-medium text-foreground">{profile.agent_name}</span>
                </div>
              )}
              {profile.agent_contact_email && (
                <div>
                  <span className="text-muted-foreground">Agent email: </span>
                  <a
                    href={`mailto:${profile.agent_contact_email}`}
                    className="break-all font-medium text-primary hover:underline"
                  >
                    {profile.agent_contact_email}
                  </a>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 5. Player- and club-entered games */}
        {(visibleGames.length > 0 || canManageGames || gamesLoading || gamesLoadError) && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5" />
                  Games
                </p>
                {visibleGames.length > 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Each row keeps its reporting source separate.
                  </p>
                ) : null}
              </div>
            </div>

            {gamesLoading && visibleGames.length === 0 ? (
              <div className="space-y-2" aria-busy="true" aria-label="Loading games">
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
              </div>
            ) : gamesLoadError ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-border px-4 py-4">
                <p className="text-sm text-muted-foreground" role="alert">{gamesLoadError}</p>
                <Button variant="outline" size="sm" onClick={() => setGamesRequest((request) => request + 1)}>
                  Try again
                </Button>
              </div>
            ) : visibleGames.length > 0 ? (
              <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border/70" role="list">
                {visibleGames.map((match) => {
                  const scoreEntered = match.result_for != null && match.result_against != null
                  const venue = MATCH_HOME_AWAY_OPTIONS.find((option) => option.value === match.home_away)?.label
                    || match.home_away
                  const editable = canManageGames && match.editable && !String(match.id).startsWith('optimistic-')
                  return (
                    <article key={match.id} className="space-y-2.5 px-3 py-3 sm:px-4" role="listitem">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                            <h3 className="break-words text-sm font-semibold text-foreground">
                              {match.opponent ? `vs ${match.opponent}` : 'Game'}
                            </h3>
                            <span className="text-sm font-semibold tabular-nums text-foreground">
                              {scoreEntered ? `${match.result_for}–${match.result_against}` : 'Score not entered'}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {[formatDateOnly(match.match_date), match.competition, venue].filter(Boolean).join(' · ')}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                          <ProvenanceChip provenance={match.provenance || match.source} />
                          {editable ? (
                            <>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => openEditGameDialog(match)}
                                aria-label={`Edit game against ${match.opponent || 'opponent'}`}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                                onClick={() => requestDeleteGame(match)}
                                aria-label={`Delete game against ${match.opponent || 'opponent'}`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span><strong className="font-semibold text-foreground">{match.minutes ?? 0}</strong> min</span>
                        <span><strong className="font-semibold text-foreground">{match.goals ?? 0}</strong> goals</span>
                        <span><strong className="font-semibold text-foreground">{match.assists ?? 0}</strong> assists</span>
                        <span><strong className="font-semibold text-foreground">{match.yellows ?? 0}</strong> yellow</span>
                        <span><strong className="font-semibold text-foreground">{match.reds ?? 0}</strong> red</span>
                        {match.saves != null ? (
                          <span><strong className="font-semibold text-foreground">{match.saves}</strong> saves</span>
                        ) : null}
                        {match.goals_conceded != null ? (
                          <span><strong className="font-semibold text-foreground">{match.goals_conceded}</strong> conceded</span>
                        ) : null}
                      </div>
                      {match.note ? (
                        <p className="break-words text-xs leading-relaxed text-foreground/75">{match.note}</p>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            ) : canManageGames ? (
              <button
                type="button"
                onClick={openAddGameDialog}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-6 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
              >
                <Plus className="h-4 w-4" />
                Add your first game
              </button>
            ) : null}
          </div>
        )}

        {/* 6. Club-verified footage */}
        {!local && verified.length > 0 && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <span className="text-sm font-semibold text-foreground">Verified appearances</span>
              <Badge className="border-emerald-200 bg-emerald-50 text-emerald-800">Club-verified</Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Verified by the club from match footage (human-confirmed identity).
            </p>
            <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border/70">
              {verified.map((v) => (
                <div key={v.match_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-foreground">
                      {v.opponent_name ? `vs ${v.opponent_name}` : v.team_name || 'Match'}
                    </p>
                    {formatDateOnly(v.match_date) && (
                      <p className="text-xs text-muted-foreground">{formatDateOnly(v.match_date)}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-4 text-right">
                    {v.minutes_on_camera != null && (
                      <div>
                        <p className="font-semibold tabular-nums text-foreground">{v.minutes_on_camera}′</p>
                        <p className="text-[11px] text-muted-foreground">on camera</p>
                      </div>
                    )}
                    {v.pct_of_match != null && (
                      <div>
                        {/* pct_of_match is a 0-1 fraction from the report pipeline */}
                        <p className="font-semibold tabular-nums text-foreground">{Math.round(v.pct_of_match * 100)}%</p>
                        <p className="text-[11px] text-muted-foreground">of match</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 7. Claim strip */}
        {showClaimStrip && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4">
            {myClaim ? (
              myClaim.status === 'pending' ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm text-amber-700">
                      Your claim for this profile is <span className="font-medium">pending review</span>.
                    </p>
                    {myClaim.verification_status === 'code_found' ? (
                      <Badge variant="outline" className="border-emerald-300 text-emerald-700">
                        Code detected
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800">
                        Unverified
                      </Badge>
                    )}
                  </div>
                  <Button variant="outline" size="sm" onClick={openVerificationDialog} className="gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    Verify it&apos;s you
                  </Button>
                </>
              ) : myClaim.status === 'rejected' ? (
                <p className="text-sm text-muted-foreground">Your previous claim for this profile was not approved.</p>
              ) : (
                <p className="text-sm text-muted-foreground">You have a claim on this profile.</p>
              )
            ) : (
              <>
                <p className="text-sm text-muted-foreground">Is this you, or someone you represent?</p>
                <Button variant="outline" size="sm" onClick={openClaimDialog}>
                  Claim this profile
                </Button>
              </>
            )}
          </div>
        )}
      </CardContent>

      {/* Claim dialog */}
      <Dialog open={!local && claimOpen} onOpenChange={setClaimOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Claim {playerName || 'this profile'}</DialogTitle>
            <DialogDescription>
              Tell us your connection to this player. An admin reviews every claim before granting access.
            </DialogDescription>
          </DialogHeader>
          {claimDone ? (
            <div className="space-y-4 py-2">
              <div className="flex items-center gap-2 text-sm text-emerald-600" role="status" aria-live="polite">
                <Check className="h-4 w-4" />
                Submitted for review
              </div>
              <VerificationCode
                code={createdClaim?.verification_code || myClaim?.verification_code}
                copyState={codeCopyState}
                onCopy={copyVerificationCode}
              />
              <VerificationInstructions />
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>I am the…</Label>
                <Select value={claimRelationship} onValueChange={setClaimRelationship}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RELATIONSHIP_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {claimRelationship === 'club_official' ? (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Club officials can claim their club directly on the{' '}
                    <Link to="/my-club" className="font-medium text-primary hover:underline">
                      My Club page
                    </Link>
                    .
                  </p>
                ) : null}
              </div>
              {claimRelationship === 'player' ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="showcase-claim-contract-status">Contract status</Label>
                    <Select
                      value={claimContractStatus}
                      onValueChange={(value) => {
                        setClaimContractStatus(value)
                        if (value === 'free_agent') setClaimCurrentClubName('')
                        setClaimError(null)
                      }}
                      required
                    >
                      <SelectTrigger
                        id="showcase-claim-contract-status"
                        aria-describedby="showcase-claim-contract-status-help"
                      >
                        <SelectValue placeholder="Select your status" />
                      </SelectTrigger>
                      <SelectContent>
                        {CLAIM_CONTRACT_STATUS_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p id="showcase-claim-contract-status-help" className="text-xs leading-relaxed text-muted-foreground">
                      Player claims are for adults aged 18 or older. Choose the status that is true today.
                    </p>
                  </div>
                  {claimContractStatus && claimContractStatus !== 'free_agent' ? (
                    <div className="space-y-2">
                      <Label htmlFor="showcase-claim-current-club">Current club (optional)</Label>
                      <Input
                        id="showcase-claim-current-club"
                        value={claimCurrentClubName}
                        onChange={(event) => setClaimCurrentClubName(event.target.value)}
                        placeholder="Club name"
                        maxLength={180}
                        autoComplete="organization"
                      />
                      <p className="text-xs leading-relaxed text-muted-foreground">
                        Used to help route introductions correctly.
                      </p>
                    </div>
                  ) : null}
                </>
              ) : null}
              <div className="space-y-2">
                <Label>Message (optional)</Label>
                <Textarea
                  placeholder="Anything that helps us verify your claim"
                  value={claimMessage}
                  onChange={(e) => setClaimMessage(e.target.value)}
                  maxLength={1000}
                  rows={3}
                />
              </div>
              {claimError && <p className="text-xs text-destructive">{claimError}</p>}
            </div>
          )}
          {claimDone ? (
            <DialogFooter>
              <Button onClick={() => setClaimOpen(false)}>Done</Button>
            </DialogFooter>
          ) : (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setClaimOpen(false)}>Cancel</Button>
              <Button
                onClick={submitClaim}
                disabled={claimBusy || (claimRelationship === 'player' && !claimContractStatus)}
              >
                {claimBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Submit claim
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {/* Social-proof verification dialog */}
      <Dialog
        open={!local && verifyOpen}
        onOpenChange={(open) => {
          if (verifyBusy) return
          setVerifyOpen(open)
          if (!open) {
            clearCloseTimer('verify')
            setVerifyDone(false)
            setVerifyError(null)
            setVerifyResult(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Verify it&apos;s you</DialogTitle>
            <DialogDescription>
              A best-effort social profile check helps our admin review your claim. It does not approve the claim automatically.
            </DialogDescription>
          </DialogHeader>

          {verifyDone ? (
            <div className="space-y-3 py-2" role="status" aria-live="polite">
              <div className={verifyResult?.verification_status === 'code_found'
                ? 'flex items-start gap-2 text-sm font-medium text-emerald-700'
                : 'flex items-start gap-2 text-sm font-medium text-amber-800'}>
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
              {verifyResult?.verification_note && (
                <p className="rounded-md bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                  {verifyResult.verification_note}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <VerificationCode
                code={myClaim?.verification_code}
                copyState={codeCopyState}
                onCopy={copyVerificationCode}
              />
              <VerificationInstructions />
              <div className="space-y-2">
                <Label htmlFor={`claim-proof-url-${playerApiId}`}>Public profile URL</Label>
                <Input
                  id={`claim-proof-url-${playerApiId}`}
                  type="url"
                  placeholder="https://instagram.com/your-profile"
                  value={proofUrl}
                  onChange={(event) => setProofUrl(event.target.value)}
                  maxLength={500}
                  disabled={verifyBusy}
                  aria-invalid={Boolean(verifyError)}
                  aria-describedby={verifyError ? `claim-proof-error-${playerApiId}` : undefined}
                />
              </div>
              {verifyError && (
                <p id={`claim-proof-error-${playerApiId}`} className="text-xs text-destructive" role="alert">
                  {verifyError}
                </p>
              )}
            </div>
          )}

          {!verifyDone ? (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setVerifyOpen(false)} disabled={verifyBusy}>Cancel</Button>
              <Button onClick={submitVerification} disabled={verifyBusy || !proofUrl.trim()}>
                {verifyBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {verifyBusy ? 'Checking…' : 'Verify'}
              </Button>
            </DialogFooter>
          ) : verifyResult?.verification_status !== 'code_found' ? (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setVerifyOpen(false)}>Close</Button>
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

      {/* Add/edit game dialog */}
      <Dialog
        open={gameOpen}
        onOpenChange={(open) => {
          if (gameBusy) return
          setGameOpen(open)
          if (!open) {
            setGameEditTarget(null)
            setGameForm(emptyMatchForm())
            setGameError(null)
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{gameEditTarget ? 'Edit game' : 'Add a game'}</DialogTitle>
            <DialogDescription>
              Enter this player&apos;s match stats. They will be labelled as self-reported.
            </DialogDescription>
          </DialogHeader>

          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              submitGame()
            }}
          >
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`player-game-date-${playerApiId}`}>Match date</Label>
                <Input
                  id={`player-game-date-${playerApiId}`}
                  type="date"
                  value={gameForm.match_date}
                  max={toLocalISODate(new Date())}
                  onChange={(event) => setGameForm((form) => ({ ...form, match_date: event.target.value }))}
                  disabled={gameBusy}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`player-game-competition-${playerApiId}`}>Competition (optional)</Label>
                <Input
                  id={`player-game-competition-${playerApiId}`}
                  value={gameForm.competition}
                  onChange={(event) => setGameForm((form) => ({ ...form, competition: event.target.value }))}
                  placeholder="e.g. National League U21"
                  maxLength={120}
                  disabled={gameBusy}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`player-game-opponent-${playerApiId}`}>Opponent</Label>
                <Input
                  id={`player-game-opponent-${playerApiId}`}
                  value={gameForm.opponent}
                  onChange={(event) => setGameForm((form) => ({ ...form, opponent: event.target.value }))}
                  placeholder="Opponent name"
                  maxLength={120}
                  disabled={gameBusy}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`player-game-venue-${playerApiId}`}>Home / away</Label>
                <Select
                  value={gameForm.home_away}
                  onValueChange={(value) => setGameForm((form) => ({ ...form, home_away: value }))}
                  disabled={gameBusy}
                >
                  <SelectTrigger id={`player-game-venue-${playerApiId}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MATCH_HOME_AWAY_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <fieldset className="space-y-2 rounded-lg border border-border/70 p-3">
              <legend className="px-1 text-sm font-medium text-foreground">Score (optional)</legend>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor={`player-game-score-for-${playerApiId}`}>Score for</Label>
                  <Input
                    id={`player-game-score-for-${playerApiId}`}
                    type="number"
                    min="0"
                    max="20"
                    step="1"
                    inputMode="numeric"
                    value={gameForm.result_for}
                    onChange={(event) => setGameForm((form) => ({ ...form, result_for: event.target.value }))}
                    disabled={gameBusy}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`player-game-score-against-${playerApiId}`}>Score against</Label>
                  <Input
                    id={`player-game-score-against-${playerApiId}`}
                    type="number"
                    min="0"
                    max="20"
                    step="1"
                    inputMode="numeric"
                    value={gameForm.result_against}
                    onChange={(event) => setGameForm((form) => ({ ...form, result_against: event.target.value }))}
                    disabled={gameBusy}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">Enter either score value when it is known.</p>
            </fieldset>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {[
                ['minutes', 'Minutes', 130],
                ['goals', 'Goals', 20],
                ['assists', 'Assists', 20],
                ['yellows', 'Yellow cards', 20],
                ['reds', 'Red cards', 20],
              ].map(([key, label, maximum]) => (
                <div key={key} className="space-y-2">
                  <Label htmlFor={`player-game-${key}-${playerApiId}`}>{label}</Label>
                  <Input
                    id={`player-game-${key}-${playerApiId}`}
                    type="number"
                    min="0"
                    max={String(maximum)}
                    step="1"
                    inputMode="numeric"
                    value={gameForm[key]}
                    onChange={(event) => setGameForm((form) => ({ ...form, [key]: event.target.value }))}
                    disabled={gameBusy}
                    required
                  />
                </div>
              ))}
            </div>

            {goalkeeper ? (
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['saves', 'Saves'],
                  ['goals_conceded', 'Goals conceded'],
                ].map(([key, label]) => (
                  <div key={key} className="space-y-2">
                    <Label htmlFor={`player-game-${key}-${playerApiId}`}>{label}</Label>
                    <Input
                      id={`player-game-${key}-${playerApiId}`}
                      type="number"
                      min="0"
                      max="20"
                      step="1"
                      inputMode="numeric"
                      value={gameForm[key]}
                      onChange={(event) => setGameForm((form) => ({ ...form, [key]: event.target.value }))}
                      disabled={gameBusy}
                    />
                  </div>
                ))}
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor={`player-game-note-${playerApiId}`}>Note (optional)</Label>
              <Textarea
                id={`player-game-note-${playerApiId}`}
                value={gameForm.note}
                onChange={(event) => setGameForm((form) => ({ ...form, note: event.target.value }))}
                placeholder="Add useful context about the performance"
                maxLength={500}
                rows={3}
                disabled={gameBusy}
              />
            </div>

            {gameError ? <p className="text-sm text-destructive" role="alert">{gameError}</p> : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setGameOpen(false)} disabled={gameBusy}>Cancel</Button>
            <Button type="submit" disabled={gameBusy}>
              {gameBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
              {gameBusy ? 'Saving…' : gameEditTarget ? 'Save changes' : 'Add game'}
            </Button>
          </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete game confirmation */}
      <Dialog
        open={gameDeleteOpen}
        onOpenChange={(open) => {
          if (gameDeleteBusy) return
          setGameDeleteOpen(open)
          if (!open) {
            setGameDeleteTarget(null)
            setGameDeleteError(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete game</DialogTitle>
            <DialogDescription>
              Remove the game against {gameDeleteTarget?.opponent || 'this opponent'} from this player&apos;s stats.
            </DialogDescription>
          </DialogHeader>
          {gameDeleteError ? (
            <p className="text-sm text-destructive" role="alert">{gameDeleteError}</p>
          ) : (
            <p className="text-sm text-foreground/90">This cannot be undone.</p>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setGameDeleteOpen(false)} disabled={gameDeleteBusy}>
              {gameDeleteError ? 'Close' : 'Cancel'}
            </Button>
            {!gameDeleteError ? (
              <Button variant="destructive" onClick={deleteGame} disabled={gameDeleteBusy}>
                {gameDeleteBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                {gameDeleteBusy ? 'Deleting…' : 'Delete game'}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add-video dialog */}
      <Dialog open={videoOpen} onOpenChange={setVideoOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a highlight video</DialogTitle>
            <DialogDescription>
              Paste a YouTube link. Videos are reviewed before appearing on the public profile.
            </DialogDescription>
          </DialogHeader>
          {videoDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600">
              <Check className="h-4 w-4" />
              Submitted for review
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>YouTube URL</Label>
                <Input
                  placeholder="https://youtube.com/watch?v=…"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  type="url"
                  maxLength={500}
                />
              </div>
              <div className="space-y-2">
                <Label>Title (optional)</Label>
                <Input
                  placeholder="e.g. Hat-trick vs. City U21"
                  value={videoTitle}
                  onChange={(e) => setVideoTitle(e.target.value)}
                  maxLength={200}
                />
              </div>
              {videoError && <p className="text-xs text-destructive">{videoError}</p>}
            </div>
          )}
          {!videoDone && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setVideoOpen(false)}>Cancel</Button>
              <Button onClick={submitVideo} disabled={videoBusy || !videoUrl.trim()}>
                {videoBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Add video
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {/* Add-photo dialog */}
      <Dialog
        open={photoOpen}
        onOpenChange={(open) => {
          if (photoBusy) return
          setPhotoOpen(open)
          if (!open) {
            setPhotoFile(null)
            setPhotoDone(false)
            setPhotoError(null)
            setPhotoInputKey((key) => key + 1)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a showcase photo</DialogTitle>
            <DialogDescription>
              Upload a JPEG, PNG or WebP image up to 8MB. Photos are reviewed before appearing publicly.
            </DialogDescription>
          </DialogHeader>
          {photoDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600" role="status" aria-live="polite">
              <Check className="h-4 w-4" />
              Submitted for review
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor={`showcase-photo-${playerApiId}`}>Photo</Label>
                <Input
                  key={photoInputKey}
                  id={`showcase-photo-${playerApiId}`}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={choosePhoto}
                  disabled={photoBusy}
                  aria-invalid={Boolean(photoError)}
                  aria-describedby={photoError ? `showcase-photo-error-${playerApiId}` : undefined}
                />
                {photoFile && (
                  <p className="text-xs text-muted-foreground">
                    {photoFile.name} · {(photoFile.size / (1024 * 1024)).toFixed(1)}MB
                  </p>
                )}
              </div>
              {photoError && (
                <p id={`showcase-photo-error-${playerApiId}`} className="text-xs text-destructive" role="alert">
                  {photoError}
                </p>
              )}
            </div>
          )}
          {!photoDone && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPhotoOpen(false)} disabled={photoBusy}>Cancel</Button>
              <Button onClick={submitPhoto} disabled={photoBusy || !photoFile}>
                {photoBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {photoBusy ? 'Uploading…' : 'Upload photo'}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {/* Photo-action dialog */}
      <Dialog
        open={photoActionOpen}
        onOpenChange={(open) => {
          if (photoActionBusy) return
          setPhotoActionOpen(open)
          if (!open) {
            clearCloseTimer('photoAction')
            setPhotoActionDone(false)
            setPhotoActionError(null)
            setPhotoDeleteTarget(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{photoActionCopy.title}</DialogTitle>
            <DialogDescription>
              Showcase photo changes are applied to this player&apos;s profile.
            </DialogDescription>
          </DialogHeader>

          {photoActionDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600" role="status" aria-live="polite">
              <Check className="h-4 w-4" />
              {photoActionCopy.done}
            </div>
          ) : photoActionError ? (
            <p className="py-2 text-sm text-destructive" role="alert">{photoActionError}</p>
          ) : photoActionBusy ? (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground" role="status" aria-live="polite">
              <Loader2 className="h-4 w-4 animate-spin" />
              Updating photos…
            </div>
          ) : photoDeleteTarget != null ? (
            <p className="py-2 text-sm text-foreground/90">
              Delete this photo permanently? This cannot be undone.
            </p>
          ) : null}

          {!photoActionDone && !photoActionBusy && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPhotoActionOpen(false)}>
                {photoDeleteTarget != null ? 'Cancel' : 'Close'}
              </Button>
              {photoDeleteTarget != null && !photoActionError && (
                <Button variant="destructive" onClick={() => deletePhoto(photoDeleteTarget)}>
                  Delete photo
                </Button>
              )}
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {/* Add-club affiliation dialog */}
      <Dialog
        open={clubOpen}
        onOpenChange={(open) => {
          if (clubBusy) return
          setClubOpen(open)
          if (!open) {
            clearCloseTimer('clubAdd')
            resetClubDialog()
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Add a club</DialogTitle>
            <DialogDescription>
              Search official and community clubs first. New community clubs and affiliations are reviewed before appearing publicly.
            </DialogDescription>
          </DialogHeader>

          {clubDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600" role="status" aria-live="polite">
              <Check className="h-4 w-4" />
              Submitted for review
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor={`showcase-club-search-${playerApiId}`}>Search clubs</Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id={`showcase-club-search-${playerApiId}`}
                    type="search"
                    placeholder="Search by club name"
                    value={clubSearch}
                    onChange={(event) => updateClubSearch(event.target.value)}
                    maxLength={200}
                    disabled={clubBusy || createClubMode}
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

              {clubSearchError ? (
                <p className="text-xs text-destructive" role="alert">{clubSearchError}</p>
              ) : null}

              {!clubSearchBusy && clubSearchComplete && clubResultCount > 0 && !createClubMode ? (
                <div className="max-h-64 space-y-4 overflow-y-auto pr-1">
                  {clubResults.api_teams.length > 0 ? (
                    <div className="space-y-2">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        Official clubs
                      </p>
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
                              className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors ${selected
                                ? 'border-primary/50 bg-primary/5'
                                : 'border-border/70 hover:border-primary/30 hover:bg-muted/50'}`}
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-medium text-foreground">{club.name}</span>
                                {club.country ? (
                                  <span className="block truncate text-xs text-muted-foreground">{club.country}</span>
                                ) : null}
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
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        Community clubs
                      </p>
                      <div className="space-y-1" role="listbox" aria-label="Community clubs">
                        {clubResults.local_clubs.map((club) => {
                          const selected = selectedClub?.kind === 'local'
                            && Number(selectedClub.club.id) === Number(club.id)
                          const location = [club.city, club.country].filter(Boolean).join(', ')
                          const level = optionLabel(CLUB_LEVEL_OPTIONS, club.level)
                          return (
                            <button
                              key={`local-${club.id}`}
                              type="button"
                              role="option"
                              aria-selected={selected}
                              onClick={() => chooseClub('local', club)}
                              className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors ${selected
                                ? 'border-primary/50 bg-primary/5'
                                : 'border-border/70 hover:border-primary/30 hover:bg-muted/50'}`}
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-medium text-foreground">{club.name}</span>
                                {location || level ? (
                                  <span className="block truncate text-xs text-muted-foreground">
                                    {[location, level].filter(Boolean).join(' · ')}
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

              {canCreateClub || createClubMode ? (
                <div className="rounded-lg border border-dashed border-border p-3">
                  <Button type="button" variant="ghost" size="sm" onClick={toggleCreateClub} disabled={clubBusy}>
                    {createClubMode ? 'Back to search' : "Can't find your club? Add it"}
                  </Button>

                  {createClubMode ? (
                    <div className="mt-3 space-y-3 border-t border-border/70 pt-3">
                      <div className="space-y-2">
                        <Label htmlFor={`showcase-local-club-name-${playerApiId}`}>Club name</Label>
                        <Input
                          id={`showcase-local-club-name-${playerApiId}`}
                          value={localClubForm.name}
                          onChange={(event) => setLocalClubForm((form) => ({ ...form, name: event.target.value }))}
                          maxLength={200}
                          disabled={clubBusy}
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor={`showcase-local-club-country-${playerApiId}`}>Country (optional)</Label>
                          <Input
                            id={`showcase-local-club-country-${playerApiId}`}
                            value={localClubForm.country}
                            onChange={(event) => setLocalClubForm((form) => ({ ...form, country: event.target.value }))}
                            maxLength={100}
                            disabled={clubBusy}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`showcase-local-club-city-${playerApiId}`}>City (optional)</Label>
                          <Input
                            id={`showcase-local-club-city-${playerApiId}`}
                            value={localClubForm.city}
                            onChange={(event) => setLocalClubForm((form) => ({ ...form, city: event.target.value }))}
                            maxLength={100}
                            disabled={clubBusy}
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`showcase-local-club-level-${playerApiId}`}>Level (optional)</Label>
                        <Select
                          value={localClubForm.level || 'not_specified'}
                          onValueChange={(value) => setLocalClubForm((form) => ({
                            ...form,
                            level: value === 'not_specified' ? '' : value,
                          }))}
                          disabled={clubBusy}
                        >
                          <SelectTrigger id={`showcase-local-club-level-${playerApiId}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="not_specified">Not specified</SelectItem>
                            {CLUB_LEVEL_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {duplicateClub ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
                  <div className="min-w-0 text-sm text-amber-900">
                    <p className="font-medium">{duplicateClub.name || duplicateClub.club?.name || 'Existing club found'}</p>
                    <p className="text-xs text-amber-800">Use the existing community club instead.</p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => chooseClub('local', duplicateClub.club || duplicateClub)}
                    disabled={clubBusy}
                  >
                    Use this club
                  </Button>
                </div>
              ) : null}

              {selectedClub ? (
                <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
                  <Check className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 truncate font-medium text-foreground">
                    Selected: {selectedClub.club.name}
                  </span>
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor={`showcase-club-season-${playerApiId}`}>Season (optional)</Label>
                <Input
                  id={`showcase-club-season-${playerApiId}`}
                  placeholder="e.g. 2025/26"
                  value={clubSeason}
                  onChange={(event) => setClubSeason(event.target.value)}
                  maxLength={20}
                  disabled={clubBusy}
                />
              </div>

              {clubError ? <p className="text-xs text-destructive" role="alert">{clubError}</p> : null}
            </div>
          )}

          {!clubDone ? (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setClubOpen(false)} disabled={clubBusy}>Cancel</Button>
              <Button
                onClick={submitClub}
                disabled={clubBusy || (createClubMode ? !localClubForm.name.trim() : !selectedClub)}
              >
                {clubBusy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                {clubBusy ? 'Adding…' : 'Add club'}
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Club affiliation delete dialog */}
      <Dialog
        open={clubDeleteOpen}
        onOpenChange={(open) => {
          if (clubDeleteBusy) return
          setClubDeleteOpen(open)
          if (!open) {
            clearCloseTimer('clubDelete')
            setClubDeleteTarget(null)
            setClubDeleteDone(false)
            setClubDeleteError(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove club</DialogTitle>
            <DialogDescription>
              This removes the affiliation from this player&apos;s showcase.
            </DialogDescription>
          </DialogHeader>

          {clubDeleteDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600" role="status" aria-live="polite">
              <Check className="h-4 w-4" />
              Club removed
            </div>
          ) : clubDeleteError ? (
            <p className="py-2 text-sm text-destructive" role="alert">{clubDeleteError}</p>
          ) : clubDeleteBusy ? (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground" role="status" aria-live="polite">
              <Loader2 className="h-4 w-4 animate-spin" />
              Removing club…
            </div>
          ) : (
            <p className="py-2 text-sm text-foreground/90">
              Remove {clubDeleteTarget?.club_name || 'this club'}? This cannot be undone.
            </p>
          )}

          {!clubDeleteDone && !clubDeleteBusy ? (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setClubDeleteOpen(false)}>
                {clubDeleteError ? 'Close' : 'Cancel'}
              </Button>
              {!clubDeleteError ? (
                <Button variant="destructive" onClick={deleteClub}>Remove club</Button>
              ) : null}
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Edit-profile dialog */}
      <Dialog open={profileOpen} onOpenChange={setProfileOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit player profile</DialogTitle>
            <DialogDescription>
              Self-reported details. Edits are re-reviewed before they appear publicly.
            </DialogDescription>
          </DialogHeader>
          {profileDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600">
              <Check className="h-4 w-4" />
              Submitted for review
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor={`showcase-profile-bio-${playerApiId}`}>Bio</Label>
                <Textarea
                  id={`showcase-profile-bio-${playerApiId}`}
                  placeholder="A short bio"
                  value={profileForm.bio}
                  onChange={(e) => setProfileForm((f) => ({ ...f, bio: e.target.value }))}
                  maxLength={2000}
                  rows={4}
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-positions-${playerApiId}`}>Positions</Label>
                  <Input
                    id={`showcase-profile-positions-${playerApiId}`}
                    placeholder="e.g. LW, ST"
                    value={profileForm.positions}
                    onChange={(e) => setProfileForm((f) => ({ ...f, positions: e.target.value }))}
                    maxLength={100}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-foot-${playerApiId}`}>Preferred foot</Label>
                  <Select
                    value={profileForm.preferred_foot}
                    onValueChange={(v) => setProfileForm((f) => ({ ...f, preferred_foot: v }))}
                  >
                    <SelectTrigger id={`showcase-profile-foot-${playerApiId}`}>
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      {FOOT_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-height-${playerApiId}`}>Height (cm)</Label>
                  <Input
                    id={`showcase-profile-height-${playerApiId}`}
                    placeholder="e.g. 178"
                    value={profileForm.height_cm}
                    onChange={(e) => setProfileForm((f) => ({ ...f, height_cm: e.target.value.replace(/[^0-9]/g, '') }))}
                    inputMode="numeric"
                    maxLength={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-nationality-${playerApiId}`}>Second nationality</Label>
                  <Input
                    id={`showcase-profile-nationality-${playerApiId}`}
                    placeholder="e.g. Irish"
                    value={profileForm.nationality_secondary}
                    onChange={(e) => setProfileForm((f) => ({ ...f, nationality_secondary: e.target.value }))}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-contract-${playerApiId}`}>Contract status</Label>
                  <Select
                    value={profileForm.contract_status || 'not_specified'}
                    onValueChange={(v) => setProfileForm((f) => ({
                      ...f,
                      contract_status: v === 'not_specified' ? '' : v,
                    }))}
                  >
                    <SelectTrigger id={`showcase-profile-contract-${playerApiId}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="not_specified">Not specified</SelectItem>
                      {CONTRACT_STATUS_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-contract-until-${playerApiId}`}>Contract until</Label>
                  <Input
                    id={`showcase-profile-contract-until-${playerApiId}`}
                    type="date"
                    value={profileForm.contract_until}
                    onChange={(e) => setProfileForm((f) => ({ ...f, contract_until: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-availability-${playerApiId}`}>Availability</Label>
                  <Select
                    value={profileForm.availability || 'not_specified'}
                    onValueChange={(v) => setProfileForm((f) => ({
                      ...f,
                      availability: v === 'not_specified' ? '' : v,
                    }))}
                  >
                    <SelectTrigger id={`showcase-profile-availability-${playerApiId}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="not_specified">Not specified</SelectItem>
                      {AVAILABILITY_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor={`showcase-profile-languages-${playerApiId}`}>Languages</Label>
                <Input
                  id={`showcase-profile-languages-${playerApiId}`}
                  placeholder="e.g. English, French"
                  value={profileForm.languages}
                  onChange={(e) => setProfileForm((f) => ({ ...f, languages: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-agent-${playerApiId}`}>Agent name</Label>
                  <Input
                    id={`showcase-profile-agent-${playerApiId}`}
                    placeholder="Agent or agency"
                    value={profileForm.agent_name}
                    onChange={(e) => setProfileForm((f) => ({ ...f, agent_name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`showcase-profile-agent-email-${playerApiId}`}>Agent contact email</Label>
                  <Input
                    id={`showcase-profile-agent-email-${playerApiId}`}
                    type="email"
                    placeholder="agent@example.com"
                    value={profileForm.agent_contact_email}
                    onChange={(e) => setProfileForm((f) => ({ ...f, agent_contact_email: e.target.value }))}
                    autoComplete="email"
                  />
                </div>
              </div>
              {profileError && <p className="text-xs text-destructive">{profileError}</p>}
            </div>
          )}
          {!profileDone && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setProfileOpen(false)}>Cancel</Button>
              <Button onClick={submitProfile} disabled={profileBusy}>
                {profileBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Save changes
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default ShowcaseSection
