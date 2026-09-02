import { useEffect, useState } from 'react'
import { Eye, Heart, ListPlus, Mail } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { APIService } from '@/lib/api'

function count(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
}

function SignalMetric({ icon: Icon, label, accentClass, children }) {
  return (
    <div className="rounded-lg border border-border/70 bg-card/80 p-3.5 shadow-xs">
      <div className="mb-3 flex items-center gap-2">
        <span className={`inline-flex h-7 w-7 items-center justify-center rounded-full ${accentClass}`}>
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</h3>
      </div>
      {children}
    </div>
  )
}

export function WatchingMeCard({ signedId }) {
  const signedIdKey = signedId == null ? '' : String(signedId)
  const [signalState, setSignalState] = useState({ signedIdKey: '', value: null })
  const [emailOptIn, setEmailOptIn] = useState(false)
  const [preferenceReady, setPreferenceReady] = useState(false)
  const [preferenceBusy, setPreferenceBusy] = useState(false)
  const [preferenceError, setPreferenceError] = useState(null)

  useEffect(() => {
    if (!signedIdKey) return undefined

    let cancelled = false

    Promise.all([
      APIService.getMyInterestSignals(),
      APIService.getEmailPreferences().catch(() => null),
    ])
      .then(([signalsResponse, preferencesResponse]) => {
        if (cancelled) return
        const entries = Array.isArray(signalsResponse?.interest_signals)
          ? signalsResponse.interest_signals
          : []
        const matchingSignal = entries.find((entry) => (
          String(entry?.player_api_id) === signedIdKey
        ))
        setSignalState({ signedIdKey, value: matchingSignal || null })

        if (typeof preferencesResponse?.profile_activity_email_opt_in === 'boolean') {
          setEmailOptIn(preferencesResponse.profile_activity_email_opt_in)
          setPreferenceReady(true)
          setPreferenceError(null)
        } else {
          setPreferenceReady(false)
          setPreferenceError('Email preference unavailable.')
        }
      })
      .catch(() => {
        if (!cancelled) setSignalState({ signedIdKey, value: null })
      })

    return () => { cancelled = true }
  }, [signedIdKey])

  const updatePreference = async (checked) => {
    if (!preferenceReady || preferenceBusy) return
    const previous = emailOptIn
    setEmailOptIn(checked)
    setPreferenceBusy(true)
    setPreferenceError(null)
    try {
      const response = await APIService.updateEmailPreferences({
        profile_activity_email_opt_in: checked,
      })
      setEmailOptIn(typeof response?.profile_activity_email_opt_in === 'boolean'
        ? response.profile_activity_email_opt_in
        : checked)
    } catch {
      setEmailOptIn(previous)
      setPreferenceError('We couldn\'t save that preference. Try again.')
    } finally {
      setPreferenceBusy(false)
    }
  }

  const signal = signalState.signedIdKey === signedIdKey ? signalState.value : null
  if (!signal) return null

  const watchlists = signal.watchlists || {}
  const fans = signal.fans || {}
  const views = signal.profile_views || {}

  return (
    <section
      className="overflow-hidden rounded-xl border border-sky-200/80 bg-gradient-to-br from-sky-50/90 via-card to-emerald-50/60 shadow-sm dark:border-sky-900/60 dark:from-sky-950/30 dark:to-emerald-950/20"
      aria-labelledby="watching-me-heading"
      data-testid="watching-me-card"
    >
      <div className="border-b border-sky-200/70 px-4 py-4 sm:px-5 dark:border-sky-900/50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-700 dark:text-sky-300">
              Private owner view
            </p>
            <h2 id="watching-me-heading" className="mt-1 text-lg font-bold tracking-tight text-foreground">
              Who&apos;s watching me
            </h2>
          </div>
          <Eye className="mt-0.5 h-5 w-5 text-sky-700 dark:text-sky-300" aria-hidden="true" />
        </div>
        <p className="mt-2 text-sm text-muted-foreground">Counts only — we never show who.</p>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-3 sm:p-5">
        <SignalMetric icon={ListPlus} label="Watchlists" accentClass="bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <p className="text-2xl font-bold tabular-nums text-foreground">{count(watchlists.total).toLocaleString()}</p>
          <p className="mt-0.5 text-xs font-medium text-amber-700 dark:text-amber-300">
            +{count(watchlists.added_this_week).toLocaleString()} this week
          </p>
        </SignalMetric>
        <SignalMetric icon={Heart} label="Fans" accentClass="bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300">
          <p className="text-2xl font-bold tabular-nums text-foreground">{count(fans.total).toLocaleString()}</p>
          <p className="mt-0.5 text-xs font-medium text-rose-700 dark:text-rose-300">
            +{count(fans.added_this_week).toLocaleString()} this week
          </p>
        </SignalMetric>
        <SignalMetric icon={Eye} label="Profile views" accentClass="bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300">
          <div className="flex items-end gap-4">
            <div>
              <p className="text-2xl font-bold tabular-nums text-foreground">{count(views.last_7_days).toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">7 days</p>
            </div>
            <div>
              <p className="text-lg font-semibold tabular-nums text-foreground">{count(views.last_30_days).toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">30 days</p>
            </div>
          </div>
        </SignalMetric>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-sky-200/70 bg-card/55 px-4 py-3.5 sm:px-5 dark:border-sky-900/50">
        <label className="flex min-w-0 flex-1 items-center gap-2.5" htmlFor="profile-activity-email-opt-in">
          <Mail className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="text-sm font-medium text-foreground">Email me a weekly activity summary</span>
        </label>
        <Switch
          id="profile-activity-email-opt-in"
          checked={emailOptIn}
          disabled={!preferenceReady || preferenceBusy}
          onCheckedChange={updatePreference}
          aria-label="Email me a weekly activity summary"
        />
        {preferenceError ? (
          <p className="basis-full text-xs text-rose-700 dark:text-rose-300" role="status">
            {preferenceError}
          </p>
        ) : null}
      </div>
    </section>
  )
}

export default WatchingMeCard
