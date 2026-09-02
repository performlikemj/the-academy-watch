import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Download, Loader2, ShieldAlert, Trash2 } from 'lucide-react'

import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
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

const EXPORT_ERROR_MESSAGE = 'We couldn’t prepare your export. Check your connection and try again.'
const EXPORT_RATE_LIMIT_MESSAGE = 'You recently exported your data; try again later.'
const DELETE_ERROR_MESSAGE = 'We couldn’t delete your account. Please check your connection and try again.'

function exportFileName() {
  return `academy-watch-export-${new Date().toISOString().slice(0, 10)}.json`
}

function downloadJson(data) {
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' })
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = exportFileName()
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

export function AccountDataControls() {
  const navigate = useNavigate()
  const { token } = useAuth()
  const { logout } = useAuthUI()
  const [profileRequest, setProfileRequest] = useState(0)
  const [profileState, setProfileState] = useState({ token: null, status: 'loading', email: null })
  const [exporting, setExporting] = useState(false)
  const [exportStatus, setExportStatus] = useState(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    APIService.getProfile()
      .then((profile) => {
        if (cancelled) return
        const email = typeof profile?.email === 'string' ? profile.email.trim().toLowerCase() : ''
        setProfileState({ token, status: email ? 'ready' : 'error', email: email || null })
      })
      .catch(() => {
        if (!cancelled) setProfileState({ token, status: 'error', email: null })
      })
    return () => { cancelled = true }
  }, [profileRequest, token])

  const currentProfile = profileState.token === token ? profileState : null
  const accountEmail = currentProfile?.status === 'ready' ? currentProfile.email : null
  const profileError = currentProfile?.status === 'error'

  const confirmationMatches = Boolean(accountEmail)
    && deleteConfirmation.trim().toLowerCase() === accountEmail

  const handleDownload = async () => {
    if (exporting) return
    setExporting(true)
    setExportStatus(null)
    try {
      const data = await APIService.exportAccountData()
      downloadJson(data)
      setExportStatus({ type: 'success', message: 'Your data download is ready.' })
    } catch (error) {
      setExportStatus({
        type: 'error',
        message: error?.status === 429 ? EXPORT_RATE_LIMIT_MESSAGE : EXPORT_ERROR_MESSAGE,
      })
    } finally {
      setExporting(false)
    }
  }

  const resetDelete = () => {
    setDeleteConfirmation('')
    setDeleteError(null)
  }

  const retryProfile = () => {
    setProfileState({ token, status: 'loading', email: null })
    setProfileRequest((request) => request + 1)
  }

  const openDeleteDialog = () => {
    setDeleteOpen(true)
    if (profileError) retryProfile()
  }

  const handleDeleteOpenChange = (open) => {
    if (deleting) return
    setDeleteOpen(open)
    if (!open) resetDelete()
  }

  const handleDelete = async () => {
    if (!confirmationMatches || deleting) return
    setDeleting(true)
    setDeleteError(null)
    try {
      const result = await APIService.deleteAccount()
      if (result?.deleted !== true) throw new Error('Account deletion was not confirmed')
      APIService.setCuratorKey('')
      logout({ clearAdminKey: true })
      navigate('/', { replace: true })
    } catch (error) {
      if (error?.status === 401) {
        APIService.setCuratorKey('')
        logout({ clearAdminKey: true })
        navigate('/', { replace: true })
        return
      }
      setDeleteError(DELETE_ERROR_MESSAGE)
      setDeleting(false)
    }
  }

  return (
    <>
      <Card className="overflow-hidden border-slate-300">
        <CardHeader className="border-b border-slate-200 bg-slate-50/80">
          <CardTitle>
            <h2 className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-slate-700" />
              Account
            </h2>
          </CardTitle>
          <CardDescription>Download your information or permanently close your account.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 pt-6 md:grid-cols-2">
          <section className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-700">
              <Download className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-foreground">Export my data</h3>
            <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">
              Download a copy of everything we store about you as a JSON file.
            </p>
            <Button className="mt-5 w-full sm:w-auto" variant="outline" onClick={handleDownload} disabled={exporting}>
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {exporting ? 'Preparing download…' : 'Download my data'}
            </Button>
            {exportStatus ? (
              <p
                className={`mt-3 text-sm ${exportStatus.type === 'error' ? 'text-rose-700' : 'text-emerald-700'}`}
                role="status"
              >
                {exportStatus.message}
              </p>
            ) : null}
          </section>

          <section className="flex h-full flex-col rounded-xl border border-rose-200 bg-rose-50/50 p-5">
            <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-rose-100 text-rose-700">
              <Trash2 className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-foreground">Delete my account</h3>
            <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">
              Deletion is immediate and irreversible. You will be signed out on this device.
            </p>
            <Button
              className="mt-5 w-full sm:w-auto"
              variant="destructive"
              onClick={openDeleteDialog}
            >
              <Trash2 className="h-4 w-4" />
              Delete my account
            </Button>
          </section>
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={handleDeleteOpenChange}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-700">
              <Trash2 className="h-5 w-5" />
              Delete your account
            </DialogTitle>
            <DialogDescription className="space-y-3 text-left leading-relaxed">
              <span className="block">
                Deletion is immediate and irreversible. Your sign-in account, profile claims, watchlist, lists,
                contact requests and messages, reports, and other content you submitted will be deleted or
                anonymized where records must be retained.
              </span>
              <span className="block font-medium text-foreground">
                This cannot be undone. Your account and associated data will be deleted immediately.
              </span>
            </DialogDescription>
          </DialogHeader>

          {profileError ? (
            <Alert className="border-rose-300 bg-rose-50">
              <AlertCircle className="h-4 w-4 text-rose-700" />
              <AlertDescription className="flex flex-wrap items-center justify-between gap-2 text-rose-900">
                <span>We couldn’t confirm your account email.</span>
                <Button type="button" variant="outline" size="sm" onClick={retryProfile}>
                  Try again
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="delete-account-email">Type your account email to confirm</Label>
            <p className="text-sm text-muted-foreground">
              {accountEmail || 'Loading your account email…'}
            </p>
            <Input
              id="delete-account-email"
              type="email"
              autoComplete="off"
              placeholder="you@example.com"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              disabled={!accountEmail || deleting}
            />
          </div>

          {deleteError ? (
            <Alert className="border-rose-300 bg-rose-50">
              <AlertCircle className="h-4 w-4 text-rose-700" />
              <AlertDescription className="text-rose-900">{deleteError}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => handleDeleteOpenChange(false)} disabled={deleting}>
              Keep account
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={!confirmationMatches || deleting}>
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              {deleting ? 'Deleting…' : 'Delete account now'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default AccountDataControls
