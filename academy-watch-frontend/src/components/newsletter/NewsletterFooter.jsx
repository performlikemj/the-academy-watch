import { ArrowRight } from 'lucide-react'

/**
 * Newsletter footer — share / forward CTAs and small print. Render-only,
 * no interactivity beyond external links.
 */
export function NewsletterFooter({ webUrl, submitTakeUrl, flagBaseUrl, teamName, newsletterId }) {
  const flagUrl = flagBaseUrl
    ? `${flagBaseUrl}?team_name=${encodeURIComponent(teamName || '')}&newsletter_id=${encodeURIComponent(
        newsletterId || ''
      )}&source=newsletter`
    : null

  return (
    <footer className="mt-16 mb-8 space-y-5">
      {webUrl && (
        <div
          className="rounded-lg p-6 text-center"
          style={{ background: 'var(--tl-section)' }}
        >
          <p className="tl-headline text-base text-[var(--tl-text)] m-0 mb-3">
            Forward this to a colleague
          </p>
          <a
            href={webUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[12px] font-extrabold uppercase tracking-wider no-underline"
            style={{ background: '#ffffff', color: 'var(--tl-page)' }}
          >
            View on web <ArrowRight className="h-3.5 w-3.5" />
          </a>
        </div>
      )}

      {submitTakeUrl && (
        <div
          className="rounded-lg p-6 text-center"
          style={{ background: 'var(--tl-section)' }}
        >
          <p className="tl-headline text-base text-[var(--tl-text)] m-0 mb-3">
            Got a take on a player?
          </p>
          <a
            href={submitTakeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-[12px] font-extrabold uppercase tracking-wider text-white no-underline"
            style={{ background: 'var(--tl-primary)' }}
          >
            Share your take
          </a>
          <p className="text-[11px] text-[var(--tl-text-muted)] mt-3 m-0">
            Your take could be featured in our next edition.
          </p>
        </div>
      )}

      {flagUrl && (
        <div className="text-center text-[11px] text-[var(--tl-text-muted)]">
          Spot something wrong?{' '}
          <a
            href={flagUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--tl-primary)] no-underline hover:underline font-semibold"
          >
            Report a data correction
          </a>
        </div>
      )}
    </footer>
  )
}

export default NewsletterFooter
