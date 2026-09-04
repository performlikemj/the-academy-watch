import { useEffect, useRef, useState } from 'react'
import { GolMessage } from './GolMessage'
import { GolInput } from './GolInput'
import { GolSuggestions } from './GolSuggestions'
import { PlayerPreviewDrawer } from './PlayerPreviewDrawer'
import { exportChatAsMarkdown } from './exportChat'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { CircleDollarSign, Download, FileDown, Loader2, LogIn, RotateCcw, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

function packOffer(config) {
  const packs = config?.packs || []
  const pack = packs.find((entry) => entry.pack_id === 'gol_starter') || packs[0]
  if (!pack || !Number.isFinite(pack.unit_amount) || !pack.currency || !Number.isFinite(pack.credits)) {
    return 'Buy a credit pack to keep asking GOL.'
  }
  const amount = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: pack.currency,
    maximumFractionDigits: pack.unit_amount % 100 === 0 ? 0 : 2,
  }).format(pack.unit_amount / 100)
  return `Buy the ${pack.label} — ${pack.credits} questions for ${amount}`
}

export function GolChatWindow({
  messages,
  isStreaming,
  sendMessage,
  retryFailedMessage,
  canRetry,
  freeQuestionsRemaining,
  creditBalance,
  topUpPath,
  clearChat,
  stopStreaming,
  expanded,
  accessState,
  creditUiLit,
  creditsExhausted,
  billingConfig,
  onSignIn,
}) {
  const [previewPlayerId, setPreviewPlayerId] = useState(null)
  const [pdfExporting, setPdfExporting] = useState(false)
  const [pdfError, setPdfError] = useState(null)
  const scrollRef = useRef(null)
  const bottomRef = useRef(null)
  const prefersReducedMotion = useRef(
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: prefersReducedMotion.current ? 'instant' : 'smooth' })
  }, [messages])

  const handleExportPdf = async () => {
    setPdfError(null)
    setPdfExporting(true)
    try {
      await APIService.golExportPdf(messages)
    } catch (err) {
      console.error('GOL PDF export failed', err)
      const isSignInRequired = err?.status === 401
      if (!isSignInRequired) setPdfError('PDF export failed. Please try again.')
    } finally {
      setPdfExporting(false)
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain px-4 py-3"
      >
        {messages.length === 0 ? (
          <GolSuggestions onSelect={sendMessage} disabled={accessState !== 'available' || creditsExhausted} />
        ) : (
          <div className="space-y-4 min-w-0">
            {messages.map(msg => (
              <GolMessage key={msg.id} message={msg} expanded={expanded} onPlayerClick={setPreviewPlayerId} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t px-4 py-3">
        {messages.length > 0 && (
          <>
            <div className="flex justify-end gap-1 mb-2">
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => {
                  const md = exportChatAsMarkdown(messages)
                  const blob = new Blob([md], { type: 'text/markdown' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `gol-chat-${new Date().toISOString().slice(0, 10)}.md`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
              >
                <Download className="h-3 w-3 mr-1" /> Save
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={handleExportPdf}
                disabled={pdfExporting || isStreaming || accessState === 'signed_out'}
                title="Download as PDF"
              >
                {pdfExporting ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <FileDown className="h-3 w-3 mr-1" />
                )}
                PDF
              </Button>
              <Button variant="ghost" size="sm" onClick={clearChat} className="text-xs text-muted-foreground">
                <Trash2 className="h-3 w-3 mr-1" /> Clear
              </Button>
            </div>
            {pdfError && (
              <div className="text-xs text-rose-500 mb-2 text-right" role="alert">
                {pdfError}
              </div>
            )}
          </>
        )}
        {accessState === 'signed_out' ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/35 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-foreground">Sign in to ask GOL</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Your suggestions will be waiting when you return.</p>
            </div>
            <Button size="sm" onClick={onSignIn}>
              <LogIn className="mr-1.5 h-4 w-4" />
              Sign in
            </Button>
          </div>
        ) : creditsExhausted ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300/70 bg-amber-50/70 px-4 py-3 text-amber-950">
              <div className="flex min-w-0 items-start gap-2.5">
                <CircleDollarSign className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <div>
                  <p className="text-sm font-semibold">You&apos;re out of GOL questions</p>
                  <p className="mt-0.5 text-xs text-amber-900/80">{packOffer(billingConfig)}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {canRetry ? (
                  <Button size="sm" variant="ghost" onClick={retryFailedMessage} disabled={isStreaming}>
                    <RotateCcw className="mr-1.5 h-3.5 w-3.5" />Retry
                  </Button>
                ) : null}
                <Button size="sm" variant="outline" asChild>
                  <Link to={topUpPath || '/account/billing'}>Get more questions</Link>
                </Button>
              </div>
            </div>
            <GolInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} disabled />
          </div>
        ) : (
          <div className="space-y-2">
            {creditUiLit && freeQuestionsRemaining !== null && creditBalance !== null ? (
              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground" aria-live="polite">
                <span className="font-medium tabular-nums text-foreground/75">
                  {freeQuestionsRemaining > 0
                    ? `${freeQuestionsRemaining} free question${freeQuestionsRemaining === 1 ? '' : 's'} left`
                    : `Credits: ${creditBalance}`}
                </span>
                {canRetry ? (
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={retryFailedMessage} disabled={isStreaming}>
                    <RotateCcw className="mr-1.5 h-3.5 w-3.5" />Retry
                  </Button>
                ) : null}
              </div>
            ) : creditUiLit && canRetry ? (
              <div className="flex justify-end">
                <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={retryFailedMessage} disabled={isStreaming}>
                  <RotateCcw className="mr-1.5 h-3.5 w-3.5" />Retry
                </Button>
              </div>
            ) : null}
            <GolInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} />
          </div>
        )}
      </div>

      <PlayerPreviewDrawer
        playerId={previewPlayerId}
        open={!!previewPlayerId}
        onOpenChange={(open) => { if (!open) setPreviewPlayerId(null) }}
      />
    </div>
  )
}
