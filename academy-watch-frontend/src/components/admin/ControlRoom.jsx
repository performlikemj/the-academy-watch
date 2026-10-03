import { cn } from '@/lib/utils'

/**
 * Floodlight control-room building blocks for admin pages (night surface).
 * Presentational only — pages keep their own data, actions and test ids.
 */

export function AdminPageHeader({ eyebrow, title, accent, lede, actions, meta, className, titleId }) {
    return (
        <header className={cn('flex flex-col gap-5 md:flex-row md:items-end md:justify-between', className)}>
            <div className="min-w-0">
                {eyebrow ? <p className="eyebrow mb-3">{eyebrow}</p> : null}
                <h1 id={titleId} className="display text-[2.75rem] leading-[.95] text-chalk sm:text-6xl lg:text-[4.5rem]">
                    {title}
                    {accent ? <> <em className="text-gold">{accent}</em></> : null}
                </h1>
                {lede ? <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-muted-dark">{lede}</p> : null}
            </div>
            {(actions || meta) ? (
                <div className="flex shrink-0 flex-wrap items-center gap-3 md:justify-end">
                    {meta}
                    {actions}
                </div>
            ) : null}
        </header>
    )
}

export function SectionTitle({ title, count, action, as: Tag = 'h2', className }) {
    return (
        <div className={cn('flex items-baseline justify-between gap-4 border-b border-chalk pb-3', className)}>
            <Tag className="display text-[2rem] leading-none text-chalk sm:text-[2.5rem]">{title}</Tag>
            <div className="flex items-baseline gap-4">
                {count != null ? <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-[#8C9791]">{count}</span> : null}
                {action}
            </div>
        </div>
    )
}

export function BigStat({ label, value, sub, subTone = 'muted', testId, className }) {
    const tone = {
        muted: 'text-[#8C9791]',
        good: 'text-[#8FBFA4]',
        warn: 'text-[#E9C46A]',
        danger: 'text-[#E9967A]',
        gold: 'text-gold',
    }[subTone] || 'text-[#8C9791]'
    return (
        <div className={cn('flex min-w-0 flex-col gap-2', className)} data-testid={testId}>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8C9791]">{label}</span>
            <span className="display text-5xl leading-[.9] text-chalk tabular-nums lg:text-[3.5rem]">{value}</span>
            {sub ? <span className={cn('text-[12.5px] leading-snug', tone)}>{sub}</span> : null}
        </div>
    )
}

// Underlined text link used for secondary actions on night surfaces.
export const textLinkClass = 'border-b border-chalk/40 pb-px text-sm text-chalk no-underline transition-colors hover:border-gold hover:no-underline'

/*
 * Calm pages (docs/agents/frontend.md, "House rules"): one sans title and at most
 * one short line, hairlines instead of boxes, status as a dot plus plain words.
 */

export function CalmHeader({ title, line, back, actions, aside, titleId, className }) {
    return (
        <header className={cn('flex flex-wrap items-center justify-between gap-x-4 gap-y-3', className)}>
            <div className="flex min-w-0 flex-col gap-1.5">
                {back}
                <h1 id={titleId} className="m-0 text-[28px] font-semibold leading-tight tracking-[-0.01em] text-chalk [overflow-wrap:anywhere]">{title}</h1>
                {line ? <p className="text-[15px] text-[#C9C5BA] [overflow-wrap:anywhere]">{line}</p> : null}
            </div>
            {aside ? <div className="text-sm text-muted-dark">{aside}</div> : null}
            {actions}
        </header>
    )
}

const DOT_TONES = { gold: 'bg-gold', warn: 'bg-[#E07A5F]', good: 'bg-[#8FBFA4]', quiet: 'bg-chalk/30' }

export function StatusDot({ tone = 'gold', className }) {
    return <span aria-hidden="true" className={cn('h-2 w-2 flex-none rounded-full', DOT_TONES[tone] || DOT_TONES.gold, className)} />
}

/** Status as a dot plus plain words — never a coloured badge. */
export function StatusWords({ tone = 'quiet', children, className }) {
    return <span className={cn('inline-flex items-center gap-2 text-muted-dark', className)}><StatusDot tone={tone} />{children}</span>
}

export function CalmSection({ title, count, children, className, ...props }) {
    return (
        <section className={cn('flex flex-col gap-3', className)} {...props}>
            {title ? <h2 className="m-0 text-base font-semibold text-chalk">{title}{count != null ? <span className="font-normal text-muted-dark"> · {count}</span> : null}</h2> : null}
            {children}
        </section>
    )
}

/** Collapsed detail: the summary line is the label, the proof is one click away. */
export function CalmDetails({ summary, note, noteTone, open, children, className, onToggle }) {
    return (
        <details open={open} onToggle={onToggle} className={cn('border-t border-chalk/[0.12] py-4', className)}>
            <summary className="cursor-pointer text-[15px] font-medium text-chalk focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold">
                {summary}{note ? <span className={cn('font-normal', noteTone === 'warn' ? 'text-[#E07A5F]' : 'text-muted-dark')}> · {note}</span> : null}
            </summary>
            <div className="pt-3 text-sm text-[#C9C5BA]">{children}</div>
        </details>
    )
}

export const calmPanelClass = 'min-w-0 rounded-[18px] border border-chalk/[0.14] p-6'
export const calmPillButton = 'inline-flex h-10 items-center justify-center rounded-full border border-chalk/25 px-4 text-sm text-chalk no-underline transition-colors hover:border-chalk/60 hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold disabled:cursor-not-allowed disabled:opacity-50'
export const calmPrimaryButton = 'inline-flex h-11 items-center justify-center rounded-full bg-chalk px-5 text-sm font-semibold text-ink transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold disabled:cursor-not-allowed disabled:opacity-50'
export const calmWarnButton = 'inline-flex h-10 items-center justify-center rounded-full border border-[#E07A5F]/60 px-4 text-sm text-[#F0A592] transition-colors hover:border-[#E07A5F] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold disabled:cursor-not-allowed disabled:opacity-50'
