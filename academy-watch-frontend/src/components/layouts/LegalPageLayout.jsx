import { PublicLayout } from '@/components/layouts/PublicLayout'

export function LegalPageLayout({ title, effectiveDate, children }) {
  return (
    <PublicLayout showSponsors={false}>
      <div className="px-4 py-8 sm:px-6 sm:py-12 lg:px-8 lg:py-16">
        <article className="mx-auto max-w-[70ch] overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
          <header className="border-t-4 border-primary border-b border-border px-6 py-8 sm:px-10 sm:py-10">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              The Academy Watch · Legal
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              {title}
            </h1>
            {effectiveDate ? (
              <p className="mt-4 text-sm text-muted-foreground">
                <strong className="font-semibold text-foreground">Effective date: {effectiveDate}</strong>
              </p>
            ) : null}
          </header>

          <div className="space-y-8 px-6 py-8 text-[1rem] leading-7 text-foreground sm:px-10 sm:py-10 [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:decoration-primary/40 [&_a]:underline-offset-4 hover:[&_a]:decoration-primary [&_h2]:text-xl [&_h2]:font-bold [&_h2]:tracking-tight [&_li]:pl-1 [&_ol]:ml-6 [&_ol]:list-decimal [&_ol]:space-y-3 [&_p]:text-pretty [&_section]:space-y-3 [&_strong]:font-semibold [&_ul]:ml-6 [&_ul]:list-disc [&_ul]:space-y-3">
            {children}
          </div>
        </article>
      </div>
    </PublicLayout>
  )
}

export default LegalPageLayout
