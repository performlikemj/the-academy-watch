import { useState, useCallback, useEffect, useRef } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { LogIn, MessageCircle, Maximize2, Minimize2 } from 'lucide-react'
import { GolChatWindow } from './GolChatWindow'
import { useGolChat } from '@/hooks/useGolChat'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import '@/styles/floodlight-night.css'

// The GOL desk is always a night surface, whatever page it opens over.
const NIGHT_PANEL = 'dark fl-night bg-night text-chalk border-hairline-dark'

const STORAGE_KEY = 'gol-chat-expanded'

function getInitialExpanded() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function GolPanel() {
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState(getInitialExpanded)
  const [responseGate, setResponseGate] = useState(null)
  const [billingConfig, setBillingConfig] = useState(null)
  const requestedBillingConfig = useRef(false)
  const auth = useAuth()
  const { logout, openLoginModal } = useAuthUI()
  const identityKey = auth.token
    ? `${auth.userId ?? auth.user_id ?? ''}:${auth.email?.trim().toLowerCase() ?? ''}:${auth.token}`
    : null
  const creditUiLit = auth.scoutPro?.enabled === true && !auth.isAdmin
  const chat = useGolChat(identityKey, {
    freeQuestionsRemaining: auth.scoutPro?.features?.free_questions_remaining,
    creditBalance: auth.scoutPro?.features?.credit_balance,
  }, creditUiLit)

  useEffect(() => {
    if (!creditUiLit || requestedBillingConfig.current) return undefined
    requestedBillingConfig.current = true
    let cancelled = false
    APIService.getBillingConfig()
      .then((config) => { if (!cancelled) setBillingConfig(config) })
      .catch(() => { if (!cancelled) setBillingConfig(null) })
    return () => { cancelled = true }
  }, [creditUiLit])

  useEffect(() => {
    const handleAccessDenied = (event) => {
      if (event.detail?.token !== APIService.userToken) return
      setResponseGate({
        ...event.detail,
        scoutPro: APIService.scoutPro,
      })
      if (event.detail?.state === 'signed_out') logout()
    }
    window.addEventListener(APIService.golAccessEventName, handleAccessDenied)
    return () => window.removeEventListener(APIService.golAccessEventName, handleAccessDenied)
  }, [logout])

  const toggleExpanded = useCallback(() => {
    setExpanded(prev => {
      const next = !prev
      try { localStorage.setItem(STORAGE_KEY, next ? '1' : '0') } catch { /* localStorage unavailable */ }
      return next
    })
  }, [])

  const handleOpen = useCallback(() => setOpen(true), [])
  const handleSignIn = useCallback(() => {
    setOpen(false)
    openLoginModal()
  }, [openLoginModal])

  const currentResponseGate = responseGate?.token === auth.token && responseGate.scoutPro === auth.scoutPro
    ? responseGate.state
    : null
  const accessState = !auth.token || currentResponseGate === 'signed_out'
    ? 'signed_out'
    : 'available'
  const creditsExhausted = creditUiLit
    && (chat.creditsExhausted || auth.scoutPro?.features?.gol_chat === false)

  const headerContent = (
    <div className="flex items-center justify-between w-full pr-8">
      <span className="flex flex-col gap-1 text-left">
        <span className="eyebrow">Scout desk</span>
        <span className="display text-[2rem] leading-none">
          <span className="sr-only">GOL Assistant — </span>Ask <em className="text-gold">GOL</em>
        </span>
      </span>
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleExpanded}
        className="hidden sm:inline-flex h-8 w-8"
        aria-label={expanded ? 'Compact chat' : 'Expand chat'}
      >
        {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
      </Button>
    </div>
  )

  const chatContent = accessState === 'signed_out' ? (
    <div className="flex flex-col items-center justify-center flex-1 px-6 py-12 text-center">
      <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-full border border-gold font-serif text-2xl text-gold" aria-hidden="true">G</span>
      <h3 className="display mb-3 text-4xl">Sign in to ask GOL</h3>
      <p className="mb-7 max-w-sm text-[15px] leading-relaxed text-muted-dark">
        Sign in to start a private GOL conversation about academy players, loan spells, and career journeys.
      </p>
      <Button variant="on-dark" onClick={handleSignIn}>
        <LogIn className="h-4 w-4 mr-2" />
        Sign in
      </Button>
    </div>
  ) : (
    <GolChatWindow
      key={identityKey}
      {...chat}
      expanded={expanded}
      accessState={accessState}
      creditUiLit={creditUiLit}
      creditsExhausted={creditsExhausted}
      billingConfig={billingConfig}
      onSignIn={handleSignIn}
    />
  )

  return (
    <>
      <Button
        onClick={handleOpen}
        aria-label="Open GOL Assistant chat"
        className="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] right-4 z-50 h-14 w-14 rounded-full border border-gold/50 bg-night text-chalk shadow-[0_8px_24px_rgb(11_14_13/0.28)] hover:bg-ink hover:text-gold focus-visible:ring-gold"
        size="icon"
      >
        <MessageCircle className="h-6 w-6" />
      </Button>

      {expanded ? (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className={`${NIGHT_PANEL} flex flex-col max-w-5xl sm:max-w-5xl w-[90vw] h-[85dvh] max-h-[85dvh] p-0 gap-0 overflow-hidden`}>
            <DialogHeader className="px-6 py-5 border-b border-hairline-dark shrink-0">
              <DialogTitle asChild>{headerContent}</DialogTitle>
              <DialogDescription className="sr-only">
                Chat with the GOL Assistant to search for academy player data and loan information.
              </DialogDescription>
            </DialogHeader>
            {chatContent}
          </DialogContent>
        </Dialog>
      ) : (
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="right" className={`${NIGHT_PANEL} w-full sm:max-w-none sm:w-[520px] p-0 flex flex-col`}>
            <SheetHeader className="px-6 py-5 border-b border-hairline-dark">
              <SheetTitle asChild>{headerContent}</SheetTitle>
              <SheetDescription className="sr-only">
                Chat with the GOL Assistant to search for academy player data and loan information.
              </SheetDescription>
            </SheetHeader>
            {chatContent}
          </SheetContent>
        </Sheet>
      )}
    </>
  )
}
