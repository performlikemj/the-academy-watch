import { PublicLayout } from '@/components/layouts/PublicLayout'

export function LegalPageLayout({ title, effectiveDate, children }) {
  return (
    <PublicLayout showSponsors={false}>
      <article>
        <header className="dark bg-night text-chalk">
          <div className="floodlight-container py-14 sm:py-20">
            <div className="mx-auto max-w-[70ch]">
              <p className="eyebrow mb-4">The Academy Watch · Legal</p>
              <h1 className="display text-[44px] sm:text-[64px]">
                {title}
              </h1>
              {effectiveDate ? (
                <p className="mt-5 font-mono text-xs uppercase tracking-[0.14em] text-muted-dark">
                  Effective date: {effectiveDate}
                </p>
              ) : null}
            </div>
          </div>
        </header>

        <div className="floodlight-container py-12 sm:py-16">
          <div className="mx-auto max-w-[70ch] space-y-10 text-[1rem] leading-7 text-ink [&_a]:font-medium [&_a]:underline [&_a]:decoration-ink/30 [&_a]:underline-offset-4 hover:[&_a]:decoration-ink [&_h2]:border-b [&_h2]:border-ink [&_h2]:pb-2 [&_h2]:font-serif [&_h2]:text-[28px] [&_h2]:font-normal [&_h2]:leading-tight [&_h2]:tracking-[-0.01em] [&_li]:pl-1 [&_ol]:ml-6 [&_ol]:list-decimal [&_ol]:space-y-3 [&_p]:text-pretty [&_section]:space-y-3 [&_strong]:font-semibold [&_ul]:ml-6 [&_ul]:list-disc [&_ul]:space-y-3">
            {children}
          </div>
        </div>
      </article>
    </PublicLayout>
  )
}

export default LegalPageLayout
