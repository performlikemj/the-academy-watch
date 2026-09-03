import { useState, useCallback, useEffect } from 'react'
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
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const identityKey = auth.token
    ? `${auth.userId ?? auth.user_id ?? ''}:${auth.email?.trim().toLowerCase() ?? ''}:${auth.token}`
    : null
  const chat = useGolChat(identityKey)

  useEffect(() => {
    const handleAccessDenied = (event) => {
      if (event.detail?.token !== APIService.userToken) return
      setResponseGate({
        ...event.detail,
        scoutPro: APIService.scoutPro,
      })
    }
    window.addEventListener(APIService.golAccessEventName, handleAccessDenied)
    return () => window.removeEventListener(APIService.golAccessEventName, handleAccessDenied)
  }, [])

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
    : currentResponseGate === 'locked' || auth.scoutPro?.features?.gol_chat === false
      ? 'locked'
      : 'available'

  const headerContent = (
    <div className="flex items-center justify-between w-full pr-8">
      <span className="text-lg font-semibold">GOL Assistant</span>
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
      <MessageCircle className="h-12 w-12 text-muted-foreground mb-4" />
      <h3 className="text-lg font-semibold mb-2">Sign in to ask GOL</h3>
      <p className="text-sm text-muted-foreground mb-6">
        Sign in to start a private GOL conversation about academy players, loan spells, and career journeys.
      </p>
      <Button onClick={handleSignIn}>
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
      onSignIn={handleSignIn}
    />
  )

  return (
    <>
      <Button
        onClick={handleOpen}
        aria-label="Open GOL Assistant chat"
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full shadow-lg bg-primary hover:bg-primary/90 pb-[env(safe-area-inset-bottom)]"
        size="icon"
      >
        <MessageCircle className="h-6 w-6 text-white" />
      </Button>

      {expanded ? (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="flex flex-col max-w-5xl sm:max-w-5xl w-[90vw] h-[85dvh] max-h-[85dvh] p-0 gap-0 overflow-hidden">
            <DialogHeader className="px-4 py-3 border-b shrink-0">
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
          <SheetContent side="right" className="w-full sm:max-w-none sm:w-[520px] p-0 flex flex-col">
            <SheetHeader className="px-4 py-3 border-b">
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
