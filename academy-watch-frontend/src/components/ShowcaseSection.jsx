import { useState, useEffect } from 'react'
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
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'
import { isYouTubeUrl } from '@/lib/youtube'
import { VideoEmbed } from '@/components/VideoEmbed'

const RELATIONSHIP_OPTIONS = [
  { value: 'player', label: 'Player' },
  { value: 'agent', label: 'Agent' },
  { value: 'guardian', label: 'Parent / Guardian' },
  { value: 'club_official', label: 'Club official' },
]

const FOOT_OPTIONS = [
  { value: 'left', label: 'Left' },
  { value: 'right', label: 'Right' },
  { value: 'both', label: 'Both' },
]

// Synthetic newsletter-sourced reel items carry string ids like "yt-123" and
// are not owner-editable (no reorder/delete). Real PlayerLink rows are integers.
const isSynthetic = (item) =>
  typeof item?.id === 'string' && item.id.startsWith('yt-')

function formatDate(value) {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function SectionHeader({ icon: Icon, eyebrow, title, action }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
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

/**
 * Showcase card. Data (showcase + the viewer's claims) is fetched ONCE by
 * PlayerPage via useShowcase and passed in — hero and this card share one
 * source of truth. The claim dialog's open state is controlled by PlayerPage
 * (`claimOpen` / `onClaimOpenChange`) so the hero's claim CTA can open the
 * same dialog; all claim/video/profile submission logic still lives here.
 */
export function ShowcaseSection({
  playerApiId,
  playerName,
  showcase,
  myClaims = [],
  loading = false,
  error = false,
  refresh,
  claimOpen = false,
  onClaimOpenChange,
  onRequestClaim,
}) {
  // Claim dialog form state (open/close is controlled by the parent)
  const [claimRelationship, setClaimRelationship] = useState('player')
  const [claimMessage, setClaimMessage] = useState('')
  const [claimBusy, setClaimBusy] = useState(false)
  const [claimDone, setClaimDone] = useState(false)
  const [claimError, setClaimError] = useState(null)

  // Add-video dialog
  const [videoOpen, setVideoOpen] = useState(false)
  const [videoUrl, setVideoUrl] = useState('')
  const [videoTitle, setVideoTitle] = useState('')
  const [videoBusy, setVideoBusy] = useState(false)
  const [videoDone, setVideoDone] = useState(false)
  const [videoError, setVideoError] = useState(null)

  // Edit-profile dialog
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileForm, setProfileForm] = useState({ bio: '', positions: '', preferred_foot: '', height_cm: '' })
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileDone, setProfileDone] = useState(false)
  const [profileError, setProfileError] = useState(null)

  // Reel mutation busy state
  const [reelBusy, setReelBusy] = useState(false)

  // Reset the claim form each time the (parent-controlled) dialog opens.
  useEffect(() => {
    if (claimOpen) {
      setClaimError(null)
      setClaimDone(false)
    }
  }, [claimOpen])

  if (loading) {
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
  const profile = showcase.profile || null
  const verified = Array.isArray(showcase.verified_footage) ? showcase.verified_footage : []
  const claimStatus = showcase.claim_status // 'unclaimed' | 'claimed'

  const myClaim = myClaims.find((c) => Number(c.player_api_id) === Number(playerApiId))
  const isOwner = myClaim?.status === 'approved'

  // Claim strip shows for non-owners who either have a claim (show its status) or
  // can still claim an unclaimed profile.
  const showClaimStrip = !isOwner && (myClaim ? true : claimStatus === 'unclaimed')

  const hasContent = reel.length > 0 || profile || verified.length > 0
  if (!hasContent && !isOwner && !showClaimStrip) return null

  const reorderableIds = reel.filter((i) => !isSynthetic(i)).map((i) => i.id)

  const submitClaim = async () => {
    if (claimBusy) return
    setClaimBusy(true)
    setClaimError(null)
    try {
      await APIService.submitProfileClaim(playerApiId, {
        relationship_type: claimRelationship,
        message: claimMessage.trim() || undefined,
      })
      track('claim_submitted', { player_api_id: playerApiId, relationship: claimRelationship })
      setClaimDone(true)
      await refresh?.()
      setTimeout(() => onClaimOpenChange?.(false), 1600)
    } catch (err) {
      setClaimError(err.body?.error || err.message || 'Failed to submit claim')
    } finally {
      setClaimBusy(false)
    }
  }

  const submitVideo = async () => {
    const url = videoUrl.trim()
    if (!url || videoBusy) return
    if (!isYouTubeUrl(url)) {
      setVideoError('Please enter a valid YouTube link.')
      return
    }
    setVideoBusy(true)
    setVideoError(null)
    try {
      await APIService.addShowcaseReelItem(playerApiId, { url, title: videoTitle.trim() || undefined })
      setVideoDone(true)
      setVideoUrl('')
      setVideoTitle('')
      await refresh?.()
      setTimeout(() => { setVideoOpen(false); setVideoDone(false) }, 1600)
    } catch (err) {
      setVideoError(err.body?.error || err.message || 'Failed to add video')
    } finally {
      setVideoBusy(false)
    }
  }

  const openProfileDialog = () => {
    setProfileForm({
      bio: profile?.bio || '',
      positions: profile?.positions || '',
      preferred_foot: profile?.preferred_foot || '',
      height_cm: profile?.height_cm != null ? String(profile.height_cm) : '',
    })
    setProfileError(null)
    setProfileDone(false)
    setProfileOpen(true)
  }

  const submitProfile = async () => {
    if (profileBusy) return
    setProfileBusy(true)
    setProfileError(null)
    try {
      const heightRaw = profileForm.height_cm.trim()
      await APIService.updateShowcaseProfile(playerApiId, {
        bio: profileForm.bio.trim(),
        positions: profileForm.positions.trim(),
        preferred_foot: profileForm.preferred_foot || null,
        height_cm: heightRaw ? parseInt(heightRaw, 10) : null,
      })
      setProfileDone(true)
      await refresh?.()
      setTimeout(() => setProfileOpen(false), 1600)
    } catch (err) {
      setProfileError(err.body?.error || err.message || 'Failed to update profile')
    } finally {
      setProfileBusy(false)
    }
  }

  const moveReelItem = async (index, dir) => {
    const target = index + dir
    if (target < 0 || target >= reel.length || reelBusy) return
    if (isSynthetic(reel[index]) || isSynthetic(reel[target])) return
    const next = [...reel]
    ;[next[index], next[target]] = [next[target], next[index]]
    const ordered_ids = next.filter((i) => !isSynthetic(i)).map((i) => i.id)
    setReelBusy(true)
    try {
      await APIService.reorderShowcaseReel(playerApiId, { ordered_ids })
      await refresh?.()
    } catch {
      // ignore — order unchanged on failure
    } finally {
      setReelBusy(false)
    }
  }

  const deleteReelItem = async (linkId) => {
    if (reelBusy) return
    setReelBusy(true)
    try {
      await APIService.deleteShowcaseReelItem(playerApiId, linkId)
      await refresh?.()
    } catch {
      // ignore
    } finally {
      setReelBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-8 py-6">
        {/* Header */}
        <SectionHeader
          icon={Sparkles}
          eyebrow="Showcase"
          action={
            isOwner ? (
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => { setVideoError(null); setVideoDone(false); setVideoOpen(true) }} className="gap-1.5">
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
            You manage this profile. Videos and profile edits are reviewed before they appear publicly.
          </p>
        )}

        {/* Empty state — invite, never a dead end */}
        {!hasContent && (
          <div className="rounded-lg border border-dashed border-border/80 bg-secondary/30 px-4 py-6 text-center">
            <Clapperboard className="mx-auto mb-2 h-6 w-6 text-muted-foreground/60" />
            <p className="text-sm font-medium text-foreground">No highlights yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {isOwner
                ? 'Add your first video to bring this profile to life.'
                : 'Highlight reels and player details appear here once this profile is claimed.'}
            </p>
          </div>
        )}

        {/* 1. Highlight reel */}
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

        {/* 2. Self-reported profile */}
        {profile && (
          <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/40 p-4">
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
                  <span className="font-medium text-foreground">{profile.positions}</span>
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
            </div>
          </div>
        )}

        {/* 3. Club-verified footage */}
        {verified.length > 0 && (
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
                    {formatDate(v.match_date) && (
                      <p className="text-xs text-muted-foreground">{formatDate(v.match_date)}</p>
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

        {/* 4. Claim strip */}
        {showClaimStrip && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4">
            {myClaim ? (
              myClaim.status === 'pending' ? (
                <p className="text-sm text-amber-700">
                  Your claim for this profile is <span className="font-medium">pending review</span>.
                </p>
              ) : myClaim.status === 'rejected' ? (
                <p className="text-sm text-muted-foreground">Your previous claim for this profile was not approved.</p>
              ) : (
                <p className="text-sm text-muted-foreground">You have a claim on this profile.</p>
              )
            ) : (
              <>
                <p className="text-sm text-muted-foreground">Is this you, or someone you represent?</p>
                <Button variant="outline" size="sm" onClick={onRequestClaim}>
                  Claim this profile
                </Button>
              </>
            )}
          </div>
        )}
      </CardContent>

      {/* Claim dialog */}
      <Dialog open={claimOpen} onOpenChange={onClaimOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Claim {playerName || 'this profile'}</DialogTitle>
            <DialogDescription>
              Tell us your connection to this player. An admin reviews every claim before granting access.
            </DialogDescription>
          </DialogHeader>
          {claimDone ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600">
              <Check className="h-4 w-4" />
              Submitted for review
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
              </div>
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
          {!claimDone && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => onClaimOpenChange?.(false)}>Cancel</Button>
              <Button onClick={submitClaim} disabled={claimBusy}>
                {claimBusy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Submit claim
              </Button>
            </DialogFooter>
          )}
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

      {/* Edit-profile dialog */}
      <Dialog open={profileOpen} onOpenChange={setProfileOpen}>
        <DialogContent>
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
                <Label>Bio</Label>
                <Textarea
                  placeholder="A short bio"
                  value={profileForm.bio}
                  onChange={(e) => setProfileForm((f) => ({ ...f, bio: e.target.value }))}
                  maxLength={2000}
                  rows={4}
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Positions</Label>
                  <Input
                    placeholder="e.g. LW, ST"
                    value={profileForm.positions}
                    onChange={(e) => setProfileForm((f) => ({ ...f, positions: e.target.value }))}
                    maxLength={100}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Preferred foot</Label>
                  <Select
                    value={profileForm.preferred_foot}
                    onValueChange={(v) => setProfileForm((f) => ({ ...f, preferred_foot: v }))}
                  >
                    <SelectTrigger>
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
              <div className="space-y-2">
                <Label>Height (cm)</Label>
                <Input
                  placeholder="e.g. 178"
                  value={profileForm.height_cm}
                  onChange={(e) => setProfileForm((f) => ({ ...f, height_cm: e.target.value.replace(/[^0-9]/g, '') }))}
                  inputMode="numeric"
                  maxLength={3}
                />
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
