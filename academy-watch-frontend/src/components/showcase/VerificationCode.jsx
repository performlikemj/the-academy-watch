import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function VerificationCode({ code, copyState, onCopy }) {
  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Your one-time code
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <code className="text-xl font-bold tracking-[0.16em] text-foreground sm:text-2xl">
          {code || 'Code unavailable'}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onCopy(code)}
          disabled={!code}
          className="gap-1.5"
          aria-label="Copy verification code"
        >
          {copyState === 'copied' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          <span role="status" aria-live="polite">
            {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy code'}
          </span>
        </Button>
      </div>
    </div>
  )
}

export function VerificationInstructions() {
  return (
    <p className="text-sm leading-relaxed text-muted-foreground">
      Add this code to the bio of your public Instagram, TikTok, X, Facebook or YouTube profile, then paste that profile&apos;s URL below.
    </p>
  )
}
