import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

/**
 * ChartLightbox — opens a single chart at native resolution in a centered
 * modal. Click-outside / ESC / X-button all close (free from Radix).
 *
 * Used by NewsletterView when a user clicks a chart image inside any
 * PlayerCommentaryCard or PlayerCardDrawer. The chart src is the same
 * base64 data URI baked into the newsletter content — no separate fetch.
 */
export function ChartLightbox({ open, onOpenChange, url, alt, caption }) {
  if (!url) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="newsletter-tactical-lens max-w-[min(95vw,1100px)] sm:max-w-[min(92vw,1100px)] p-0 overflow-hidden border-0 bg-[var(--tl-card)]"
      >
        <DialogHeader className="px-5 pt-5 pb-3 text-left">
          <DialogTitle className="tl-headline text-base sm:text-lg text-[var(--tl-text)] m-0">
            {caption || alt || 'Chart'}
          </DialogTitle>
          <DialogDescription className="text-[12px] text-[var(--tl-text-muted)] m-0">
            Click outside or press ESC to close.
          </DialogDescription>
        </DialogHeader>
        <div className="px-5 pb-6">
          <img
            src={url}
            alt={alt || 'Chart'}
            className="block w-full h-auto max-h-[78vh] object-contain rounded-md"
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default ChartLightbox
