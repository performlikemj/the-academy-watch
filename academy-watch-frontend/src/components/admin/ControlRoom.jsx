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
