/**
 * Small Floodlight building blocks shared by the public pages (club, player,
 * teasers). Tokens and utilities come from src/index.css (L0 contract).
 */
import { InterestSignup } from '@/components/interest/InterestSignup'

/** Serif section title with a 1px ink rule under it and an optional mono counter. */
export function SectionHeading({ id, title, meta, as: Tag = 'h2', className = '', children }) {
  return (
    <div className={`flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-ink pb-3 dark:border-chalk/40 ${className}`}>
      <Tag id={id} className="display text-[34px] sm:text-[44px]">{title}</Tag>
      {meta ? <span className="eyebrow pb-1.5">{meta}</span> : null}
      {children}
    </div>
  )
}

/** Mono label over a big serif number. The number is passed as children. */
export function StatFigure({ label, children, className = '' }) {
  return (
    <div className={`min-w-0 border-b border-border py-5 pr-4 ${className}`}>
      <div className="eyebrow">{label}</div>
      <div className="display mt-1.5 text-[44px] tabular-nums sm:text-[56px]">{children}</div>
    </div>
  )
}

/** Hairline key/value row, as on the player and club sidebars. */
export function FactRow({ label, children }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-border py-3 text-[15px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right [overflow-wrap:anywhere]">{children}</span>
    </div>
  )
}

/** Calm empty state: a short serif line plus a plain explanation. */
export function QuietNote({ title, children, className = '' }) {
  return (
    <div className={`border-b border-border py-8 ${className}`}>
      <p className="display text-2xl">{title}</p>
      {children ? <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">{children}</p> : null}
    </div>
  )
}

/** Compact "coming soon" block for a NEW feature inside an existing page. */
export function TeaserBlock({ feature, eyebrow = 'Coming soon', title, lede, className = '' }) {
  return (
    <section className={`rounded-[10px] border border-border bg-chalk-2/60 p-6 sm:p-8 ${className}`}>
      <p className="eyebrow text-gold-text">{eyebrow}</p>
      <h3 className="display mt-3 text-3xl">{title}</h3>
      {lede ? <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted-foreground">{lede}</p> : null}
      <InterestSignup feature={feature} className="mt-6" />
    </section>
  )
}
